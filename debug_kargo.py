# python debug_kargo.py
import requests
import json
from base64 import b64encode
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

BASE = "https://api.trendyol.com/sapigw"

endpoints = [
    f"/suppliers/{supplier_id}/settlements",
    f"/suppliers/{supplier_id}/finance/settlements",
    f"/suppliers/{supplier_id}/finance/iban",
    f"/suppliers/{supplier_id}/packages?status=Shipped&page=0&size=3",
]

for ep in endpoints:
    url = BASE + ep
    try:
        r = requests.get(url, headers=headers, timeout=15)
        print(f"\n{'='*60}")
        print(f"URL: {ep}")
        print(f"Status: {r.status_code}")
        if r.status_code == 200:
            data = r.json()
            print(json.dumps(data, ensure_ascii=False, indent=2)[:600])
        else:
            print(r.text[:300])
    except Exception as e:
        print(f"HATA: {e}")
