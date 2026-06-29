import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta, date

from database import (
    init_db, get_maliyetler, get_maliyet_map, get_marka_map,
    save_maliyet, get_giderler, save_gider, delete_gider,
    get_ayar, save_ayar, get_markalar, add_marka, delete_marka
)
from trendyol_api import get_all_orders, parse_orders, IPTAL_DURUMLARI
import trendyol_api as _tapi
from rapor import pdf_olustur
from auth import (
    giris_yap, kullanici_olustur, kullanici_sil,
    aktif_degistir, kullanici_sayisi, tum_kullanicilar, sifre_degistir
)

# ── Sayfa ayarları ──────────────────────────────────────────────
st.set_page_config(
    page_title="Dentalpazar | Kar Takip",
    page_icon="🦷",
    layout="wide",
    initial_sidebar_state="expanded"
)
init_db()

# ── İlk kurulum: hiç kullanıcı yoksa admin oluştur ──────────────
if kullanici_sayisi() == 0:
    st.markdown("## 🦷 Dentalpazar — İlk Kurulum")
    st.info("Sisteme ilk girişte bir **admin** hesabı oluşturmanız gerekiyor.")
    with st.form("ilk_kurulum_form"):
        _ik_k = st.text_input("Admin Kullanıcı Adı")
        _ik_s = st.text_input("Şifre", type="password")
        _ik_s2 = st.text_input("Şifre (tekrar)", type="password")
        if st.form_submit_button("Admin Hesabı Oluştur", type="primary"):
            if not _ik_k.strip() or not _ik_s:
                st.error("Kullanıcı adı ve şifre boş olamaz.")
            elif _ik_s != _ik_s2:
                st.error("Şifreler eşleşmiyor.")
            else:
                kullanici_olustur(_ik_k.strip(), _ik_s, "admin")
                st.success("Admin hesabı oluşturuldu! Giriş yapabilirsiniz.")
                st.rerun()
    st.stop()

# ── Login kontrolü ───────────────────────────────────────────────
if "oturum" not in st.session_state:
    st.session_state["oturum"] = None

if st.session_state["oturum"] is None:
    _lc1, _lc2, _lc3 = st.columns([1.4, 2, 1.4])
    with _lc2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("## 🦷 Dentalpazar")
        st.caption("Trendyol Kar Takip Sistemi")
        st.markdown("---")
        with st.form("login_form"):
            _lk = st.text_input("Kullanıcı Adı")
            _ls = st.text_input("Şifre", type="password")
            if st.form_submit_button("🔐 Giriş Yap", type="primary", use_container_width=True):
                _user = giris_yap(_lk, _ls)
                if _user:
                    st.session_state["oturum"] = _user
                    st.rerun()
                else:
                    st.error("Kullanıcı adı veya şifre hatalı.")
        st.caption("Erişim için sistem yöneticinize (admin) başvurun.")
    st.stop()

# ── Session state ────────────────────────────────────────────────
for key, val in [("df", None), ("baslangic", None), ("bitis", None), ("yuklendi", False)]:
    if key not in st.session_state:
        st.session_state[key] = val

# ── Yardımcı fonksiyonlar ────────────────────────────────────────

def get_api_config():
    return {
        "supplier_id": get_ayar("supplier_id"),
        "api_key":     get_ayar("api_key"),
        "api_secret":  get_ayar("api_secret"),
    }


def api_hazir():
    cfg = get_api_config()
    return all(cfg.values())


