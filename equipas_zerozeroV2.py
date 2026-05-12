import requests
from bs4 import BeautifulSoup
import time
import psycopg2
import os
import re

DATABASE_URL = os.environ.get("DATABASE_URL")

headers = {"User-Agent": "Mozilla/5.0"}
base = "https://www.zerozero.pt"

URL = "https://www.zerozero.pt/equipas/futebol-de-8/portugal?order=popular&page="


def extrair_pagina(page):
    url = URL + str(page)
    print(f"🔍 Página {page}")

    r = requests.get(url, headers=headers)

    if r.status_code != 200:
        return []

    soup = BeautifulSoup(r.text, "html.parser")

    equipas = []

    # ✅ método principal
    items = soup.select("div.zz-search-item.team")

    # 🔥 fallback para páginas avançadas (tipo >600)
    if not items:
        print("⚠️ fallback ativado")

        links = soup.find_all("a", href=True)

        novos = []
        for l in links:
            href = l.get("href", "")
            if "/equipa/" in href:
                novos.append(l)

        items = novos

    for item in items:

        # ✅ adaptação HTML normal vs fallback
        if hasattr(item, "select_one"):
            a = item.select_one("a.title")
        else:
            a = item

        if not a:
            continue

        nome = a.get_text(strip=True)
        href = a.get("href")

        if not href:
            continue

        nome = nome.strip()

        # ✅ separar clube + escalão corretamente
        match = re.search(r"(Jun\.[A-Z]\s*S\d+|Sub\d+|S\d+)", nome)

        if match:
            escalao = match.group(0)
            nome_clube = nome[:match.start()].strip()
        else:
            escalao = "A"
            nome_clube = nome

        partes = href.split("/")
        id_zz = partes[-1]

        if "?" in id_zz:
            id_zz = id_zz.split("?")[0]

        if not id_zz.isnumeric():
            continue

        equipas.append({
            "id_zerozero": id_zz,
            "nome": nome,
            "clube": nome_clube,
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
                e["clube"],
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

    # ✅ debug total linhas
    cur.execute("SELECT COUNT(*) FROM zerozero_equipa")
    total = cur.fetchone()[0]
    print("TOTAL LINHAS BD:", total)

    conn.commit()


def main():
    conn = psycopg2.connect(DATABASE_URL)

    page = 1
    MAX_PAGE = 6

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