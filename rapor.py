# -*- coding: utf-8 -*-
from fpdf import FPDF
from datetime import datetime
import io

TR_MAP = str.maketrans(
    "şğ\xfc\xf6\xe7ıŞĞ\xdc\xd6\xc7İ",
    "sguociSGUOCI"
)

def tr(text):
    result = (str(text)
              .translate(TR_MAP)
              .replace("–", "-")
              .replace("—", "-")
              .replace("'", "'")
              .replace("'", "'")
              .replace(""", '"')
              .replace(""", '"'))
    return result.encode("latin-1", errors="replace").decode("latin-1")

def _p(val):
    try:
        return "TL {:,.2f}".format(float(val))
    except Exception:
        return str(val)

NAVY  = (26,  58,  92)
BLUE  = (46, 109, 164)
GREEN = (27, 153,  86)
RED   = (192,  57,  43)
LGRAY = (218, 224, 232)
LIGHT = (246, 248, 251)
DARK  = ( 33,  37,  41)
GRAY  = (120, 130, 140)
WHITE = (255, 255, 255)


class Rapor(FPDF):
    def __init__(self, magaza, tarih, siparis, adet):
        super().__init__()
        self._magaza  = magaza
        self._tarih   = tarih
        self._siparis = siparis
        self._adet    = adet

    def header(self):
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 2.5, style="F")
        self.set_xy(10, 6)
        self.set_font("Helvetica", "B", 15)
        self.set_text_color(*NAVY)
        self.cell(130, 8, tr(self._magaza), align="L")
        self.set_xy(10, 15)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GRAY)
        self.cell(130, 5, "Trendyol Satis & Kar Raporu", align="L")
        self.set_xy(130, 6)
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(*NAVY)
        self.cell(70, 7, tr(self._tarih), align="R")
        self.set_xy(130, 14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*GRAY)
        self.cell(70, 5,
                  tr("{} siparis | {} urun".format(self._siparis, self._adet)),
                  align="R")
        self.set_draw_color(*LGRAY)
        self.set_line_width(0.3)
        self.line(10, 23, 200, 23)
        self.set_text_color(*DARK)

    def footer(self):
        # Ust cizgi
        self.set_y(-18)
        self.set_draw_color(*LGRAY)
        self.set_line_width(0.3)
        self.line(10, self.get_y(), 200, self.get_y())
        # Telif satiri
        self.set_xy(10, self.get_y() + 1.5)
        self.set_font("Helvetica", "B", 7)
        self.set_text_color(*NAVY)
        self.cell(0, 4.5,
                  tr("Trendyol Kar Takip Sistemi  |  Gelistiren: Taha Salman"),
                  align="C")
        self.ln(4.5)
        # Yasal uyari
        self.set_font("Helvetica", "I", 6)
        self.set_text_color(*GRAY)
        self.cell(0, 4,
                  tr("Bu rapor ozel yazilim ile uretilmistir. Izinsiz kopyalanmasi, dagitilmasi veya ticari amacla kullanilmasi kesinlikle yasaktir. (C) Taha Salman"),
                  align="C")
        self.ln(4)
        # Sayfa no
        self.set_draw_color(*LGRAY)
        self.set_line_width(0.2)
        self.line(10, self.get_y(), 200, self.get_y())
        self.set_xy(10, self.get_y() + 1)
        self.set_font("Helvetica", "", 6.5)
        self.set_text_color(*GRAY)
        self.cell(95, 4, tr(self._magaza + "  |  " + self._tarih), align="L")
        self.cell(0, 4,
                  "Sayfa {} | {}".format(self.page_no(), datetime.now().strftime("%d.%m.%Y %H:%M")),
                  align="R")
        self.set_text_color(*DARK)


def _net_kar_kutusu(pdf, net_kar, marj):
    """Sayfanin ustunde buyuk net kar kutusu."""
    renk = GREEN if net_kar >= 0 else RED
    x, y, w, h = 10, 28, 190, 46
    # Golge
    pdf.set_fill_color(190, 195, 200)
    pdf.rect(x + 1, y + 1, w, h, style="F")
    # Ana kutu
    pdf.set_fill_color(*renk)
    pdf.rect(x, y, w, h, style="F")
    # "NET KAR" etiketi
    pdf.set_xy(x, y + 7)
    pdf.set_font("Helvetica", "B", 10)
    pdf.set_text_color(210, 240, 210)
    pdf.cell(w, 6, "NET KAR", align="C")
    # Buyuk rakam
    pdf.set_xy(x, y + 14)
    pdf.set_font("Helvetica", "B", 32)
    pdf.set_text_color(*WHITE)
    pdf.cell(w, 18, tr(_p(net_kar)), align="C")
    # Marj
    pdf.set_xy(x, y + 33)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(210, 240, 210)
    pdf.cell(w, 6, tr("Kar Marji: %{:.1f}   |   Net satisa gore".format(marj)), align="C")
    pdf.set_text_color(*DARK)