def veri_cek(baslangic, bitis):
    cfg     = get_api_config()
    start   = datetime.combine(baslangic, datetime.min.time())
    end     = datetime.combine(bitis, datetime.max.time().replace(microsecond=0))

    # API lastModifiedDate'e göre filtreler; 7'şer günlük chunk'larla sorgularız.
    # Seçilen başlangıçtan 5 gün önce başlayıp bugüne kadar sorgularız.
    api_start = datetime.combine(baslangic - timedelta(days=5), datetime.min.time())
    api_end   = datetime.combine(date.today(), datetime.max.time().replace(microsecond=0))

    toplam_gun   = (api_end - api_start).days
    chunk_sayisi = max(1, (toplam_gun + 6) // 7)

    with st.spinner(f"Trendyol'dan veriler alınıyor... ({chunk_sayisi} parça sorgu)"):
        orders, error = get_all_orders(
            cfg["supplier_id"], cfg["api_key"], cfg["api_secret"], api_start, api_end
        )

    if error:
        st.error(f"API Hatası: {error}")
        return False

    ham_siparis_sayisi = len(set(o.get("orderNumber", "") for o in (orders or [])))

    rows = parse_orders(orders)
    if not rows:
        st.warning("Bu tarih aralığında sipariş bulunamadı.")
        return False

    df = pd.DataFrame(rows)
    df["tarih"] = pd.to_datetime(df["tarih"])
    # Sipariş tarihine göre kesin filtrele
    df_all = df.copy()   # filtre öncesi (tüm API verisi)
    df = df[(df["tarih"] >= start) & (df["tarih"] <= end)]

    if df.empty:
        st.warning("Seçilen tarihlerde sipariş bulunamadı.")
        return False

    st.session_state.df              = df
    st.session_state.baslangic       = baslangic
    st.session_state.bitis           = bitis
    st.session_state.yuklendi        = True
    st.session_state.ham_siparis     = ham_siparis_sayisi   # debug: API'den gelen ham sipariş
    st.session_state.filtrelenmis_sp = df["siparis_no"].nunique()  # filtre sonrası
    return True


def hesapla_kar(df):
    maliyet_map = get_maliyet_map()
    marka_map   = get_marka_map()
    df = df.copy()
    df["maliyet_birim"]   = df["barkod"].map(maliyet_map).fillna(0)
    df["toplam_maliyet"]  = df["maliyet_birim"] * df["adet"]
    df["marka"]           = df["barkod"].map(marka_map).fillna("")
    df["brut_kar"]        = df["net_odeme"] - df["toplam_maliyet"]
    return df


def aktif_df(df):
    return df[~df["durum"].isin(IPTAL_DURUMLARI)].copy()


def iptal_df(df):
    return df[df["durum"].isin(IPTAL_DURUMLARI)].copy()


def para(x):
    return f"₺{x:,.2f}"


DURUM_TR = {
    "Created":     "Oluşturuldu",
    "Picking":     "Hazırlanıyor",
    "Invoiced":    "Faturalandı",
    "Shipped":     "Kargoya Verildi",
    "Delivered":   "Teslim Edildi",
    "UnDelivered": "Teslim Edilemedi",
    "Returned":    "İade Edildi",
    "Cancelled":   "İptal Edildi",
    "UnSupplied":  "Tedarik Edilemedi",
}

def durum_tr(durum):
    return DURUM_TR.get(durum, durum)


# ── Sidebar ──────────────────────────────────────────────────────
_magaza_adi = get_ayar("magaza_adi", "Dentalpazar")
with st.sidebar:
    st.markdown(f"## 🦷 {_magaza_adi}")
    st.caption("Trendyol Kar Takip Sistemi")
    st.markdown("---")

    st.markdown("**📅 Tarih Aralığı**")
    b_col, e_col = st.columns(2)
    with b_col:
        bas = st.date_input("Başlangıç", value=date.today() - timedelta(days=7), label_visibility="collapsed")
    with e_col:
        bit = st.date_input("Bitiş", value=date.today(), label_visibility="collapsed")
    st.caption(f"{bas.strftime('%d.%m.%Y')} – {bit.strftime('%d.%m.%Y')}")

    if not api_hazir():
        st.warning("API bilgileri eksik → Ayarlar")
    else:
        vb1, vb2 = st.columns(2)
        with vb1:
            if st.button("🔄 Veri Çek", type="primary", use_container_width=True):
                veri_cek(bas, bit)
        with vb2:
            if st.button("🗑️ Temizle", use_container_width=True):
                st.session_state.df        = None
                st.session_state.yuklendi  = False
                st.session_state.baslangic = None
                st.session_state.bitis     = None
                st.rerun()

    if st.session_state.yuklendi:
        n = len(st.session_state.df)
        st.success(f"✅ {n} satır yüklendi")
        st.caption(f"{st.session_state.baslangic.strftime('%d.%m.%Y')} – {st.session_state.bitis.strftime('%d.%m.%Y')}")
    else:
        st.info("Veri bekleniyor")

    st.markdown("---")
    _oturum = st.session_state.get("oturum", {})
    sayfa = st.radio(
        "Menü",
        ["📊 Dashboard", "📦 Siparişler", "💰 Ürün Maliyetleri", "📋 Giderler", "📄 Rapor", "🔍 Panel Karşılaştır", "⚙️ Ayarlar"],
        label_visibility="collapsed"
    )
    st.markdown("---")
    _rol_etiket = " 👑 admin" if _oturum.get("rol") == "admin" else ""
    st.caption(f"👤 **{_oturum.get('kullanici_adi', '')}**{_rol_etiket}")
    if st.button("🚪 Çıkış Yap", use_container_width=True):
        st.session_state["oturum"] = None
        st.rerun()
    st.markdown("---")
    st.caption("Hazırlayan: **Taha Salman**")


# ════════════════════════════════════════════════════════════════
# DASHBOARD
# ════════════════════════════════════════════════════════════════
if sayfa == "📊 Dashboard":
    st.title("📊 Dashboard")

    if not st.session_state.yuklendi:
        st.info("Sol taraftan tarih seçip **Veri Çek** butonuna bas.")
        st.stop()

    df_raw = st.session_state.df
    df     = hesapla_kar(df_raw)
    aktif  = aktif_df(df)
    iptal  = iptal_df(df)

    giderler    = get_giderler(str(st.session_state.baslangic), str(st.session_state.bitis))
    toplam_gider = giderler["tutar"].sum() if not giderler.empty else 0

    # Gider payını sipariş bazında dağıt
    if not aktif.empty and aktif["net_odeme"].sum() > 0:
        aktif = aktif.copy()
        aktif["gider_payi"] = aktif["net_odeme"] / aktif["net_odeme"].sum() * toplam_gider
        aktif["net_kar"]    = aktif["brut_kar"] - aktif["gider_payi"]
    else:
        aktif = aktif.copy()
        aktif["gider_payi"] = 0
        aktif["net_kar"]    = aktif["brut_kar"]

    # Brüt = TÜM siparişler (iptal dahil), panelle aynı mantık
    brut_satis    = df["liste_fiyati"].sum()
    brut_adet     = int(df["adet"].sum())

    # İptal / iade adet ve bedel (satis_fiyati ile, panelin gösterdiği şekilde)
    iptal_df_c    = iptal[iptal["durum"] == "Cancelled"]
    iade_df_c     = iptal[iptal["durum"] == "Returned"]
    iptal_adet    = int(iptal_df_c["adet"].sum())
    iade_adet     = int(iade_df_c["adet"].sum())
    iptal_bedel   = iptal_df_c["satis_fiyati"].sum()
    iade_bedel    = iade_df_c["satis_fiyati"].sum()

    indirim_top   = aktif["iskonto"].sum()
    net_satis     = aktif["satis_fiyati"].sum()
    net_adet      = int(aktif["adet"].sum())
    toplam_kom    = aktif["komisyon"].sum()
    net_odeme_top = aktif["net_odeme"].sum()
    toplam_maliyet= aktif["toplam_maliyet"].sum()
    net_kar       = aktif["net_kar"].sum()
    siparis_sayisi= aktif["siparis_no"].nunique()

    # ── Metrikler ──
    st.markdown("#### Satış Özeti")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Brüt Satış",       para(brut_satis),
              help=f"Tüm siparişler (iptal dahil) | {brut_adet} adet")
    c2.metric("İptaller",         para(-iptal_bedel),
              help=f"{iptal_adet} adet iptal edildi")
    c3.metric("İadeler",          para(-iade_bedel),
              help=f"{iade_adet} adet iade edildi")
    c4.metric("İndirimler",       para(-indirim_top),
              help="Liste fiyatı − gerçek satış fiyatı")
    c5.metric("Net Satış",        para(net_satis),
              help=f"Aktif ve teslim edilen siparişler | {net_adet} adet")

    st.markdown("---")
    c6, c7, c8, c9, c10 = st.columns(5)
    c6.metric("Toplam Komisyon",  para(-toplam_kom),
              help="Trendyol'un kestiği komisyon")
    c7.metric("Net Trendyol Öd.", para(net_odeme_top),
              help="Trendyol'un sana ödeyeceği net tutar")
    c8.metric("Ürün Maliyeti",    para(-toplam_maliyet))
    c9.metric("Diğer Giderler",   para(-toplam_gider))
    marj = (net_kar / net_satis * 100) if net_satis > 0 else 0
    c10.metric("NET KAR",         para(net_kar), delta=f"%{marj:.1f} marj")

    st.markdown("---")
    cs1, cs2, cs3, cs4 = st.columns(4)
    cs1.metric("Aktif Sipariş",  siparis_sayisi)
    cs2.metric("İptal Adet",     iptal_adet,
               help=f"₺{iptal_bedel:,.2f} tutarında {iptal_adet} ürün iptal")
    cs3.metric("İade Adet",      iade_adet,
               help=f"₺{iade_bedel:,.2f} tutarında {iade_adet} ürün iade")
    _ham = st.session_state.get("ham_siparis", "?")
    _fil = st.session_state.get("filtrelenmis_sp", "?")
    cs4.metric("API Ham Sipariş", _ham,
               help=f"API'den toplam gelen: {_ham} sipariş | Tarih filtresi sonrası: {_fil} sipariş")

    st.markdown("---")

    # ── Günlük satış grafiği ──
    aktif_g = aktif.copy()
    aktif_g["gun"] = aktif_g["tarih"].dt.date
    gunluk = aktif_g.groupby("gun").agg(
        net_satis=("satis_fiyati", "sum"),
        net_kar=("net_kar", "sum"),
        adet=("adet", "sum")
    ).reset_index()

    fig = go.Figure()
    fig.add_trace(go.Bar(x=gunluk["gun"], y=gunluk["net_satis"], name="Net Satış", marker_color="#0066cc", opacity=0.8))
    fig.add_trace(go.Scatter(x=gunluk["gun"], y=gunluk["net_kar"], name="Net Kar", line=dict(color="#28a745", width=3)))
    fig.update_layout(title="Günlük Net Satış & Kar", height=320, hovermode="x unified", margin=dict(t=35))
    st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ── Ürün/Marka/Kategori tablosu ──
    st.markdown("#### Ürün Bazlı Analiz")

    urun_tablo = aktif_g.groupby(["barkod", "urun_adi", "marka", "kategori"]).agg(
        adet=("adet", "sum"),
        satis_fiyati=("satis_fiyati", "sum"),
        komisyon=("komisyon", "sum"),
        net_odeme=("net_odeme", "sum"),
        toplam_maliyet=("toplam_maliyet", "sum"),
        net_kar=("net_kar", "sum"),
    ).reset_index().sort_values("net_kar", ascending=False)

    maliyet_girilmemis = (urun_tablo["toplam_maliyet"] == 0).sum()
    if maliyet_girilmemis > 0:
        st.warning(f"⚠️ {maliyet_girilmemis} ürünün maliyeti girilmemiş — **Ürün Maliyetleri** sayfasından doldur.")

    goster = urun_tablo.copy()
    goster.columns = ["Barkod", "Ürün Adı", "Marka", "Kategori", "Adet",
                      "Net Satış", "Komisyon", "Trendyol Öd.", "Maliyet", "Net Kar"]

    def renk_kar(val):
        try:
            return "color: #28a745; font-weight:bold" if float(val) > 0 else "color: #dc3545; font-weight:bold"
        except Exception:
            return ""

    st.dataframe(
        goster.style.format({
            "Net Satış":     "₺{:,.2f}",
            "Komisyon":      "₺{:,.2f}",
            "Trendyol Öd.":  "₺{:,.2f}",
            "Maliyet":       "₺{:,.2f}",
            "Net Kar":       "₺{:,.2f}",
        }).map(renk_kar, subset=["Net Kar"]),
        use_container_width=True, height=420
    )

    # ── Marka / Kategori grafikleri ──
    col_a, col_b = st.columns(2)
    with col_a:
        marka_g = urun_tablo.groupby("marka")["net_kar"].sum().reset_index()
        marka_g = marka_g[marka_g["marka"] != ""]
        if not marka_g.empty:
            fig_m = px.pie(marka_g, values="net_kar", names="marka", title="Markaya Göre Net Kar")
            st.plotly_chart(fig_m, use_container_width=True)
    with col_b:
        kat_g = urun_tablo.groupby("kategori")["satis_fiyati"].sum().reset_index()
        kat_g = kat_g[kat_g["kategori"] != ""]
        if not kat_g.empty:
            fig_k = px.bar(kat_g, x="kategori", y="satis_fiyati", title="Kategoriye Göre Satış", color="satis_fiyati", color_continuous_scale="Blues")
            fig_k.update_layout(showlegend=False, height=300)
            st.plotly_chart(fig_k, use_container_width=True)


