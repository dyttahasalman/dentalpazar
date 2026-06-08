# -*- coding: utf-8 -*-
"""
Supabase (PostgreSQL) veritabani katmani.
Kurulum sonrasi bu dosyayi database.py ile degistir.
"""
import os
import psycopg2
import psycopg2.extras
import pandas as pd
from datetime import datetime
import streamlit as st

# Streamlit Cloud'da st.secrets, lokalde environment variable
def _get_dsn():
    try:
        import streamlit as st
        return st.secrets["DATABASE_URL"]
    except Exception:
        return os.environ.get("DATABASE_URL", "")


@st.cache_resource
def _get_pool():
    """Uygulama basina tek sefer baglanti olustur, yeniden kullan."""
    import streamlit as st
    dsn = _get_dsn()
    conn = psycopg2.connect(dsn, sslmode="require")
    conn.autocommit = False
    return conn


def get_connection():
    """Pooled baglanti doner; kopuksa yeniden baglanir."""
    import streamlit as st
    conn = _get_pool()
    try:
        conn.cursor().execute("SELECT 1")
    except Exception:
        st.cache_resource.clear()
        conn = _get_pool()
    return conn


def init_db():
    conn = get_connection()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS urun_maliyetleri (
            barkod TEXT PRIMARY KEY,
            urun_adi TEXT,
            marka TEXT DEFAULT '',
            maliyet REAL DEFAULT 0,
            guncelleme TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS giderler (
            id SERIAL PRIMARY KEY,
            tarih TEXT,
            kategori TEXT,
            aciklama TEXT,
            tutar REAL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS ayarlar (
            anahtar TEXT PRIMARY KEY,
            deger TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS markalar (
            id SERIAL PRIMARY KEY,
            ad TEXT UNIQUE
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS kullanicilar (
            id SERIAL PRIMARY KEY,
            kullanici_adi TEXT UNIQUE NOT NULL,
            sifre_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            rol TEXT DEFAULT 'kullanici',
            aktif INTEGER DEFAULT 1,
            olusturma_tarihi TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# ── Ürün Maliyetleri ─────────────────────────────────────────────

def get_maliyetler():
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM urun_maliyetleri ORDER BY urun_adi", conn)
    conn.close()
    return df


@st.cache_data(ttl=300)
def get_maliyet_map():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT barkod, maliyet FROM urun_maliyetleri")
    rows = c.fetchall()
    return {r[0]: r[1] for r in rows}


@st.cache_data(ttl=300)
def get_marka_map():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT barkod, marka FROM urun_maliyetleri")
    rows = c.fetchall()
    return {r[0]: r[1] for r in rows}


def save_maliyet(barkod, urun_adi, marka, maliyet):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO urun_maliyetleri (barkod, urun_adi, marka, maliyet, guncelleme)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (barkod) DO UPDATE SET
            urun_adi   = EXCLUDED.urun_adi,
            marka      = EXCLUDED.marka,
            maliyet    = EXCLUDED.maliyet,
            guncelleme = EXCLUDED.guncelleme
    """, (barkod, urun_adi, marka, maliyet, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    get_maliyet_map.clear()
    get_marka_map.clear()


# ── Markalar ─────────────────────────────────────────────────────

def get_markalar():
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT id, ad FROM markalar ORDER BY ad")
    rows = c.fetchall()
    conn.close()
    return rows


def add_marka(ad):
    ad = ad.strip()
    if not ad:
        return
    conn = get_connection()
    c = conn.cursor()
    c.execute("INSERT INTO markalar (ad) VALUES (%s) ON CONFLICT (ad) DO NOTHING", (ad,))
    conn.commit()
    conn.close()


def delete_marka(marka_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM markalar WHERE id = %s", (marka_id,))
    conn.commit()
    conn.close()


# ── Giderler ─────────────────────────────────────────────────────

def get_giderler(baslangic=None, bitis=None):
    conn = get_connection()
    if baslangic and bitis:
        df = pd.read_sql(
            "SELECT * FROM giderler WHERE tarih BETWEEN %s AND %s ORDER BY tarih DESC",
            conn, params=(baslangic, bitis)
        )
    else:
        df = pd.read_sql("SELECT * FROM giderler ORDER BY tarih DESC", conn)
    conn.close()
    return df


def save_gider(tarih, kategori, aciklama, tutar):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "INSERT INTO giderler (tarih, kategori, aciklama, tutar) VALUES (%s, %s, %s, %s)",
        (str(tarih), kategori, aciklama, tutar)
    )
    conn.commit()
    conn.close()


def delete_gider(gider_id):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM giderler WHERE id = %s", (gider_id,))
    conn.commit()
    conn.close()


# ── Ayarlar ──────────────────────────────────────────────────────

@st.cache_data(ttl=600)
def get_ayar(anahtar, varsayilan=""):
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT deger FROM ayarlar WHERE anahtar = %s", (anahtar,))
    row = c.fetchone()
    return row[0] if row else varsayilan


def save_ayar(anahtar, deger):
    conn = get_connection()
    c = conn.cursor()
    c.execute("""
        INSERT INTO ayarlar (anahtar, deger) VALUES (%s, %s)
        ON CONFLICT (anahtar) DO UPDATE SET deger = EXCLUDED.deger
    """, (anahtar, deger))
    conn.commit()
    get_ayar.clear()
