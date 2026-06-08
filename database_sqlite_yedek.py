import sqlite3
import pandas as pd
from datetime import datetime

DB_PATH = "dentalpazar.db"


def get_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


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
    # marka kolonu yoksa ekle (eski DB için)
    try:
        c.execute("ALTER TABLE urun_maliyetleri ADD COLUMN marka TEXT DEFAULT ''")
    except Exception:
        pass

    c.execute("""
        CREATE TABLE IF NOT EXISTS giderler (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ad TEXT UNIQUE
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS kullanicilar (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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


def get_maliyet_map():
    conn = get_connection()
    rows = conn.execute("SELECT barkod, maliyet FROM urun_maliyetleri").fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


def get_marka_map():
    conn = get_connection()
    rows = conn.execute("SELECT barkod, marka FROM urun_maliyetleri").fetchall()
    conn.close()
    return {r[0]: r[1] for r in rows}


def save_maliyet(barkod, urun_adi, marka, maliyet):
    conn = get_connection()
    conn.execute("""
        INSERT INTO urun_maliyetleri (barkod, urun_adi, marka, maliyet, guncelleme)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(barkod) DO UPDATE SET
            urun_adi=excluded.urun_adi,
            marka=excluded.marka,
            maliyet=excluded.maliyet,
            guncelleme=excluded.guncelleme
    """, (barkod, urun_adi, marka, maliyet, datetime.now().strftime("%Y-%m-%d %H:%M")))
    conn.commit()
    conn.close()


# ── Markalar ─────────────────────────────────────────────────────

def get_markalar():
    conn = get_connection()
    rows = conn.execute("SELECT id, ad FROM markalar ORDER BY ad").fetchall()
    conn.close()
    return rows  # [(id, ad), ...]


def add_marka(ad):
    ad = ad.strip()
    if not ad:
        return
    conn = get_connection()
    conn.execute("INSERT OR IGNORE INTO markalar (ad) VALUES (?)", (ad,))
    conn.commit()
    conn.close()


def delete_marka(marka_id):
    conn = get_connection()
    conn.execute("DELETE FROM markalar WHERE id=?", (marka_id,))
    conn.commit()
    conn.close()


# ── Giderler ─────────────────────────────────────────────────────

def get_giderler(baslangic=None, bitis=None):
    conn = get_connection()
    query = "SELECT * FROM giderler"
    params = []
    if baslangic and bitis:
        query += " WHERE tarih BETWEEN ? AND ?"
        params = [baslangic, bitis]
    query += " ORDER BY tarih DESC"
    df = pd.read_sql(query, conn, params=params)
    conn.close()
    return df


def save_gider(tarih, kategori, aciklama, tutar):
    conn = get_connection()
    conn.execute("""
        INSERT INTO giderler (tarih, kategori, aciklama, tutar)
        VALUES (?, ?, ?, ?)
    """, (str(tarih), kategori, aciklama, tutar))
    conn.commit()
    conn.close()


def delete_gider(gider_id):
    conn = get_connection()
    conn.execute("DELETE FROM giderler WHERE id=?", (gider_id,))
    conn.commit()
    conn.close()


# ── Ayarlar ──────────────────────────────────────────────────────

def get_ayar(anahtar, varsayilan=""):
    conn = get_connection()
    row = conn.execute("SELECT deger FROM ayarlar WHERE anahtar=?", (anahtar,)).fetchone()
    conn.close()
    return row[0] if row else varsayilan


def save_ayar(anahtar, deger):
    conn = get_connection()
    conn.execute("""
        INSERT INTO ayarlar (anahtar, deger) VALUES (?, ?)
        ON CONFLICT(anahtar) DO UPDATE SET deger=excluded.deger
    """, (anahtar, deger))
    conn.commit()
    conn.close()