# ════════════════════════════════════════════════════════════════
# SİPARİŞLER
# ════════════════════════════════════════════════════════════════
elif sayfa == "📦 Siparişler":
    st.title("📦 Siparişler")

    if not st.session_state.yuklendi:
        st.info("Sol taraftan tarih seçip **Veri Çek** butonuna bas.")
        st.stop()

    df = hesapla_kar(st.session_state.df)

    # Durum sütununu Türkçeleştir
    df["durum_tr"] = df["durum"].apply(durum_tr)

    col_f1, col_f2 = st.columns([2, 3])
    with col_f1:
        durum_secenekler_tr = sorted(df["durum_tr"].unique().tolist())
        durum_filtre_tr = st.multiselect("Durum Filtrele", durum_secenekler_tr, default=durum_secenekler_tr)
    with col_f2:
        arama = st.text_input("Sipariş No / Ürün Ara")

    filtreli = df[df["durum_tr"].isin(durum_filtre_tr)]
    if arama:
        filtreli = filtreli[
            filtreli["siparis_no"].astype(str).str.contains(arama, case=False) |
            filtreli["urun_adi"].str.contains(arama, case=False, na=False)
        ]

    st.caption(f"{filtreli['siparis_no'].nunique()} sipariş | {int(filtreli['adet'].sum())} ürün")

    goster = filtreli[[
        "tarih", "siparis_no", "durum_tr", "urun_adi", "marka", "kategori", "barkod",
        "adet", "liste_fiyati", "iskonto", "satis_fiyati",
        "komisyon_oran", "komisyon", "net_odeme",
        "maliyet_birim", "toplam_maliyet", "brut_kar"
    ]].copy()
    goster.columns = [
        "Tarih", "Sipariş No", "Durum", "Ürün Adı", "Marka", "Kategori", "Barkod",
        "Adet", "Liste Fiyatı", "İndirim", "Net Satış",
        "Kom.%", "Komisyon ₺", "Trendyol Öd.",
        "Birim Maliyet", "Toplam Maliyet", "Brüt Kar"
    ]

    st.dataframe(
        goster.style.format({
            "Liste Fiyatı":   "₺{:.2f}",
            "İndirim":        "₺{:.2f}",
            "Net Satış":      "₺{:.2f}",
            "Kom.%":          "%{:.1f}",
            "Komisyon ₺":     "₺{:.2f}",
            "Trendyol Öd.":   "₺{:.2f}",
            "Birim Maliyet":  "₺{:.2f}",
            "Toplam Maliyet": "₺{:.2f}",
            "Brüt Kar":       "₺{:.2f}",
        }),
        use_container_width=True, height=520
    )

    csv = goster.to_csv(index=False, encoding="utf-8-sig")
    st.download_button("📥 CSV İndir", data=csv,
                       file_name=f"siparisler_{st.session_state.baslangic}_{st.session_state.bitis}.csv",
                       mime="text/csv")


