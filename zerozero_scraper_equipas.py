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

WAIT_TIMEOUT = 25
DELAY = 1.2

MODALIDADES_PERMITIDAS = {
    "Futebol",
    "Futsal",
    "Futebol de 9",
    "Futebol de 7",
    "Act. Lúdicas (Max. 5)",
}

# ======================================================
# BD
# ======================================================

def obter_clubes_base(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT clube_fpf, url_zerozero_base
        FROM clube_zerozero_base
        WHERE ativo = TRUE
        ORDER BY clube_fpf
    """)
    return cur.fetchall()

def inserir_equipa(conn, equipa):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO zerozero_equipa (
            id_zerozero_equipa,
            nome_equipa,
            clube,
            escalao,
            url_zerozero
        )
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (id_zerozero_equipa) DO NOTHING
    """, (
        equipa["id"],
        equipa["nome"],
        equipa["clube"],
        equipa["escalao"],
        equipa["url"]
    ))
    conn.commit()

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

def extrair_id_zerozero(url):
    m = re.search(r"/(\d+)$", url)
    return int(m.group(1)) if m else None

def inferir_escalao(nome):
    m = re.search(r"(S\d+|Sub-\d+)", nome, re.I)
    return m.group(1) if m else None

# ======================================================
# SCRAPER DE EQUIPAS (CORRETO)
# ======================================================

def processar_clube(driver, clube_fpf, url_base):
    print(f"🔍 Abrir página base de {clube_fpf}")
    driver.get(url_base)

    WebDriverWait(driver, WAIT_TIMEOUT).until(
        EC.presence_of_element_located((By.CLASS_NAME, "card-data"))
    )

    soup = BeautifulSoup(driver.page_source, "html.parser")

    equipas = []

    # Procurar o card "Equipas"
    cards = soup.find_all("div", class_="card-data")

    card_equipas = None
    for card in cards:
        title = card.find("h2", class_="card-data__title")
        if title and "Equipas" in title.get_text():
            card_equipas = card
            break

    if not card_equipas:
        print("❌ Card de Equipas não encontrado")
        return []

    body = card_equipas.find("div", class_="card-data__body")
    if not body:
        print("❌ card-data__body das Equipas não encontrado")
        return []

    sections = body.find_all("div", class_="section")
    print(f"📦 Secções Equipas: {[s.get_text(strip=True) for s in sections]}")

    for sec in sections:
        modalidade = sec.get_text(strip=True)
        if modalidade not in MODALIDADES_PERMITIDAS:
            continue

        lista = sec.find_next_sibling("div", class_="rbtextlist")
        if not lista:
            continue

        for a in lista.find_all("a"):
            nome = a.get_text(strip=True)
            href = a.get("href")

            if not nome or not href:
                continue

            url_full = urljoin(BASE_ZEROZERO, href)
            id_eq = extrair_id_zerozero(url_full)
            if not id_eq:
                continue

            equipas.append({
                "id": id_eq,
                "nome": nome,
                "clube": clube_fpf,
                "escalao": inferir_escalao(nome),
                "url": url_full
            })

    return {e["id"]: e for e in equipas}.values()

# ======================================================
# MAIN
# ======================================================

def main():
    conn = psycopg2.connect(DATABASE_URL)
    driver = criar_driver()

    clubes = obter_clubes_base(conn)
    total = 0

    for clube, url in clubes:
        print(f"\n🔹 Processar clube: {clube}")
        equipas = processar_clube(driver, clube, url)

        for eq in equipas:
            inserir_equipa(conn, eq)
            total += 1
            print(f"   ✅ {eq['nome']}")

    driver.quit()
    conn.close()

    print(f"\n✅ Total de equipas gravadas: {total}")

if __name__ == "__main__":
    main()