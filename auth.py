# -*- coding: utf-8 -*-
import hashlib
import os
from database import get_connection


def _hash(sifre: str, salt: str = None):
    if salt is None:
        salt = os.urandom(16).hex()
    ozet = hashlib.sha256((sifre + salt).encode("utf-8")).hexdigest()
    return ozet, salt


def giris_yap(kullanici_adi: str, sifre: str):
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, kullanici_adi, sifre_hash, salt, rol, aktif "
        "FROM kullanicilar WHERE kullanici_adi = %s",
        (kullanici_adi.strip(),)
    )
    row = c.fetchone()
    conn.close()
    if not row or not row[5]:
        return None
    ozet, _ = _hash(sifre, row[3])
    if ozet == row[2]:
        return {"id": row[0], "kullanici_adi": row[1], "rol": row[4]}
    return None


def kullanici_olustur(kullanici_adi: str, sifre: str, rol: str = "kullanici") -> bool:
    ozet, salt = _hash(sifre)
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            "INSERT INTO kullanicilar (kullanici_adi, sifre_hash, salt, rol, aktif) "
            "VALUES (%s, %s, %s, %s, 1)",
            (kullanici_adi.strip(), ozet, salt, rol)
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def sifre_degistir(kullanici_id: int, yeni_sifre: str) -> bool:
    ozet, salt = _hash(yeni_sifre)
    conn = get_connection()
    c = conn.cursor()
    try:
        c.execute(
            "UPDATE kullanicilar SET sifre_hash=%s, salt=%s WHERE id=%s",
            (ozet, salt, kullanici_id)
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        return False
    finally:
        conn.close()


def kullanici_sil(kullanici_id: int):
    conn = get_connection()
    c = conn.cursor()
    c.execute("DELETE FROM kullanicilar WHERE id = %s", (kullanici_id,))
    conn.commit()
    conn.close()


def aktif_degistir(kullanici_id: int, aktif: bool):
    conn = get_connection()
    c = conn.cursor()
    c.execute("UPDATE kullanicilar SET aktif = %s WHERE id = %s",
              (int(aktif), kullanici_id))
    conn.commit()
    conn.close()


def kullanici_sayisi() -> int:
    conn = get_connection()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM kullanicilar")
    n = c.fetchone()[0]
    conn.close()
    return n


def tum_kullanicilar():
    conn = get_connection()
    c = conn.cursor()
    c.execute(
        "SELECT id, kullanici_adi, rol, aktif, olusturma_tarihi "
        "FROM kullanicilar ORDER BY id"
    )
    rows = c.fetchall()
    conn.close()
    return rows
