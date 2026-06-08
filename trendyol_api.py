import requests
from base64 import b64encode
from datetime import datetime, timedelta

BASE_URL = "https://api.trendyol.com/sapigw"
CHUNK_DAYS = 3           # 3 günlük chunk: daha küçük aralık = daha güvenilir veri
MAX_PAGES  = 50          # Sonsuz döngü koruması
IPTAL_DURUMLARI = {"Cancelled", "Returned"}


def get_auth_header(api_key, api_secret):
    credentials = b64encode(f"{api_key}:{api_secret}".encode()).decode()
    return {
        "Authorization": f"Basic {credentials}",
        "User-Agent":    "dentalpazar - SelfIntegration",
        "Content-Type":  "application/json",
    }


def get_orders_page(supplier_id, api_key, api_secret, start_date, end_date, page=0, size=200):
    url = f"{BASE_URL}/suppliers/{supplier_id}/orders"
    params = {
        "startDate":        int(start_date.timestamp() * 1000),
        "endDate":          int(end_date.timestamp()   * 1000),
        "page":             page,
        "size":             size,
        "orderByField":     "CreatedDate",
        "orderByDirection": "DESC",
    }
    try:
        resp = requests.get(
            url,
            headers=get_auth_header(api_key, api_secret),
            params=params,
            timeout=30,
        )
        if resp.status_code == 200:
            return resp.json(), None
        return None, f"API Hatası {resp.status_code}: {resp.text[:300]}"
    except Exception as e:
        return None, f"Bağlantı hatası: {e}"


def _get_range(supplier_id, api_key, api_secret, start_date, end_date, size=200):
    """Tek bir aralık için tüm sayfaları çeker. totalPages'e güvenmek yerine
    alınan kayıt sayısı < size olduğunda durur (daha güvenilir)."""
    all_orders = []
    page = 0
    while page < MAX_PAGES:
        data, error = get_orders_page(
            supplier_id, api_key, api_secret, start_date, end_date, page, size
        )
        if error:
            return None, error
        orders = data.get("content", [])
        all_orders.extend(orders)
        # Son sayfa tespiti: hem totalPages hem sayı bazlı çift kontrol
        total_pages = data.get("totalPages", 1)
        if len(orders) < size or page >= total_pages - 1:
            break
        page += 1
    return all_orders, None


chunk_debug_log = []   # Her çekimde sıfırlanır; app.py okur


def get_all_orders(supplier_id, api_key, api_secret, start_date, end_date):
    """
    Tarih aralığını CHUNK_DAYS'lik parçalara bölerek sorgular.
    Aynı sipariş numarası birden fazla parçada gelebileceğinden deduplikasyon yapılır.
    """
    global chunk_debug_log
    chunk_debug_log = []
    seen = {}   # orderNumber -> order dict
    current = start_date

    while current < end_date:
        chunk_end = min(current + timedelta(days=CHUNK_DAYS), end_date)
        orders, error = _get_range(supplier_id, api_key, api_secret, current, chunk_end)
        if error:
            return None, error
        yeni = 0
        for order in (orders or []):
            key = order.get("orderNumber") or id(order)
            if key not in seen:
                seen[key] = order
                yeni += 1
        chunk_debug_log.append({
            "aralik": f"{current.date()} → {chunk_end.date()}",
            "alinan": len(orders or []),
            "yeni":   yeni,
        })
        current = chunk_end

    return list(seen.values()), None


def parse_orders(orders):
    rows = []
    for order in orders:
        order_number = order.get("orderNumber", "")
        order_date   = datetime.fromtimestamp(order.get("orderDate", 0) / 1000)
        status       = order.get("status", "")

        for line in order.get("lines", []):
            birim_liste   = line.get("amount") or 0
            birim_gercek  = line.get("price") or line.get("lineUnitPrice") or birim_liste
            komisyon_oran = line.get("commission") or 0
            adet          = line.get("quantity") or 1
            kategori      = line.get("businessUnit") or ""

            # Tüm fiyatlar TOPLAM (× adet)
            toplam_liste   = round(birim_liste  * adet, 2)
            toplam_satis   = round(birim_gercek * adet, 2)
            iskonto        = round(toplam_liste - toplam_satis, 2)
            komisyon_tutar = round(toplam_satis * komisyon_oran / 100, 2)
            net_odeme      = round(toplam_satis - komisyon_tutar, 2)

            rows.append({
                "siparis_no":    order_number,
                "tarih":         order_date,
                "durum":         status,
                "urun_adi":      line.get("productName", ""),
                "barkod":        line.get("barcode", ""),
                "urun_kodu":     line.get("merchantSku", ""),
                "kategori":      kategori,
                "adet":          adet,
                "liste_fiyati":  toplam_liste,
                "iskonto":       iskonto,
                "satis_fiyati":  toplam_satis,
                "komisyon_oran": komisyon_oran,
                "komisyon":      komisyon_tutar,
                "net_odeme":     net_odeme,
            })
    return rows
