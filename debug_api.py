# python debug_api.py
import requests
import json
from base64 import b64encode
from datetime import datetime
import sqlite3

def get_ayar(anahtar):
    conn = sqlite3.connect("dentalpazar.db")
    row = conn.execute("SELECT deger FROM ayarlar WHERE anahtar=?", (anahtar,)).fetchone()
    conn.close()
    return row[0] if row else ""

supplier_id = get_ayar("supplier_id")
api_key     = get_ayar("api_key")
api_secret  = get_ayar("api_secret")

credentials = b64encode(f"{api_key}:{api_secret}".encode()).decode()
headers = {
    "Authorization": f"Basic {credentials}",
    "User-Agent": "dentalpazar - SelfIntegration",
    "Content-Type": "application/json"
}

# Son 7 gün
baslangic = datetime(2026, 6, 1)
bitis     = datetime(2026, 6, 8, 23, 59, 59)

params = {
    "startDate": int(baslangic.timestamp() * 1000),
    "endDate":   int(bitis.timestamp() * 1000),
    "page": 0,
    "size": 5,  # sadece ilk 5 siparis
    "orderByField": "CreatedDate",
    "orderByDirection": "DESC"
}

url = f"https://api.trendyol.com/sapigw/suppliers/{supplier_id}/orders"
resp = requests.get(url, headers=headers, params=params, timeout=30)

print(f"HTTP Status: {resp.status_code}")
print(f"URL: {resp.url}")
print()

if resp.status_code == 200:
    data = resp.json()
    print(f"totalPages    : {data.get('totalPages')}")
    print(f"totalElements : {data.get('totalElements')}")
    print(f"page          : {data.get('page')}")
    print(f"size          : {data.get('size')}")
    print()

    orders = data.get("content", [])
    print(f"Bu sayfada {len(orders)} siparis geldi")
    print()

    for i, order in enumerate(orders[:2]):
        print(f"--- Siparis {i+1} ---")
        print(f"  orderNumber : {order.get('orderNumber')}")
        print(f"  status      : {order.get('status')}")
        lines = order.get("lines", [])
        for j, line in enumerate(lines):
            print(f"  LINE {j+1} - TUM ALANLAR:")
            print(json.dumps(line, ensure_ascii=False, indent=4))
        print()
else:
    print(f"HATA: {resp.text}")