# ════════════════════════════════════════════════════════════════
# ÜRÜN MALİYETLERİ
# ════════════════════════════════════════════════════════════════
elif sayfa == "💰 Ürün Maliyetleri":
    st.title("💰 Ürün Maliyetleri")

    if not st.session_state.yuklendi:
        st.info("Sol taraftan tarih seçip **Veri Çek** butonuna bas — satılan ürünler otomatik gelecek.")
        st.stop()

    df = st.session_state.df
    aktif = aktif_df(df)

    # Bu dönemde satılan benzersiz ürünler
    satilan = aktif.groupby("barkod").agg(
        urun_adi=("urun_adi", "first"),
        kategori=("kategori", "first"),
        adet=("adet", "sum"),
        net_satis=("satis_fiyati", "sum")
    ).reset_index().sort_values("net_satis", ascending=False)

    maliyet_map = get_maliyet_map()
    marka_map   = get_marka_map()

    # ── Marka Listesi Yönetimi ──────────────────────────────────
    with st.expander("⚙️ Marka Listesini Düzenle", expanded=len(get_markalar()) == 0):
        st.caption("Buraya markalarını ekle (ör: GC, Apa, Colgate, Özel). Bir kez girince hep listede kalır.")
        c1, c2 = st.columns([4, 1])
        with c1:
            yeni_marka_input = st.text_input("Yeni marka adı", key="yeni_marka_ekle",
                                              placeholder="örn: GC, Apa, Colgate, TePe")
        with c2:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("➕ Ekle", key="marka_ekle_btn"):
                if yeni_marka_input.strip():
                    add_marka(yeni_marka_input.strip())
                    st.rerun()

        kayitli = get_markalar()
        if kayitli:
            st.markdown("**Kayıtlı markalar:**")
            cols = st.columns(6)
            for i, (mid, ad) in enumerate(kayitli):
                with cols[i % 6]:
                    if st.button(f"✕ {ad}", key=f"sil_marka_{mid}"):
                        delete_marka(mid)
                        st.rerun()
        else:
            st.info("Henüz marka eklenmedi. Yukarıdan ekleyebilirsin.")

    # Markalar: DB markalar tablosu + daha önce ürünlere atanmış markalar
    markalar_db  = [ad for _, ad in get_markalar()]
    markalar_urun = [v for v in marka_map.values() if v and v.strip()]
    mevcut_markalar = sorted(set(markalar_db + markalar_urun))
    marka_secenekler = ["— Seç —"] + mevcut_markalar

    st.markdown(f"**Bu dönemde {len(satilan)} farklı ürün satıldı.** Her ürün için marka seç ve maliyet gir.")
    st.markdown("---")

    with st.form("maliyet_form"):
        for _, row in satilan.iterrows():
            barkod         = row["barkod"]
            urun_adi       = row["urun_adi"]
            mevcut_maliyet = maliyet_map.get(barkod, 0.0)
            mevcut_marka   = marka_map.get(barkod, "")

            st.markdown(f"**{urun_adi[:80]}**")
            col1, col2, col3, col4, col5 = st.columns([3, 2, 2, 2, 1])
            with col1:
                st.caption(f"Barkod: {barkod} | Satılan: {int(row['adet'])} adet | Net Satış: ₺{row['net_satis']:,.2f}")
            with col2:
                # Listeden seç
                try:
                    idx = marka_secenekler.index(mevcut_marka) if mevcut_marka in marka_secenekler else 0
                except ValueError:
                    idx = 0
                st.selectbox("Marka (listeden seç)", marka_secenekler, index=idx, key=f"marka_sec_{barkod}")
            with col3:
                # Yeni marka yazılabilir — dolu ise listeden seçimi ezer
                st.text_input("Yeni marka (opsiyonel)", value="", key=f"marka_yeni_{barkod}",
                               placeholder="Yeni marka adı yaz")
            with col4:
                st.number_input("Maliyet (₺)", value=float(mevcut_maliyet),
                                min_value=0.0, step=0.5, format="%.2f", key=f"mal_{barkod}")
            with col5:
                st.markdown("<br>", unsafe_allow_html=True)
                st.caption(f"Kayıtlı:\n₺{mevcut_maliyet:.2f}")
            st.divider()

        if st.form_submit_button("💾 Tümünü Kaydet", type="primary", use_container_width=True):
            for _, row in satilan.iterrows():
                barkod   = row["barkod"]
                urun_adi = row["urun_adi"]
                yeni     = st.session_state.get(f"marka_yeni_{barkod}", "").strip()
                secim    = st.session_state.get(f"marka_sec_{barkod}", "— Seç —")
                marka    = yeni if yeni else ("" if secim == "— Seç —" else secim)
                maliyet  = st.session_state.get(f"mal_{barkod}", 0.0)
                save_maliyet(barkod, urun_adi, marka, maliyet)
            st.success("✅ Tüm maliyetler kaydedildi!")
            st.rerun()


# ════════════════════════════════════════════════════════════════
# GİDERLER
# ════════════════════════════════════════════════════════════════
elif sayfa == "📋 Giderler":
    st.title("📋 Giderler")
    st.caption("Tüm giderler aşağıda görünür. Dönem seçiliyse o döneme ait giderler gösterilir.")

    # ── Mevcut Giderler (her zaman görünür) ────────────────────
    giderler = get_giderler(
        str(st.session_state.baslangic) if st.session_state.baslangic else None,
        str(st.session_state.bitis) if st.session_state.bitis else None
    )

    if not giderler.empty:
        toplam_g = giderler["tutar"].sum()
        st.markdown(f"#### 📋 Kayıtlı Giderler — Toplam: **{para(toplam_g)}**")

        for _, row in giderler.iterrows():
            c1, c2, c3, c4, c5 = st.columns([1.5, 2, 4, 2, 1])
            c1.write(str(row["tarih"]))
            c2.write(f"**{row['kategori']}**")
            c3.write(row["aciklama"] or "—")
            c4.write(f"**{para(row['tutar'])}**")
            if c5.button("🗑️", key=f"sil_{row['id']}"):
                delete_gider(int(row["id"]))
                st.rerun()
        st.markdown("---")
    else:
        st.info("Henüz gider eklenmedi.")
        st.markdown("---")

    # ── Yeni Gider Ekle ────────────────────────────────────────
    st.markdown("#### ➕ Yeni Gider Ekle")
    c1, c2, c3, c4, c5 = st.columns([2, 2, 4, 2, 1])
    with c1:
        g_tarih    = st.date_input("Tarih", value=date.today(), label_visibility="collapsed", key="g_tarih")
    with c2:
        g_kategori = st.text_input("Kategori", placeholder="Reklam / Vergi / Kargo...", label_visibility="collapsed", key="g_kat")
    with c3:
        g_aciklama = st.text_input("Açıklama", placeholder="Detay (opsiyonel)", label_visibility="collapsed", key="g_acik")
    with c4:
        g_tutar    = st.number_input("₺", min_value=0.0, step=1.0, format="%.2f", label_visibility="collapsed", key="g_tutar")
    with c5:
        if st.button("➕", type="primary", key="g_ekle"):
            if g_tutar > 0 and g_kategori.strip():
                save_gider(str(g_tarih), g_kategori.strip(), g_aciklama.strip(), g_tutar)
                st.rerun()
            else:
                st.error("Kategori ve tutar zorunlu.")

    st.caption("Tarih | Kategori | Açıklama | Tutar | Ekle")
    st.markdown("---")

    # ── Kargo Hesaplayıcı ──────────────────────────────────────
    st.markdown("#### 🚚 Kargo Hesaplayıcı")
    if st.session_state.yuklendi:
        aktif_k = aktif_df(st.session_state.df)
        siparis_toplam = aktif_k.groupby("siparis_no")["satis_fiyati"].sum()
        n1 = int((siparis_toplam < 200).sum())
        n2 = int(((siparis_toplam >= 200) & (siparis_toplam < 300)).sum())
        n3 = int((siparis_toplam >= 300).sum())

        tk1, tk2, tk3 = st.columns(3)
        tk1.metric("200 ₺ altı", f"{n1} sipariş")
        tk2.metric("200 – 300 ₺", f"{n2} sipariş")
        tk3.metric("300 ₺ üzeri", f"{n3} sipariş")

        ck1, ck2, ck3 = st.columns(3)
        k1 = ck1.number_input("200 ₺ altı (₺/sipariş)", value=40.0, step=1.0, format="%.2f")
        k2 = ck2.number_input("200–300 ₺ (₺/sipariş)",  value=70.0, step=1.0, format="%.2f")
        k3 = ck3.number_input("300 ₺ üzeri (₺/sipariş)", value=94.0, step=1.0, format="%.2f")

        toplam_kargo   = n1*k1 + n2*k2 + n3*k3
        aciklama_kargo = f"<200₺:{n1}×{k1:.0f} + 200-300₺:{n2}×{k2:.0f} + >300₺:{n3}×{k3:.0f}"

        km1, km2 = st.columns([3, 1])
        km1.success(f"**Toplam Kargo: {para(toplam_kargo)}**  |  {aciklama_kargo}")
        with km2:
            if st.button("🚚 Gidere Ekle", type="primary", use_container_width=True):
                save_gider(str(st.session_state.bitis), "Kargo", aciklama_kargo, toplam_kargo)
                st.rerun()
    else:
        st.info("Kargo hesabı için önce veri çek.")