def _pl_satir(pdf, label, deger, cizgi=False, kalin=False, gri=False, renk=None, indent=0):
    """Gelir tablosu satiri."""
    pdf.set_fill_color(*(LIGHT if gri else WHITE))
    h = 8 if kalin else 7
    pdf.rect(pdf.l_margin, pdf.get_y(), pdf.epw, h, style="F")
    pdf.set_x(pdf.l_margin + 3 + indent)
    pdf.set_font("Helvetica", "B" if kalin else "", 9 if kalin else 8.5)
    pdf.set_text_color(*DARK)
    pdf.cell(pdf.epw - 55 - indent, h, tr(label), align="L")
    if renk:
        pdf.set_text_color(*renk)
    elif kalin:
        pdf.set_text_color(*NAVY)
    pdf.set_font("Helvetica", "B" if kalin else "", 9 if kalin else 8.5)
    pdf.cell(50, h, tr(str(deger)), align="R")
    pdf.ln()
    if cizgi:
        pdf.set_draw_color(*LGRAY)
        pdf.set_line_width(0.25)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.set_text_color(*DARK)


def _kalin_cizgi(pdf):
    pdf.set_draw_color(*NAVY)
    pdf.set_line_width(0.5)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.set_line_width(0.2)
    pdf.ln(1)


def _ince_cizgi(pdf):
    pdf.set_draw_color(*LGRAY)
    pdf.set_line_width(0.25)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2)


def _tablo_baslik(pdf, kolonlar, genislikler):
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(*WHITE)
    for k, g in zip(kolonlar, genislikler):
        pdf.cell(g, 7, "  " + tr(k), fill=True, border=0)
    pdf.ln()
    pdf.set_text_color(*DARK)


def _tablo_satir(pdf, degerler, genislikler, gri=False):
    pdf.set_font("Helvetica", "", 8)
    pdf.set_fill_color(*(LIGHT if gri else WHITE))
    for d, g in zip(degerler, genislikler):
        pdf.cell(g, 6.5, "  " + tr(str(d)), fill=True, border=0)
    pdf.ln()
    pdf.set_draw_color(*LGRAY)
    pdf.set_line_width(0.15)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())


def _tablo_toplam(pdf, degerler, genislikler):
    pdf.set_font("Helvetica", "B", 8)
    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(*WHITE)
    for d, g in zip(degerler, genislikler):
        pdf.cell(g, 7, "  " + tr(str(d)), fill=True, border=0)
    pdf.ln()
    pdf.set_text_color(*DARK)


def _bolum_baslik(pdf, metin):
    pdf.ln(4)
    pdf.set_font("Helvetica", "B", 9)
    pdf.set_fill_color(*NAVY)
    pdf.set_text_color(*WHITE)
    pdf.cell(0, 7, "   " + tr(metin.upper()), fill=True, new_x="LMARGIN", new_y="NEXT")
    pdf.set_fill_color(46, 109, 164)
    pdf.rect(pdf.l_margin, pdf.get_y(), pdf.epw, 1, style="F")
    pdf.ln(3)
    pdf.set_text_color(*DARK)


# ─────────────────────────────────────────────────────────────────────────────

