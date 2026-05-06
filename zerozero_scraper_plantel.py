# -*- coding: utf-8 -*-

import os
import re
import time
import psycopg2
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager

# ======================================================
# CONFIGURAÇÃO
# ======================================================

DATABASE_URL = os.environ["DATABASE_URL"]
BASE_ZEROZERO = "https://www.zerozero.pt"

FIREFOX_BINARY = r"C:\Users\augusto.roxo\AppData\Local\Mozilla Firefox\firefox.exe"

WAIT_TIMEOUT = 20
DELAY = 1.0

# ======================================================
# BD
# ======================================================

def obter_equipas(conn, limite=None):
    cur = conn.cursor()
    sql = """
        SELECT
            id_zerozero_equipa,
            nome_equipa,
            clube,
            escalao,
            url_zerozero
        FROM zerozero_equipa
        ORDER BY id_zerozero_equipa
    """
    if limite:
        sql += " LIMIT %s"
        cur.execute(sql, (limite,))
    else:
        cur.execute(sql)

    return cur.fetchall()

def inserir_atleta(conn, atleta):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO zerozero_atleta (
            id_zerozero_atleta,
            nome_completo,
            url_zerozero
        )
        VALUES (%s,%s,%s)
        ON CONFLICT (id_zerozero_atleta) DO UPDATE SET
            nome_completo = EXCLUDED.nome_completo
    """, (
        atleta["id"],
        atleta["nome"],
        atleta["url"]
    ))

def inserir_plantel(conn, ligacao):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO zerozero_plantel (
            id_zerozero_equipa,
            id_zerozero_atleta,
            nome_atleta,
            clube,
            escalao,
            origem,
            confianca_origem
        )
        VALUES (%s,%s,%s,%s,%s,'plantel',100)
        ON CONFLICT (id_zerozero_equipa, id_zerozero_atleta) DO NOTHING
    """, (
        ligacao["id_equipa"],
        ligacao["id_atleta"],
        ligacao["nome"],
        ligacao["clube"],
        ligacao["escalao"]
    ))

# ======================================================
# FIREFOX
# ======================================================

def criar_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.binary_location = FIREFOX_BINARY
    service = Service(GeckoDriverManager().install())
    return webdriver.Firefox(service=service, options=opts)

# ======================================================
# UTILITÁRIOS
# ======================================================

def extrair_id_zerozero_atleta(url):
    m = re.search(r"/jogador/.*?/(\d+)", url)
    return int(m.group(1)) if m else None

# ======================================================
# SCRAPER PLANTEL
# ======================================================

def obter_plantel_equipa(driver, equipa):
    url_plantel = equipa["url"] + "/plantel"
    print(f"🔍 Plantel: {equipa['nome']}")

    driver.get(url_plantel)

    try:
        WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except:
        print("⚠️ Página de plantel não carregou")
        return []

    soup = BeautifulSoup(driver.page_source, "html.parser")

    atletas = []

    # o plantel está estruturado em tabelas
    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            a = tr.find("a", href=re.compile("/jogador/"))
            if not a:
                continue

            nome = a.get_text(strip=True)
            url = urljoin(BASE_ZEROZERO, a["href"])
            id_atleta = extrair_id_zerozero_atleta(url)

            if not id_atleta:
                continue

            atletas.append({
                "id": id_atleta,
                "nome": nome,
                "url": url
            })

    if not atletas:
        print("⚠️ Plantel vazio")
    return atletas

# ======================================================
# MAIN
# ======================================================

def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False

    driver = criar_driver()

    equipas_raw = obter_equipas(conn)
    print(f"✅ Equipas a processar: {len(equipas_raw)}")

    total_atletas = 0
    total_ligacoes = 0

    for (
        id_eq, nome_eq, clube, escalao, url
    ) in equipas_raw:

        equipa = {
            "id": id_eq,
            "nome": nome_eq,
            "clube": clube,
            "escalao": escalao,
            "url": url
        }

        try:
            atletas = obter_plantel_equipa(driver, equipa)

            for a in atletas:
                inserir_atleta(conn, a)
                inserir_plantel(conn, {
                    "id_equipa": id_eq,
                    "id_atleta": a["id"],
                    "nome": a["nome"],
                    "clube": clube,
                    "escalao": escalao
                })
                total_atletas += 1
                total_ligacoes += 1

            conn.commit()

        except Exception as e:
            conn.rollback()
            print(f"❌ Erro em {nome_eq}: {e}")

        time.sleep(DELAY)

    driver.quit()
    conn.close()

    print("\n✅ Scraping de plantéis concluído")
    print(f"Atletas processados: {total_atletas}")
    print(f"Ligações criadas: {total_ligacoes}")

if __name__ == "__main__":
    main()