# ════════════════════════════════════════════════════════════════
# RAPOR
# ════════════════════════════════════════════════════════════════
elif sayfa == "📄 Rapor":
    st.title("📄 Rapor")

    if not st.session_state.yuklendi:
        st.info("Sol taraftan tarih seçip **Veri Çek** butonuna bas.")
        st.stop()

    df_raw  = st.session_state.df
    df      = hesapla_kar(df_raw)
    aktif   = aktif_df(df)
    giderler = get_giderler(str(st.session_state.baslangic), str(st.session_state.bitis))
    toplam_gider = giderler["tutar"].sum() if not giderler.empty else 0

    if not aktif.empty and aktif["net_odeme"].sum() > 0:
        aktif = aktif.copy()
        aktif["gider_payi"] = aktif["net_odeme"] / aktif["net_odeme"].sum() * toplam_gider
        aktif["net_kar"]    = aktif["brut_kar"] - aktif["gider_payi"]
    else:
        aktif = aktif.copy()
        aktif["gider_payi"] = 0
        aktif["net_kar"]    = aktif["brut_kar"]

    net_satis = aktif["satis_fiyati"].sum()

    ozet = {
        "brut_satis":  aktif["liste_fiyati"].sum(),
        "indirim":     aktif["iskonto"].sum(),
        "net_satis":   net_satis,
        "komisyon":    aktif["komisyon"].sum(),
        "net_odeme":   aktif["net_odeme"].sum(),
        "maliyet":     aktif["toplam_maliyet"].sum(),
        "gider":       toplam_gider,
        "net_kar":     aktif["net_kar"].sum(),
        "marj":        (aktif["net_kar"].sum() / net_satis * 100) if net_satis > 0 else 0,
        "siparis":     aktif["siparis_no"].nunique(),
        "adet":        int(aktif["adet"].sum()),
    }

    urun_tablo = aktif.groupby(["barkod", "urun_adi", "marka", "kategori"]).agg(
        adet=("adet", "sum"),
        satis_fiyati=("satis_fiyati", "sum"),
        komisyon=("komisyon", "sum"),
        net_odeme=("net_odeme", "sum"),
        toplam_maliyet=("toplam_maliyet", "sum"),
        net_kar=("net_kar", "sum"),
    ).reset_index().sort_values("net_kar", ascending=False)

    tarih_aralik = f"{st.session_state.baslangic.strftime('%d.%m.%Y')} – {st.session_state.bitis.strftime('%d.%m.%Y')}"

    net_kar      = ozet["net_kar"]
    marj         = ozet["marj"]
    kar_renk_hex = "#1a7f37" if net_kar >= 0 else "#c0392b"

    # Gider satırları HTML olarak oluştur
    gider_satirlari = ""
    if not giderler.empty:
        for _, g in giderler.iterrows():
            label = str(g["kategori"]) + (" — " + str(g["aciklama"]) if g["aciklama"] else "")
            gider_satirlari += (
                '<tr><td style="padding:6px 12px;color:#555;">↳ ' + label + '</td>'
                '<td style="padding:6px 12px;text-align:right;color:#c0392b;">- ' + para(g["tutar"]) + '</td></tr>'
            )

    html_rapor = (
        '<div style="font-family:Segoe UI,Arial,sans-serif;max-width:700px;margin:0 auto;'
        'border:1px solid #dde3ea;border-radius:12px;overflow:hidden;box-shadow:0 4px 20px rgba(0,0,0,0.08);">'

        # Başlık
        '<div style="background:linear-gradient(135deg,#1a3a5c,#2e6da4);padding:22px 28px;color:white;">'
        '<div style="font-size:11px;letter-spacing:2px;opacity:0.8;text-transform:uppercase;">Dentalpazar · Trendyol</div>'
        '<div style="font-size:22px;font-weight:700;margin-top:4px;">Satış &amp; Kar Raporu</div>'
        '<div style="font-size:13px;opacity:0.85;margin-top:2px;">' + tarih_aralik + ' &nbsp;|&nbsp; ' + str(ozet["siparis"]) + ' sipariş · ' + str(ozet["adet"]) + ' ürün</div>'
        '</div>'

        # Gelir bölümü
        '<div style="padding:20px 28px 0;">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:1.5px;color:#2e6da4;text-transform:uppercase;margin-bottom:8px;">Gelir Kalemleri</div>'
        '<table style="width:100%;border-collapse:collapse;">'
        '<tr style="background:#f4f8ff;"><td style="padding:7px 12px;color:#555;">Brüt Satış (liste fiyatı)</td><td style="padding:7px 12px;text-align:right;color:#333;font-weight:600;">' + para(ozet["brut_satis"]) + '</td></tr>'
        '<tr><td style="padding:7px 12px;color:#555;">(-) Satıcı İndirimleri</td><td style="padding:7px 12px;text-align:right;color:#c0392b;">- ' + para(ozet["indirim"]) + '</td></tr>'
        '<tr style="background:#f4f8ff;"><td style="padding:7px 12px;color:#1a3a5c;font-weight:600;">Net Satış (müşteri ödedi)</td><td style="padding:7px 12px;text-align:right;color:#1a3a5c;font-weight:700;">' + para(ozet["net_satis"]) + '</td></tr>'
        '<tr><td style="padding:7px 12px;color:#555;">(-) Trendyol Komisyonu</td><td style="padding:7px 12px;text-align:right;color:#c0392b;">- ' + para(ozet["komisyon"]) + '</td></tr>'
        '<tr style="background:#e8f5e9;border-top:2px solid #2e6da4;"><td style="padding:9px 12px;color:#1a3a5c;font-weight:700;">Trendyol Net Ödemesi</td><td style="padding:9px 12px;text-align:right;color:#1a7f37;font-weight:700;font-size:15px;">' + para(ozet["net_odeme"]) + '</td></tr>'
        '</table></div>'

        # Gider bölümü
        '<div style="padding:20px 28px 0;">'
        '<div style="font-size:11px;font-weight:700;letter-spacing:1.5px;color:#c0392b;text-transform:uppercase;margin-bottom:8px;">Gider Kalemleri</div>'
        '<table style="width:100%;border-collapse:collapse;">'
        '<tr style="background:#fff5f5;"><td style="padding:7px 12px;color:#555;">(-) Ürün Maliyetleri (toplam)</td><td style="padding:7px 12px;text-align:right;color:#c0392b;">- ' + para(ozet["maliyet"]) + '</td></tr>'
        + gider_satirlari +
        '<tr style="background:#fff5f5;border-top:1px solid #f0c0c0;"><td style="padding:8px 12px;color:#333;font-weight:600;">Toplam Giderler</td><td style="padding:8px 12px;text-align:right;color:#c0392b;font-weight:700;">- ' + para(ozet["gider"]) + '</td></tr>'
        '</table></div>'

        # Net Kar
        '<div style="margin:20px 28px;background:' + kar_renk_hex + ';border-radius:10px;padding:20px 24px;">'
        '<div style="color:rgba(255,255,255,0.8);font-size:11px;letter-spacing:2px;text-transform:uppercase;">Net Kar</div>'
        '<div style="color:white;font-size:36px;font-weight:800;letter-spacing:-1px;margin-top:4px;">' + para(net_kar) + '</div>'
        '<div style="color:rgba(255,255,255,0.85);font-size:13px;margin-top:4px;">Kar marjı (net satışa göre): %' + f'{marj:.1f}' + '</div>'
        '</div>'
        '</div>'
    )
    st.markdown(html_rapor, unsafe_allow_html=True)
    st.markdown("")

    # ── Ürün Döküm Tablosu ──
    st.markdown("#### 📦 Ürün Bazlı Döküm")
    ut = urun_tablo[["urun_adi", "marka", "kategori", "adet",
                      "satis_fiyati", "komisyon", "net_odeme",
                      "toplam_maliyet", "net_kar"]].copy()
    ut.columns = ["Ürün", "Marka", "Kategori", "Adet",
                  "Net Satış", "Komisyon", "Trendyol Öd.", "Maliyet", "Net Kar"]

    # Toplam satırı ekle
    toplam_satir = pd.DataFrame([{
        "Ürün": "TOPLAM", "Marka": "", "Kategori": "", "Adet": int(ut["Adet"].sum()),
        "Net Satış": ut["Net Satış"].sum(), "Komisyon": ut["Komisyon"].sum(),
        "Trendyol Öd.": ut["Trendyol Öd."].sum(),
        "Maliyet": ut["Maliyet"].sum(), "Net Kar": ut["Net Kar"].sum()
    }])
    ut = pd.concat([ut, toplam_satir], ignore_index=True)

    def renk_kar_r(val):
        try:
            f = float(val)
            if f > 0:  return "color: #28a745; font-weight:bold"
            elif f < 0: return "color: #dc3545; font-weight:bold"
        except Exception:
            pass
        return ""

    st.dataframe(
        ut.style.format({
            "Net Satış": "₺{:,.2f}", "Komisyon": "₺{:,.2f}",
            "Trendyol Öd.": "₺{:,.2f}", "Maliyet": "₺{:,.2f}", "Net Kar": "₺{:,.2f}"
        }).map(renk_kar_r, subset=["Net Kar"]),
        use_container_width=True, height=450
    )

    st.markdown("---")
    col_pdf1, col_pdf2 = st.columns(2)
    with col_pdf1:
        if st.button("📥 PDF Raporu Oluştur", type="primary", use_container_width=True):
            pdf_buf = pdf_olustur(
                ozet=ozet,
                urun_df=urun_tablo,
                gider_df=giderler if not giderler.empty else None,
                tarih_aralik=tarih_aralik,
                magaza=get_ayar("magaza_adi", "Dentalpazar"),
            )
            st.download_button(
                label="📄 PDF İndir",
                data=pdf_buf,
                file_name=f"dentalpazar_rapor_{st.session_state.baslangic}_{st.session_state.bitis}.pdf",
                mime="application/pdf",
                use_container_width=True
            )
    with col_pdf2:
        csv_r = ut.to_csv(index=False, encoding="utf-8-sig")
        st.download_button("📊 Excel'e Aktar (CSV)", data=csv_r,
                           file_name=f"rapor_{st.session_state.baslangic}_{st.session_state.bitis}.csv",
                           mime="text/csv", use_container_width=True)


