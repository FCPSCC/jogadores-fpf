# -*- coding: utf-8 -*-

import os
import re
import time
import psycopg2
from datetime import datetime

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager

# ======================================================
# CONFIG
# ======================================================

DATABASE_URL = os.environ["DATABASE_URL"]

FIREFOX_BINARY = r"C:\Users\augusto.roxo\AppData\Local\Mozilla Firefox\firefox.exe"

WAIT_TIMEOUT = 20
DELAY = 0.8

ANO_EPOCA = 2026

# ======================================================
# BD
# ======================================================

def obter_matches(conn):
    cur = conn.cursor()

    cur.execute("""
        SELECT
            m.player_id_fpf,
            m.id_zerozero_atleta,
            z.nome_completo,
            z.url_zerozero,
            j.ano_nascimento
        FROM match_zerozero_fpf m
        JOIN zerozero_atleta z
            ON z.id_zerozero_atleta = m.id_zerozero_atleta
        JOIN jogadores j
            ON j.player_id = m.player_id_fpf
        WHERE m.estado = 'confirmado'
    """)

    return cur.fetchall()

def inserir_stat(conn, row):
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO estatisticas_zerozero (
            player_id,
            jogos,
            golos,
            competicao,
            epoca,
            ultima_atualizacao,
            zz_player_url,
            foto_url
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, row)

# ======================================================
# DRIVER
# ======================================================

def criar_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.binary_location = FIREFOX_BINARY
    service = Service(GeckoDriverManager().install())
    return webdriver.Firefox(service=service, options=opts)

# ======================================================
# UTIL
# ======================================================

def extrair_s(texto):
    if not texto:
        return None
    m = re.search(r"S(\d+)", texto)
    return int(m.group(1)) if m else None

def interpretar_status(esc_zz, esc_esperado):
    diff = esc_zz - esc_esperado
    if diff > 0:
        return f"ACIMA (+{diff})"
    elif diff == 0:
        return "OK"
    else:
        return f"ABAIXO ({diff})"

def extrair_foto(soup):
    img = soup.find("img", {"itemprop": "image"})
    if img:
        return img.get("src")
    return None

# ======================================================
# SCRAPER HISTÓRICO
# ======================================================

def extrair_career(soup):
    tabela = soup.find("table", class_="career")
    if not tabela:
        return []

    resultados = []

    for tr in tabela.find("tbody").find_all("tr"):
        cols = tr.find_all("td")
        if len(cols) < 5:
            continue

        epoca = cols[1].get_text(strip=True)

        clube_raw = cols[2].get_text(" ", strip=True)

        jogos_txt = cols[3].get_text(strip=True)
        golos_txt = cols[4].get_text(strip=True)

        try:
            jogos = int(jogos_txt)
        except:
            jogos = None

        try:
            golos = int(golos_txt)
        except:
            golos = None

        resultados.append((epoca, clube_raw, jogos, golos))

    return resultados

# ======================================================
# MAIN
# ======================================================

def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False

    driver = criar_driver()

    dados = obter_matches(conn)
    print(f"✅ Jogadores a processar: {len(dados)}")

    total = 0

    for player_id, zz_id, nome, url, ano_nasc in dados:

        print(f"🔍 {nome}")

        driver.get(url)

        WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )

        soup = BeautifulSoup(driver.page_source, "html.parser")

        foto = extrair_foto(soup)
        historico = extrair_career(soup)

        for epoca, clube_raw, jogos, golos in historico:

            esc_zz = extrair_s(clube_raw)

            if esc_zz and ano_nasc:
                esc_esperado = ANO_EPOCA - ano_nasc
                status = interpretar_status(esc_zz, esc_esperado)

                competicao = f"{clube_raw} | S{esc_zz} | ESP S{esc_esperado} | {status}"
            else:
                competicao = clube_raw

            inserir_stat(conn, (
                player_id,
                jogos,
                golos,
                competicao,
                epoca,
                datetime.now(),
                url,
                foto
            ))

            total += 1

        conn.commit()
        time.sleep(DELAY)

    driver.quit()
    conn.close()

    print("\n✅ PIPELINE CONCLUÍDO")
    print(f"Total registos inseridos: {total}")

# ======================================================
# ENTRY
# ======================================================

if __name__ == "__main__":
    main()