def pdf_olustur(ozet, urun_df, gider_df, tarih_aralik, kargo_bilgi=None, magaza="Dentalpazar"):
    net_kar = ozet.get("net_kar", 0)
    marj    = ozet.get("marj", 0)

    pdf = Rapor(
        magaza=magaza,
        tarih=tarih_aralik,
        siparis=ozet.get("siparis", 0),
        adet=ozet.get("adet", 0),
    )
    pdf.set_margins(10, 28, 10)
    pdf.set_auto_page_break(auto=True, margin=22)

    # ════════════════════════════════════════════════
    # SAYFA 1 — Kapak / Ozet
    # ════════════════════════════════════════════════
    pdf.add_page()

    # Buyuk net kar kutusu
    _net_kar_kutusu(pdf, net_kar, marj)
    pdf.set_y(82)

    # Gelir tablosu (P&L)
    _ince_cizgi(pdf)
    _pl_satir(pdf, "Brut Satis  (liste fiyati)",    _p(ozet.get("brut_satis", 0)), gri=True,  cizgi=True)
    _pl_satir(pdf, "(-) Satici Indirimleri",         "- " + _p(ozet.get("indirim", 0)), cizgi=True)
    _pl_satir(pdf, "Net Satis  (musteri odedi)",     _p(ozet.get("net_satis", 0)),  gri=True,  kalin=True, cizgi=True)
    pdf.ln(1)
    _pl_satir(pdf, "(-) Trendyol Komisyonu",         "- " + _p(ozet.get("komisyon", 0)), cizgi=True)
    _pl_satir(pdf, "Trendyol Net Odemesi",           _p(ozet.get("net_odeme", 0)),  gri=True,  kalin=True, cizgi=True)
    pdf.ln(1)
    _pl_satir(pdf, "(-) Urun Maliyetleri",           "- " + _p(ozet.get("maliyet", 0)), cizgi=True)
    _pl_satir(pdf, "(-) Diger Giderler",             "- " + _p(ozet.get("gider", 0)),   gri=True, cizgi=True)
    if kargo_bilgi:
        _pl_satir(pdf, "(-) Kargo Gideri",           "- " + _p(kargo_bilgi.get("toplam", 0)), cizgi=True)
    _kalin_cizgi(pdf)
    kar_renk = GREEN if net_kar >= 0 else RED
    _pl_satir(pdf, "NET KAR", _p(net_kar), kalin=True, gri=True, renk=kar_renk)
    _pl_satir(pdf, "Kar Marji", "%{:.1f}  (net satisa gore)".format(marj), cizgi=True)
    pdf.ln(3)
    _ince_cizgi(pdf)

    # Istatistik satiri
    pdf.ln(2)
    pdf.set_font("Helvetica", "", 8.5)
    pdf.set_text_color(*GRAY)
    istatlar = [
        ("Aktif Siparis", str(ozet.get("siparis", 0))),
        ("Satilan Urun",  str(ozet.get("adet", 0))),
        ("Net Satis",     _p(ozet.get("net_satis", 0))),
        ("Net Odeme",     _p(ozet.get("net_odeme", 0))),
    ]
    col = 190 / len(istatlar)
    for lbl, val in istatlar:
        pdf.set_font("Helvetica", "",  7.5)
        pdf.set_text_color(*GRAY)
        pdf.cell(col / 2, 6, tr(lbl + ":"), align="R")
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(*NAVY)
        pdf.cell(col / 2, 6, tr(val), align="L")
    pdf.set_text_color(*DARK)

    # ════════════════════════════════════════════════
    # SAYFA 2+ — Urun Dokumu (ekstre tarzi)
    # ════════════════════════════════════════════════
    if urun_df is not None and not urun_df.empty:
        pdf.add_page()
        _bolum_baslik(pdf, "Urun Bazli Dokum  —  {} kalem".format(len(urun_df)))

        kolonlar    = ["Urun Adi", "Barkod", "Marka", "Kategori",
                       "Adet", "Birim Satis", "Net Satis",
                       "Komisyon", "Net Odeme", "Maliyet", "Kar"]
        genislikler = [42, 22, 16, 18, 10, 18, 18, 17, 19, 15, 15]
        _tablo_baslik(pdf, kolonlar, genislikler)

        for i, row in urun_df.sort_values("net_kar", ascending=False).iterrows():
            adet       = int(row.get("adet", 0))
            net_satis  = row.get("satis_fiyati", 0)
            birim      = net_satis / adet if adet else 0
            _tablo_satir(pdf, [
                str(row.get("urun_adi",  ""))[:22],
                str(row.get("barkod",    ""))[:14],
                str(row.get("marka",     ""))[:8],
                str(row.get("kategori",  ""))[:10],
                str(adet),
                "{:,.2f}".format(birim),
                "{:,.2f}".format(net_satis),
                "{:,.2f}".format(row.get("komisyon",       0)),
                "{:,.2f}".format(row.get("net_odeme",      0)),
                "{:,.2f}".format(row.get("toplam_maliyet", 0)),
                "{:,.2f}".format(row.get("net_kar",        0)),
            ], genislikler, gri=(i % 2 == 0))

        _tablo_toplam(pdf, [
            "TOPLAM ({} kalem)".format(len(urun_df)),
            "", "", "",
            str(int(urun_df["adet"].sum())),
            "",
            "{:,.2f}".format(urun_df["satis_fiyati"].sum()),
            "{:,.2f}".format(urun_df["komisyon"].sum()),
            "{:,.2f}".format(urun_df["net_odeme"].sum()),
            "{:,.2f}".format(urun_df["toplam_maliyet"].sum()),
            "{:,.2f}".format(urun_df["net_kar"].sum()),
        ], genislikler)

    # ════════════════════════════════════════════════
    # Giderler (ayni sayfada yer yoksa yeni sayfa)
    # ════════════════════════════════════════════════
    if gider_df is not None and not gider_df.empty:
        if pdf.get_y() > 220:
            pdf.add_page()
        _bolum_baslik(pdf, "Gider Detayi")
        kolonlar    = ["Tarih", "Kategori", "Aciklama", "Tutar TL"]
        genislikler = [28, 35, 97, 30]
        _tablo_baslik(pdf, kolonlar, genislikler)
        for i, row in gider_df.iterrows():
            _tablo_satir(pdf, [
                str(row.get("tarih",    "")),
                str(row.get("kategori", "")),
                str(row.get("aciklama", ""))[:52],
                "{:,.2f}".format(row.get("tutar", 0)),
            ], genislikler, gri=(i % 2 == 0))
        _tablo_toplam(pdf,
            ["TOPLAM GIDER", "", "", "{:,.2f}".format(gider_df["tutar"].sum())],
            genislikler)

    buf = io.BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf
