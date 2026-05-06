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
# CONFIG
# ======================================================

DATABASE_URL = os.environ["DATABASE_URL"]
FIREFOX_BINARY = r"C:\Users\augusto.roxo\AppData\Local\Mozilla Firefox\firefox.exe"

WAIT_TIMEOUT = 10
DELAY = 1

# ======================================================
# BD
# ======================================================

def obter_atletas(conn, limite=None):
    cur = conn.cursor()

    sql = """
    SELECT id_zerozero_atleta, url_zerozero
    FROM zerozero_atleta
    WHERE ultima_atualizacao IS NULL
       OR ultima_atualizacao < NOW() - INTERVAL '1 day'
    ORDER BY ultima_atualizacao NULLS FIRST
    """

    if limite:
        sql += " LIMIT %s"
        cur.execute(sql, (limite,))
    else:
        cur.execute(sql)

    return cur.fetchall()

def marcar_atualizado(conn, atleta_id):
    cur = conn.cursor()
    cur.execute("""
        UPDATE zerozero_atleta
        SET ultima_atualizacao = NOW()
        WHERE id_zerozero_atleta = %s
    """, (atleta_id,))


def limpar_estatisticas(conn, atleta_id):
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM estatisticas_zerozero WHERE player_id = %s",
        (atleta_id,)
    )


def inserir(conn, d):
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO estatisticas_zerozero
        (player_id, epoca, competicao, jogos, golos)
        VALUES (%s, %s, %s, %s, %s)
    """, (
        d["player_id"],
        d["epoca"],
        d["competicao"],
        d["jogos"],
        d["golos"]
    ))

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
# EXTRAÇÃO CORRETA
# ======================================================

def extrair_estatisticas(driver, player_id):
    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")

    # ✅ 👉 CONTAINER EXATO QUE ENVIASTE
    container = soup.select_one("#coach_career")

    if not container:
        print("❌ container #coach_career não encontrado")
        return []

    tabela = container.select_one("table.career")

    if not tabela:
        print("❌ tabela career não encontrada")
        return []

    rows = tabela.select("tbody tr")

    epoca_atual = None
    dados = []

    for row in rows:
        cols = row.find_all("td")

        if len(cols) < 4:
            continue

        # ✅ coluna da época
        epoca = cols[1].get_text(strip=True)

        if epoca:
            epoca_atual = epoca

        if not epoca_atual:
            continue

        # ✅ equipa + escalão
        equipa = cols[2].get_text(" ", strip=True)

        # ✅ jogos e golos
        jogos = cols[3].get_text(strip=True)
        golos = cols[4].get_text(strip=True)

        jogos = None if jogos in ["-", ""] else int(jogos)
        golos = None if golos in ["-", ""] else int(golos)

        dados.append({
            "player_id": player_id,
            "epoca": epoca_atual,
            "competicao": equipa,
            "jogos": jogos,
            "golos": golos
        })

    return dados

# ======================================================
# PROCESSAR ATLETA
# ======================================================

def processar_atleta(driver, conn, atleta_id, url):
    print(f"🔍 Atleta {atleta_id}")

    driver.get(url)

    try:
        WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, "coach_career"))
        )
    except:
        print("❌ página não carregou corretamente")
        return

    time.sleep(1)

    dados = extrair_estatisticas(driver, atleta_id)

    if not dados:
        print("⚠️ Sem dados")
        return

    limpar_estatisticas(conn, atleta_id)

    for d in dados:
        inserir(conn, d)

    conn.commit()

    print(f"✅ {len(dados)} registos inseridos")

# ======================================================
# MAIN
# ======================================================

def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False

    driver = criar_driver()

    atletas = obter_atletas(conn)

    for atleta_id, url in atletas:
        try:
            processar_atleta(driver, conn, atleta_id, url)
            marcar_atualizado(conn, atleta_id)
            time.sleep(DELAY)
        except Exception as e:
            print(f"❌ erro {atleta_id}: {e}")
            conn.rollback()

    driver.quit()
    conn.close()


if __name__ == "__main__":
    main()