# ════════════════════════════════════════════════════════════════
# PANEL KARŞILAŞTIR
# ════════════════════════════════════════════════════════════════
elif sayfa == "🔍 Panel Karşılaştır":
    st.title("🔍 Panel Karşılaştırma")
    st.markdown(
        "Trendyol panelinden indirdiğin **Satış Raporu Excel**'ini yükle. "
        "Uygulama verileriyle karşılaştırılır, adet ve TL farkları gösterilir."
    )

    if not st.session_state.yuklendi:
        st.warning("Önce sol taraftan tarih seçip **Veri Çek** butonuna bas.")
        st.stop()

    _bas = st.session_state.baslangic
    _bit = st.session_state.bitis
    st.info(
        f"📅 Uygulamada yüklü tarih: **{_bas.strftime('%d.%m.%Y')} – {_bit.strftime('%d.%m.%Y')}**  \n"
        f"Trendyol'dan da **aynı tarih aralığını** indirdiğinden emin ol, yoksa rakamlar tutmaz."
    )

    uploaded = st.file_uploader(
        "Trendyol Satış Raporu Excel (.xlsx)",
        type=["xlsx"],
        help="Panel → Raporlar → Satış Raporu → aynı tarih aralığını seçip indir"
    )

    if uploaded:
        import io, openpyxl, re

        # ── Excel oku ──────────────────────────────────────────
        wb = openpyxl.load_workbook(io.BytesIO(uploaded.read()))
        ws = wb.active
        excel_rows = []
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row[0] is None:
                continue
            excel_rows.append({
                "barkod":    str(row[0]).strip(),
                "urun_adi":  str(row[1] or "").strip(),
                "model":     str(row[2] or row[0]).strip(),
                "net_adet":  int(row[13] or 0),
                "net_ciro":  float(row[16] or 0),
            })

        if not excel_rows:
            st.error("Excel'den veri okunamadı — doğru dosyayı yüklediğinden emin ol.")
            st.stop()

        # ── App verisi — barkod bazlı grupla ──────────────────
        df_app = hesapla_kar(aktif_df(st.session_state.df))
        urun_app = df_app.groupby("barkod").agg(
            adet=("adet", "sum"),
            net_satis=("satis_fiyati", "sum"),
            urun_adi=("urun_adi", "first"),
        ).reset_index()
        app_by_barkod = {row["barkod"]: row for _, row in urun_app.iterrows()}

        # ── Eşleştir: Excel barkod → App barkod ───────────────
        satirlar = []
        for ev in sorted(excel_rows, key=lambda x: -x["net_ciro"]):
            barkod = ev["barkod"]
            av = app_by_barkod.get(barkod)
            if av is not None:
                fark_adet = ev["net_adet"] - int(av["adet"])
                fark_tl   = ev["net_ciro"] - av["net_satis"]
                satirlar.append({
                    "Barkod":     barkod,
                    "Ürün Adı":   ev["urun_adi"][:45],
                    "Panel Adet": ev["net_adet"],
                    "App Adet":   int(av["adet"]),
                    "Fark Adet":  fark_adet,
                    "Panel TL":   ev["net_ciro"],
                    "App TL":     round(av["net_satis"], 2),
                    "Fark TL":    round(fark_tl, 2),
                    "Durum":      "✅ Eşleşti" if fark_adet == 0 else ("⚠️ Eksik" if fark_adet > 0 else "➕ Fazla"),
                })
            else:
                satirlar.append({
                    "Barkod":     barkod,
                    "Ürün Adı":   ev["urun_adi"][:45],
                    "Panel Adet": ev["net_adet"],
                    "App Adet":   0,
                    "Fark Adet":  ev["net_adet"],
                    "Panel TL":   ev["net_ciro"],
                    "App TL":     0.0,
                    "Fark TL":    ev["net_ciro"],
                    "Durum":      "❌ API'den Gelmedi",
                })

        # App'ta olup Excel'de olmayan
        excel_barkodlar = {ev["barkod"] for ev in excel_rows}
        for _, av in urun_app.iterrows():
            if av["barkod"] not in excel_barkodlar:
                satirlar.append({
                    "Barkod":     av["barkod"],
                    "Ürün Adı":   str(av["urun_adi"])[:45],
                    "Panel Adet": 0,
                    "App Adet":   int(av["adet"]),
                    "Fark Adet":  -int(av["adet"]),
                    "Panel TL":   0.0,
                    "App TL":     round(av["net_satis"], 2),
                    "Fark TL":    -round(av["net_satis"], 2),
                    "Durum":      "🔄 Panel'de Yok",
                })

        # ── Ortalama kar marjı (maliyeti girilmiş ürünlerden) ─
        df_maliyetli = df_app[df_app["toplam_maliyet"] > 0]
        if not df_maliyetli.empty and df_maliyetli["satis_fiyati"].sum() > 0:
            ort_kar_oran = df_maliyetli["brut_kar"].sum() / df_maliyetli["satis_fiyati"].sum()
        else:
            ort_kar_oran = 0.0

        # Tabloya tahmini kar sütunu ekle
        def tahmini_kar(row):
            if row["Fark TL"] > 0:
                return round(row["Fark TL"] * ort_kar_oran, 2)
            return 0.0

        kar_df = pd.DataFrame(satirlar)
        kar_df["Tahmini Kar"] = kar_df.apply(tahmini_kar, axis=1)

        # ── Özet metrikler ─────────────────────────────────────
        toplam_panel_adet = sum(ev["net_adet"] for ev in excel_rows)
        toplam_app_adet   = int(df_app["adet"].sum())
        toplam_panel_tl   = sum(ev["net_ciro"] for ev in excel_rows)
        toplam_app_tl     = df_app["satis_fiyati"].sum()
        kayip_tl          = toplam_panel_tl - toplam_app_tl
        kayip_adet        = toplam_panel_adet - toplam_app_adet
        tahmini_kayip_kar = kar_df["Tahmini Kar"].sum()

        st.markdown("---")
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Panel Net Satış", para(toplam_panel_tl),
                  help=f"{toplam_panel_adet} adet")
        m2.metric("App Net Satış",   para(toplam_app_tl),
                  help=f"{toplam_app_adet} adet")
        m3.metric("Kayıp Satış",     para(kayip_tl),
                  delta=f"{kayip_adet:+d} adet",
                  delta_color="inverse" if kayip_tl > 0 else "normal")
        m4.metric("Ort. Kar Marjı",  f"%{ort_kar_oran*100:.1f}",
                  help="Maliyeti girilmiş ürünlerin brüt kar marjı")
        m5.metric("Tahmini Kayıp Kar", para(tahmini_kayip_kar),
                  help=f"Kayıp satış × %{ort_kar_oran*100:.1f} ort. marj",
                  delta_color="inverse")

        if ort_kar_oran == 0:
            st.warning("Ürün Maliyetleri sayfasına maliyet girersen kar tahmini hesaplanır.")

        st.markdown("---")

        # ── Tablo ──────────────────────────────────────────────
        def renk_durum(val):
            if val == "✅ Eşleşti":          return "background-color:#d4edda;color:#155724"
            if val == "❌ API'den Gelmedi":   return "background-color:#f8d7da;color:#721c24"
            if val == "⚠️ Eksik":            return "background-color:#fff3cd;color:#856404"
            if val == "➕ Fazla":            return "background-color:#cce5ff;color:#004085"
            if val == "🔄 Panel'de Yok":     return "background-color:#e2e3e5;color:#383d41"
            return ""

        def renk_fark_tl(val):
            try:
                f = float(val)
                if f > 0: return "color:#dc3545;font-weight:bold"
                if f < 0: return "color:#007bff;font-weight:bold"
            except Exception:
                pass
            return ""

        def renk_tahmini(val):
            try:
                if float(val) > 0: return "color:#856404;font-weight:bold"
            except Exception:
                pass
            return ""

        st.markdown("#### Ürün Bazlı Karşılaştırma")
        styled = (
            kar_df.style
            .format({"Panel TL":"₺{:,.2f}","App TL":"₺{:,.2f}",
                     "Fark TL":"₺{:,.2f}","Tahmini Kar":"₺{:,.2f}"})
            .map(renk_durum,    subset=["Durum"])
            .map(renk_fark_tl,  subset=["Fark TL"])
            .map(renk_tahmini,  subset=["Tahmini Kar"])
        )
        st.dataframe(styled, use_container_width=True, height=500)

        # ── Kayıp özeti ────────────────────────────────────────
        kayip_df = kar_df[kar_df["Fark TL"] > 0].sort_values("Fark TL", ascending=False)
        if not kayip_df.empty:
            st.markdown("---")
            st.markdown("#### ⚠️ Kayıp Satış Detayı")
            _urun_sayisi = len(df_maliyetli.groupby("barkod"))
            st.caption(
                f"Ort. kar marjı %{ort_kar_oran*100:.1f} uygulandı "
                f"({'maliyeti girilmiş ' + str(_urun_sayisi) + ' üründen hesaplandı' if ort_kar_oran > 0 else 'maliyet girilmedi'})"
            )
            for _, r in kayip_df.iterrows():
                birim = r["Panel TL"] / r["Panel Adet"] if r["Panel Adet"] > 0 else 0
                kar_str = f" → tahmini kar **₺{r['Tahmini Kar']:,.2f}**" if r["Tahmini Kar"] > 0 else ""
                st.markdown(
                    f"**{r['Barkod']}** — {r['Ürün Adı']}  \n"
                    f"{r['Fark Adet']} adet × ₺{birim:,.0f} = ₺{r['Fark TL']:,.2f} kayıp satış{kar_str}"
                )
            st.markdown("---")
            col_k1, col_k2 = st.columns(2)
            col_k1.metric("Toplam Kayıp Satış", para(kayip_df["Fark TL"].sum()))
            col_k2.metric("Toplam Tahmini Kayıp Kar", para(kayip_df["Tahmini Kar"].sum()),
                          help="Bu satışlar gelseydi tahmini elde edeceğin kar")

        # ── CSV indir ──────────────────────────────────────────
        csv_kar = kar_df.to_csv(index=False, encoding="utf-8-sig")
        st.download_button(
            "📥 Karşılaştırmayı İndir (CSV)",
            data=csv_kar,
            file_name=f"karsilastirma_{st.session_state.baslangic}_{st.session_state.bitis}.csv",
            mime="text/csv"
        )


