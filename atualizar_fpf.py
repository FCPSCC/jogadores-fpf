# -*- coding: utf-8 -*-

import time
import random
import sqlite3
import json
import re
import unicodedata
import pandas as pd

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

DB_PATH = r"C:\Users\augusto.roxo\Documents\Scripts\BD\jogadores_fpf.db"
CLUBES_XLSX = r"C:\Users\augusto.roxo\Documents\Scripts\BD\Clubes.xlsx"
FIREFOX_BINARY = r"C:\Users\augusto.roxo\AppData\Local\Mozilla Firefox\firefox.exe"

BASE_URL = "https://www.fpf.pt/pt/Jogadores/Ficha-de-Jogador/playerId/"
EPOCA_ATUAL = "2025-2026"

RANGE_MAX = 3000
MAX_FALHAS_SEGUIDAS = 80

# ======================================================
# UTILITÁRIOS
# ======================================================

def normalizar_nome(txt):
    if not txt:
        return ""
    txt = txt.lower().strip()
    txt = unicodedata.normalize("NFD", txt)
    txt = "".join(c for c in txt if unicodedata.category(c) != "Mn")
    txt = re.sub(r"[^a-z0-9 ]", "", txt)
    txt = re.sub(r"\s+", " ", txt)
    return txt


def converter_data_pt_para_iso(data_str):
    """
    16 de outubro de 2013 -> 16-10-2013
    """
    if not data_str:
        return None

    meses = {
        "janeiro": "01",
        "fevereiro": "02",
        "março": "03",
        "abril": "04",
        "maio": "05",
        "junho": "06",
        "julho": "07",
        "agosto": "08",
        "setembro": "09",
        "outubro": "10",
        "novembro": "11",
        "dezembro": "12",
    }

    partes = data_str.lower().split(" de ")
    if len(partes) != 3:
        return None

    dia = partes[0].zfill(2)
    mes = meses.get(partes[1])
    ano = partes[2]

    if not mes:
        return None

    return f"{dia}-{mes}-{ano}"

# ======================================================
# CLUBES → DISTRITO (Excel col B → col C)
# ======================================================

def carregar_clubes(path):
    df = pd.read_excel(path)
    mapa = {}

    for _, row in df.iterrows():
        clube = str(row.iloc[1]).strip()     # coluna B
        distrito = str(row.iloc[2]).strip()  # coluna C

        if clube and distrito and clube.lower() != "nan":
            mapa[normalizar_nome(clube)] = distrito

    return mapa

# ======================================================
# BASE DE DADOS
# ======================================================

def obter_ultimo_id(conn):
    cur = conn.cursor()
    cur.execute("SELECT valor FROM controlo WHERE chave='ultimo_player_id'")
    return int(cur.fetchone()[0])


def atualizar_ultimo_id(conn, pid):
    cur = conn.cursor()
    cur.execute(
        "UPDATE controlo SET valor=? WHERE chave='ultimo_player_id'",
        (str(pid),)
    )
    conn.commit()


def inserir_jogador(conn, d):
    cur = conn.cursor()
    cur.execute("""
        INSERT OR IGNORE INTO jogadores (
            player_id,
            nome,
            data_nascimento,
            clube,
            epoca,
            distrito,
            naturalidade,
            data_importacao
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        d["player_id"],
        d["nome"],
        d["data_nascimento"],
        d["clube"],
        d["epoca"],
        d["distrito"],
        d["naturalidade"]
    ))
    conn.commit()

# ======================================================
# FIREFOX HEADLESS
# ======================================================

def criar_driver():
    options = Options()
    options.add_argument("--headless")
    options.binary_location = FIREFOX_BINARY

    service = Service(GeckoDriverManager().install())
    driver = webdriver.Firefox(service=service, options=options)
    driver.set_page_load_timeout(30)
    return driver

# ======================================================
# EXTRAÇÃO
# ======================================================

def extrair_model_js(driver):
    html = driver.page_source
    m = re.search(r"var\s+model\s*=\s*(\{.*?\})\s*;", html, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(1))
    except:
        return {}


def valor_por_dt(driver, label):
    try:
        el = driver.find_element(
            By.XPATH,
            f"//dt[normalize-space()='{label}:']/following-sibling::dd[1]"
        )
        return el.text.strip()
    except:
        return None

# ======================================================
# SCRAPING DO JOGADOR
# ======================================================

def obter_dados_jogador(driver, pid, mapa_clubes):
    driver.get(f"{BASE_URL}{pid}")

    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "dl"))
        )
    except:
        return None

    model = extrair_model_js(driver)

    nome = model.get("FullName") or valor_por_dt(driver, "Nome")

    nascimento_raw = (
        model.get("BirthDate")
        or valor_por_dt(driver, "Data de Nascimento")
    )
    nascimento = converter_data_pt_para_iso(nascimento_raw)

    naturalidade = (
        model.get("Nationality")
        or model.get("PlaceOfBirth")
        or valor_por_dt(driver, "Naturalidade")
    )

    clube = model.get("CurrentClub")

    if not clube:
        try:
            clube = driver.find_element(
                By.XPATH,
                "//table[contains(@class,'table')]//tbody/tr[1]/td[1]"
            ).text.strip()
        except:
            clube = None

    if not nome or not nascimento or not clube:
        return None

    distrito = mapa_clubes.get(normalizar_nome(clube))

    return {
        "player_id": pid,
        "nome": nome,
        "data_nascimento": nascimento,   # ✅ DD-MM-AAAA
        "clube": clube,                 # ✅ clube real
        "epoca": EPOCA_ATUAL,            # ✅ época correta
        "distrito": distrito,
        "naturalidade": naturalidade
    }

# ======================================================
# MAIN
# ======================================================

def main():
    print("A carregar Clubes.xlsx...")
    mapa_clubes = carregar_clubes(CLUBES_XLSX)

    conn = sqlite3.connect(DB_PATH)
    ultimo_id = obter_ultimo_id(conn)

    inicio = ultimo_id + 1
    fim = inicio + RANGE_MAX

    driver = criar_driver()
    falhas = 0
    ultimo_valido = ultimo_id

    print(f"A iniciar atualização a partir do ID {inicio}")

    try:
        for pid in range(inicio, fim):
            print(f"A testar ID {pid}")

            dados = obter_dados_jogador(driver, pid, mapa_clubes)

            if not dados:
                falhas += 1
                if falhas >= MAX_FALHAS_SEGUIDAS:
                    print("Sem novos atletas por muitos IDs. A parar.")
                    break
                continue

            falhas = 0
            inserir_jogador(conn, dados)
            ultimo_valido = pid

            print(f"Inserido: {dados['nome']} ({pid})")
            time.sleep(random.uniform(1.5, 3.0))

    finally:
        atualizar_ultimo_id(conn, ultimo_valido)
        conn.close()
        driver.quit()
        print("Atualização concluída.")

if __name__ == "__main__":
    main()