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
GECKO_PATH = r"C:\Users\augusto.roxo\Documents\Scripts\drivers\geckodriver.exe"


WAIT_TIMEOUT = 20
DELAY = 1.5
RESET_DRIVER_EVERY = 500

# ======================================================
# BD
# ======================================================

def obter_equipas(conn):
    cur = conn.cursor()

    cur.execute("""
        SELECT
            z.id_zerozero_equipa,
            z.nome_equipa,
            z.clube,
            z.escalao,
            z.url_zerozero
        FROM zerozero_equipa z
        WHERE z.url_zerozero IS NOT NULL
        AND NOT EXISTS (
            SELECT 1 FROM zerozero_plantel p
            WHERE p.id_zerozero_equipa = z.id_zerozero_equipa
        )
        ORDER BY id_zerozero_equipa
    """)

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
        RETURNING id_zerozero_atleta
    """, (
        atleta["id"],
        atleta["nome"],
        atleta["url"]
    ))

    return cur.fetchone()


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

    service = Service(GECKO_PATH)

    return webdriver.Firefox(service=service, options=opts)

# ======================================================
# UTILITÁRIOS
# ======================================================

def extrair_id_zerozero_atleta(url):
    m = re.search(r"/jogador/.+?/(\d+)", url)
    return int(m.group(1)) if m else None

# ======================================================
# SCRAPER PLANTEL (CORRIGIDO)
# ======================================================

def obter_plantel_equipa(driver, equipa):
    url_plantel = equipa["url"] + "/plantel"
    print(f"🔍 {equipa['nome']}")

    for tentativa in range(3):
    try:
        driver.get(url_plantel)
        break
    except:
        print("⚠️ erro carregar página, retry...")
        time.sleep(3)


    try:
        WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
    except:
        print("⚠️ página não carregou")
        return []

    soup = BeautifulSoup(driver.page_source, "html.parser")

    atletas = []

    # ✅ SELECTOR ROBUSTO (FIX PRINCIPAL)
    links = soup.select("a[href*='/jogador/']")

    for link in links:
        nome = link.get_text(strip=True)

        # ✅ evita lixo (links vazios / icones)
        if not nome or len(nome) < 3:
            continue

        href = link.get("href")
        url = urljoin(BASE_ZEROZERO, href)

        id_atleta = extrair_id_zerozero_atleta(url)
        if not id_atleta:
            continue

        atletas.append({
            "id": id_atleta,
            "nome": nome,
            "url": url
        })

    # ✅ remove duplicados da página
    atletas_unicos = {}
    for a in atletas:
        atletas_unicos[a["id"]] = a

    atletas = list(atletas_unicos.values())

    if not atletas:
        print("⚠️ sem jogadores encontrados")

    return atletas

 import os

    print("GECKO OK:", os.path.exists(GECKO_PATH))
    print("FIREFOX OK:", os.path.exists(FIREFOX_BINARY))

# ======================================================
# MAIN
# ======================================================

def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False

    def safe_criar_driver():
        while True:
            try:
                return criar_driver()
            except Exception as e:
                print("⚠️ erro a criar driver, retry...")
                time.sleep(5)

    driver = safe_criar_driver()


    equipas = obter_equipas(conn)
    total = len(equipas)

    print(f"✅ Equipas por processar: {total}")

    total_atletas = 0
    total_ligacoes = 0

    for i, (id_eq, nome_eq, clube, escalao, url) in enumerate(equipas):

        # ✅ reinicia driver para evitar crash
        if i > 0 and i % RESET_DRIVER_EVERY == 0:
            print("🔄 reiniciar driver...")
            driver.quit()
            driver = criar_driver()

        equipa = {
            "id": id_eq,
            "nome": nome_eq,
            "clube": clube,
            "escalao": escalao,
            "url": url
        }

        print(f"\n🏟️ {i+1}/{total} - {nome_eq}")

        try:
            atletas = obter_plantel_equipa(driver, equipa)

            for a in atletas:
                res = inserir_atleta(conn, a)

                if res:
                    total_atletas += 1

                inserir_plantel(conn, {
                    "id_equipa": id_eq,
                    "id_atleta": a["id"],
                    "nome": a["nome"],
                    "clube": clube,
                    "escalao": escalao
                })

                total_ligacoes += 1

            conn.commit()

        except Exception as e:
            print("❌ erro equipa:", nome_eq)
            print(e)

            try:
                conn.rollback()
            except:
                conn = psycopg2.connect(DATABASE_URL)

        time.sleep(DELAY)

    driver.quit()
    conn.close()

    print("\n✅ SCRAPER CONCLUÍDO")
    print("Atletas novos:", total_atletas)
    print("Ligações:", total_ligacoes)


if __name__ == "__main__":
    main()