# ════════════════════════════════════════════════════════════════
# AYARLAR
# ════════════════════════════════════════════════════════════════
elif sayfa == "⚙️ Ayarlar":
    st.title("⚙️ Ayarlar")

    st.subheader("🏪 Mağaza Bilgileri")
    with st.form("magaza_form"):
        magaza_adi = st.text_input("Mağaza Adı (sidebar'da görünür)",
                                    value=get_ayar("magaza_adi", "Dentalpazar"),
                                    placeholder="örn: Dentalpazar, Sağlık Mağazam...")
        if st.form_submit_button("💾 Kaydet", type="primary"):
            save_ayar("magaza_adi", magaza_adi.strip() or "Dentalpazar")
            st.success("Kaydedildi!")

    st.markdown("---")
    st.subheader("🔑 Trendyol API Bilgileri")

    with st.form("api_form"):
        sup_id     = st.text_input("Supplier ID", value=get_ayar("supplier_id"))
        api_key    = st.text_input("API Key",     value=get_ayar("api_key"),    type="password")
        api_secret = st.text_input("API Secret",  value=get_ayar("api_secret"), type="password")

        if st.form_submit_button("💾 Kaydet", type="primary"):
            save_ayar("supplier_id", sup_id.strip())
            save_ayar("api_key",     api_key.strip())
            save_ayar("api_secret",  api_secret.strip())
            st.success("Kaydedildi!")

    if api_hazir():
        st.success("✅ API yapılandırıldı.")
    else:
        st.warning("⚠️ API bilgileri eksik.")

    # ── API Chunk Debug ──────────────────────────────────────────
    debug_log = _tapi.chunk_debug_log
    if debug_log:
        st.markdown("---")
        with st.expander("🔍 Son Veri Çekimi — Chunk Detayı", expanded=False):
            st.caption("Her 7 günlük parça için API'den kaç sipariş alındı.")
            debug_df = pd.DataFrame(debug_log)
            debug_df.columns = ["Tarih Aralığı", "API'den Gelen", "Yeni Eklenen"]
            st.dataframe(debug_df, use_container_width=True)
            st.caption(f"Toplam benzersiz sipariş: {sum(r['yeni'] for r in debug_log)}")

    # ── Kullanıcı Yönetimi (sadece admin) ────────────────────────
    if st.session_state.get("oturum", {}).get("rol") == "admin":
        st.markdown("---")
        st.subheader("👥 Kullanıcı Yönetimi")
        st.caption("Sadece admin bu bölümü görebilir. Yeni kullanıcı oluşturabilir, mevcut hesapları yönetebilirsin.")

        # Mevcut kullanıcılar
        kullanicilar = tum_kullanicilar()
        if kullanicilar:
            st.markdown("**Kayıtlı Kullanıcılar**")
            for uid, uad, urol, uaktif, utarih in kullanicilar:
                c1, c2, c3, c4, c5 = st.columns([3, 2, 1.5, 1.5, 1.5])
                c1.write(f"**{uad}**")
                c2.write(f"{'👑 admin' if urol == 'admin' else '👤 kullanıcı'}")
                c3.write("✅ Aktif" if uaktif else "🔴 Pasif")
                # Admin kendini devre dışı bırakamaz
                _kendi = uid == st.session_state["oturum"]["id"]
                if not _kendi:
                    with c4:
                        _btn_lbl = "Pasife Al" if uaktif else "Aktif Et"
                        if st.button(_btn_lbl, key=f"akt_{uid}"):
                            aktif_degistir(uid, not uaktif)
                            st.rerun()
                    with c5:
                        if st.button("🗑️ Sil", key=f"sil_u_{uid}"):
                            kullanici_sil(uid)
                            st.rerun()
                else:
                    c4.caption("(sen)")

        st.markdown("---")
        st.markdown("**Yeni Kullanıcı Ekle**")
        with st.form("yeni_kullanici_form"):
            nk_ad  = st.text_input("Kullanıcı Adı")
            nk_s1  = st.text_input("Şifre", type="password")
            nk_s2  = st.text_input("Şifre (tekrar)", type="password")
            nk_rol = st.selectbox("Rol", ["kullanici", "admin"])
            if st.form_submit_button("➕ Kullanıcı Ekle", type="primary"):
                if not nk_ad.strip() or not nk_s1:
                    st.error("Kullanıcı adı ve şifre boş olamaz.")
                elif nk_s1 != nk_s2:
                    st.error("Şifreler eşleşmiyor.")
                elif kullanici_olustur(nk_ad.strip(), nk_s1, nk_rol):
                    st.success(f"✅ '{nk_ad}' kullanıcısı oluşturuldu.")
                    st.rerun()
                else:
                    st.error("Bu kullanıcı adı zaten alınmış.")

        st.markdown("---")
        st.markdown("**Şifre Değiştir**")
        with st.form("sifre_degistir_form"):
            _kullanicilar_liste = [(uid, uad) for uid, uad, *_ in tum_kullanicilar()]
            _secenekler = {uad: uid for uid, uad in _kullanicilar_liste}
            _secilen = st.selectbox("Kullanıcı Seç", list(_secenekler.keys()))
            sd_s1 = st.text_input("Yeni Şifre", type="password")
            sd_s2 = st.text_input("Yeni Şifre (tekrar)", type="password")
            if st.form_submit_button("🔑 Şifre Güncelle", type="primary"):
                if not sd_s1:
                    st.error("Şifre boş olamaz.")
                elif sd_s1 != sd_s2:
                    st.error("Şifreler eşleşmiyor.")
                else:
                    sifre_degistir(_secenekler[_secilen], sd_s1)
                    st.success(f"✅ '{_secilen}' şifresi güncellendi.")
