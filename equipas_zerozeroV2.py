import requests
from bs4 import BeautifulSoup
import time
import psycopg2
import os

DATABASE_URL = os.environ.get("DATABASE_URL")

headers = {"User-Agent": "Mozilla/5.0"}
base = "https://www.zerozero.pt"

URL = "https://www.zerozero.pt/equipas/futebol/portugal?order=popular&type_id=0&page="


def extrair_pagina(page):
    url = URL + str(page)
    print(f"🔍 Página {page}")

    r = requests.get(url, headers=headers)

    if r.status_code != 200:
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    equipas = []

    items = soup.select("div.zz-search-item.team")

    for item in items:
        a = item.select_one("a.title")

        if not a:
            continue

        nome = a.get_text(strip=True)
        href = a.get("href")

        if not href:
            continue

        nome = nome.strip()

        # ✅ ESCALÃO
        if any(x in nome for x in ["Jun.", "Sub"]):
            escalao = nome
        else:
            escalao = "A"

        # ✅ ID ZEROZERO
        partes = href.split("/")
        id_zz = partes[-1]

        if "?" in id_zz:
            id_zz = id_zz.split("?")[0]

        if not id_zz.isnumeric():
            continue

        equipas.append({
            "id_zerozero": id_zz,
            "nome": nome,
            "escalao": escalao,
            "url": base + href
        })

    return equipas


def guardar_bd(conn, equipas):
    cur = conn.cursor()

    for e in equipas:
        try:
            cur.execute("""
                INSERT INTO zerozero_equipa
                (id_zerozero_equipa, nome_equipa, clube, escalao, url_zerozero)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (id_zerozero_equipa) DO NOTHING
            """, (
                e["id_zerozero"],
                e["nome"],
                e["nome"],     # clube simplificado (por agora)
                e["escalao"],
                e["url"]
            ))

            if cur.rowcount > 0:
                print("✅ inserido:", e["nome"])
            else:
                print("⚠️ já existia:", e["nome"])

        except Exception as ex:
            print("❌ erro BD:", ex)
            conn.rollback()

    # ✅ DEBUG FINAL CORRETO (aqui faz sentido)
    cur.execute("SELECT COUNT(*) FROM zerozero_equipa")
    print("TOTAL LINHAS BD:", cur.fetchone())

    conn.commit()


def main():
    conn = psycopg2.connect(DATABASE_URL)

    page = 1

    MAX_PAGE = 1181

    while page <= MAX_PAGE:
        equipas = extrair_pagina(page)

        print(f"✅ {len(equipas)} encontrados")

        if equipas:
            guardar_bd(conn, equipas)
        else:
            print("⚠️ página sem dados")

        page += 1
        time.sleep(1)

    print("✅ scraping completo")

    conn.close()


if __name__ == "__main__":
    main()