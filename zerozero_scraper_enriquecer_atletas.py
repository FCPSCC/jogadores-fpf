# -*- coding: utf-8 -*-

import os
import re
import time
import psycopg2

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
FIREFOX_BINARY = r"C:\Users\augusto.roxo\AppData\Local\Mozilla Firefox\firefox.exe"

WAIT_TIMEOUT = 15
DELAY = 0.8

# ======================================================
# BD
# ======================================================

def obter_atletas(conn, limite=None):
    cur = conn.cursor()
    sql = """
        SELECT
            id_zerozero_atleta,
            nome_completo,
            url_zerozero
        FROM zerozero_atleta
        ORDER BY id_zerozero_atleta
    """
    if limite:
        sql += " LIMIT %s"
        cur.execute(sql, (limite,))
    else:
        cur.execute(sql)
    return cur.fetchall()

def atualizar_nome_atleta(conn, atleta_id, nome):
    cur = conn.cursor()
    cur.execute("""
        UPDATE zerozero_atleta
        SET nome_completo = %s
        WHERE id_zerozero_atleta = %s
    """, (nome, atleta_id))

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

def nome_precisa_enriquecimento(nome):
    if not nome:
        return True
    if nome.isdigit():
        return True
    if len(nome.split()) <= 2:
        return True
    return False

def extrair_nome_completo(html):
    soup = BeautifulSoup(html, "html.parser")

    # 1️⃣ DADOS PESSOAIS → Nome (canónico)
    bio = soup.find("div", class_="card-data bio")
    if bio:
        for row in bio.find_all("div", class_="card-data__row"):
            label = row.find("span", class_="card-data__label")
            value = row.find("span", class_="card-data__value")
            if label and value and label.get_text(strip=True) == "Nome":
                return value.get_text(strip=True)

    # 2️⃣ FAQ → “O nome completo é …”
    faq = soup.find("div", class_="faq answer")
    if faq:
        text = faq.get_text(" ", strip=True)
        m = re.search(r"nome completo é (.+)", text, re.IGNORECASE)
        if m:
            return m.group(1).strip().rstrip(".")

    # 3️⃣ H1 canónico
    h1 = soup.find("h1", class_="zz-name")
    if h1:
        return h1.get_text(strip=True)

    h1_schema = soup.find("h1", itemprop="name")
    if h1_schema:
        return h1_schema.get_text(strip=True)

    # 4️⃣ OpenGraph
    meta = soup.find("meta", property="og:title")
    if meta and meta.get("content"):
        return meta["content"].replace(" :: ZeroZero", "").strip()

    return None

# ======================================================
# SCRAPER
# ======================================================

def enriquecer_atleta(driver, atleta_id, url):
    print(f"🔍 Atleta {atleta_id}")
    driver.get(url)

    WebDriverWait(driver, WAIT_TIMEOUT).until(
        EC.presence_of_element_located((By.TAG_NAME, "body"))
    )

    return extrair_nome_completo(driver.page_source)

# ======================================================
# MAIN
# ======================================================

def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False

    driver = criar_driver()

    atletas = obter_atletas(conn)
    print(f"✅ Atletas a verificar: {len(atletas)}")

    atualizados = 0

    for atleta_id, nome_atual, url in atletas:
        if not nome_precisa_enriquecimento(nome_atual):
            continue

        try:
            nome_correto = enriquecer_atleta(driver, atleta_id, url)

            if nome_correto:
                atualizar_nome_atleta(conn, atleta_id, nome_correto)
                conn.commit()
                atualizados += 1
                print(f"   ✅ {nome_correto}")
            else:
                print("⚠️ Nome completo não disponível publicamente")
                conn.rollback()

        except Exception as e:
            conn.rollback()
            print(f"❌ Erro no atleta {atleta_id}: {e}")

        time.sleep(DELAY)

    driver.quit()
    conn.close()

    print("\n✅ Enriquecimento concluído")
    print(f"Atletas atualizados: {atualizados}")

if __name__ == "__main__":
    main()