# -*- coding: utf-8 -*-

import os
import time
import psycopg2
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ======================================================
# CONFIG
# ======================================================

DATABASE_URL = os.environ["DATABASE_URL"]
WAIT_TIMEOUT = 10
DELAY = 1

# ======================================================
# BD
# ======================================================

def obter_atletas(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT id_zerozero_atleta, url_zerozero
        FROM zerozero_atleta
    """)
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
    cur.execute("""
        DELETE FROM estatisticas_zerozero
        WHERE player_id = %s
    """, (atleta_id,))


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
# DRIVER (SIMPLIFICADO E ESTÁVEL)
# ======================================================

def criar_driver():
    opts = Options()
    opts.add_argument("--headless")  # comenta isto se quiseres ver browser

    return webdriver.Firefox(options=opts)

# ======================================================
# EXTRAÇÃO
# ======================================================

def extrair_estatisticas(driver, player_id):
    html = driver.page_source
    soup = BeautifulSoup(html, "html.parser")

    # ✅ FOTO (via source - método robusto)
    foto_url = None

    meta = soup.find("meta", property="og:image")

    if meta:
        url = meta.get("content")

        if url and str(player_id) in url:
            foto_url = url

    if not foto_url and meta:
        foto_url = meta.get("content")

    print(f"📸 FOTO {player_id}: {foto_url}")

    # ✅ TABELA
    container = soup.select_one("#coach_career")

    if not container:
        print("❌ container não encontrado")
        return [], foto_url

    tabela = container.select_one("table.career")

    if not tabela:
        print("❌ tabela não encontrada")
        return [], foto_url

    rows = tabela.select("tbody tr")

    epoca_atual = None
    dados = []

    for row in rows:
        cols = row.find_all("td")

        if len(cols) < 4:
            continue

        epoca = cols[1].get_text(strip=True)

        if epoca:
            epoca_atual = epoca

        if not epoca_atual:
            continue

        competicao = cols[2].get_text(" ", strip=True)

        jogos = cols[3].get_text(strip=True)
        golos = cols[4].get_text(strip=True)

        jogos = None if jogos in ["-", ""] else int(jogos)
        golos = None if golos in ["-", ""] else int(golos)

        dados.append({
            "player_id": player_id,
            "epoca": epoca_atual,
            "competicao": competicao,
            "jogos": jogos,
            "golos": golos
        })

    return dados, foto_url

# ======================================================
# PROCESSAR
# ======================================================

def processar_atleta(driver, conn, atleta_id, url):
    print(f"🔍 Atleta {atleta_id}")

    driver.get(url)

    try:
        WebDriverWait(driver, WAIT_TIMEOUT).until(
            EC.presence_of_element_located((By.ID, "coach_career"))
        )
    except:
        print("❌ página não carregou")
        return

    time.sleep(1)

    dados, foto_url = extrair_estatisticas(driver, atleta_id)

    if not dados:
        print("⚠️ Sem dados")
        return

    # ✅ GUARDAR FOTO (LOCAL CORRETO)
    if foto_url:
        cur = conn.cursor()
        cur.execute("""
            UPDATE zerozero_atleta
            SET foto_url = %s
            WHERE id_zerozero_atleta = %s
        """, (foto_url, atleta_id))

    limpar_estatisticas(conn, atleta_id)

    for d in dados:
        inserir(conn, d)

    marcar_atualizado(conn, atleta_id)

    conn.commit()

    print(f"✅ {len(dados)} registos inseridos")

# ======================================================
# MAIN
# ======================================================

def main():
    conn = psycopg2.connect(DATABASE_URL)

    driver = criar_driver()

    atletas = obter_atletas(conn)

    for atleta_id, url in atletas:
        try:
            processar_atleta(driver, conn, atleta_id, url)
            time.sleep(DELAY)
        except Exception as e:
            print(f"❌ erro {atleta_id}: {e}")
            conn.rollback()

    driver.quit()
    conn.close()


if __name__ == "__main__":
    main()