# -*- coding: utf-8 -*-

import time
import random
import sqlite3
import re
import unicodedata
import json
from datetime import datetime

import openpyxl
from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from webdriver_manager.firefox import GeckoDriverManager

# ======================================================
# CONFIGURAÇÃO
# ======================================================

DB_PATH = "jogadores_fpf.db"
CLUBES_XLSX = "Clubes.xlsx"

BASE_URL = "https://www.fpf.pt/pt/Jogadores/Ficha-de-Jogador/playerId/"
EPOCA_ATUAL = "2025-2026"

RANGE_MAX = 3000
MAX_FALHAS_SEGUIDAS = 80
MAX_RETRIES_POR_ID = 3

FIREFOX_BINARY = r"C:\Users\augusto.roxo\AppData\Local\Mozilla Firefox\firefox.exe"

# ======================================================
# UTILITÁRIOS
# ======================================================

def normalizar_clube(txt):
    if not txt:
        return None
    txt = txt.lower()
    txt = unicodedata.normalize("NFD", txt)
    txt = "".join(c for c in txt if unicodedata.category(c) != "Mn")
    txt = re.sub(r"[.\-]", " ", txt)
    txt = re.sub(r"\s+", " ", txt)
    return txt.strip()

def extrair_ano(data):
    try:
        return int(data[-4:])
    except:
        return None

def converter_data_pt_para_ddmmaaaa(data):
    if not data:
        return None

    data = unicodedata.normalize("NFD", data)
    data = "".join(c for c in data if unicodedata.category(c) != "Mn")
    data = data.lower().strip()

    meses = {
        "janeiro": "01","fevereiro": "02","marco": "03",
        "abril": "04","maio": "05","junho": "06",
        "julho": "07","agosto": "08","setembro": "09",
        "outubro": "10","novembro": "11","dezembro": "12",
    }

    m = re.match(r"(\d{1,2})\s+de\s+([a-z]+)\s+de\s+(\d{4})", data)
    if not m:
        return None

    dia, mes_txt, ano = m.groups()
    mes = meses.get(mes_txt)
    if not mes:
        return None

    return f"{dia.zfill(2)}-{mes}-{ano}"

def calcular_categoria_por_ano(ano):
    if not ano:
        return None
    idade = 2026 - ano  # ajustar se mudares época dinâmica
    return f"Sub-{idade}"

# ======================================================
# CLUBES → DISTRITOS
# ======================================================

def carregar_mapa_clubes():
    wb = openpyxl.load_workbook(CLUBES_XLSX)
    ws = wb.active
    mapa = {}
    for row in ws.iter_rows(min_row=2, values_only=True):
        clube = row[1]
        distrito = row[2]
        if clube and distrito:
            mapa[normalizar_clube(clube)] = distrito.strip()
    print(f"✅ Clubes carregados: {len(mapa)}")
    return mapa

# ======================================================
# BASE DE DADOS
# ======================================================

def obter_ultimo_id(conn):
    cur = conn.cursor()
    cur.execute("SELECT valor FROM controlo WHERE chave='ultimo_player_id'")
    return int(cur.fetchone()[0])

def atualizar_ultimo_id(conn, pid):
    conn.execute(
        "UPDATE controlo SET valor=? WHERE chave='ultimo_player_id'",
        (str(pid),)
    )

def inserir_jogador(conn, dados, mapa_clubes):
    clube_norm = normalizar_clube(dados["clube"])
    distrito = mapa_clubes.get(clube_norm)

    conn.execute("""
        INSERT OR REPLACE INTO jogadores (
            player_id,
            nome,
            data_nascimento,
            ano_nascimento,
            clube,
            epoca,
            distrito,
            naturalidade,
            escalao,
            categoria,
            data_importacao
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        dados["player_id"],
        dados["nome"],
        dados["data_nascimento"],
        extrair_ano(dados["data_nascimento"]),
        dados["clube"],
        dados["epoca"],
        distrito,
        dados["naturalidade"],
        dados["escalao"],    # Escalão FPF
        dados["categoria"],  # Sub-X
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
# MODEL JS
# ======================================================

def extrair_model_js(driver):
    html = driver.page_source
    m = re.search(r"var\s+model\s*=\s*({.*?})\s*;", html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except:
        return None

# ======================================================
# EXTRAÇÃO JOGADOR (COM RETRY)
# ======================================================

def obter_dados_jogador(driver, pid):
    for _ in range(MAX_RETRIES_POR_ID):
        try:
            driver.get(f"{BASE_URL}{pid}")

            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )

            model = extrair_model_js(driver)
            if not model:
                time.sleep(1)
                continue

            nome = model.get("FullName") or model.get("ShortName")
            if not nome:
                return None  # jogador não existe

            # ESCALÃO FPF
            escalao = None
            for c in model.get("Clubs", []):
                if c.get("Season") == EPOCA_ATUAL:
                    escalao = c.get("FootballClassName")
                    break

            data_nasc = converter_data_pt_para_ddmmaaaa(model.get("BirthDate"))
            ano = extrair_ano(data_nasc)
            categoria = calcular_categoria_por_ano(ano)

            return {
                "player_id": pid,
                "nome": nome,
                "data_nascimento": data_nasc,
                "clube": model.get("CurrentClub"),
                "epoca": EPOCA_ATUAL,
                "naturalidade": model.get("Nationality"),
                "escalao": escalao,
                "categoria": categoria
            }

        except (TimeoutException, WebDriverException):
            time.sleep(1)

    return None

# ======================================================
# MAIN
# ======================================================

def main():
    mapa_clubes = carregar_mapa_clubes()

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("BEGIN")

    driver = criar_driver()

    ultimo = obter_ultimo_id(conn)
    falhas = 0

    for pid in range(ultimo + 1, ultimo + RANGE_MAX):
        dados = obter_dados_jogador(driver, pid)

        if dados:
            inserir_jogador(conn, dados, mapa_clubes)
            atualizar_ultimo_id(conn, pid)
            falhas = 0
            print(f"✅ {pid} — {dados['nome']}")
        else:
            falhas += 1
            print(f"❌ {pid} inexistente / erro ({falhas})")

        if falhas >= MAX_FALHAS_SEGUIDAS:
            print("🛑 Limite de falhas consecutivas atingido")
            break

        time.sleep(random.uniform(0.8, 1.4))

    driver.quit()
    conn.commit()
    conn.close()

    print("✅ Execução terminada com sucesso.")

    git_push_bd()

# ======================================================
# GIT PUSH
# ======================================================

import subprocess

def git_push_bd():
    subprocess.run(["git", "add", "jogadores_fpf.db"], check=False)
    subprocess.run(["git", "commit", "-m", "Atualização automática da BD"], check=False)
    subprocess.run(["git", "push"], check=False)

# ======================================================
# ENTRY POINT
# ======================================================

if __name__ == "__main__":
    main()