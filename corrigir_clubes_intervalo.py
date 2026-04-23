# -*- coding: utf-8 -*-

import sqlite3
import time
import random
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

ID_INICIO = 2352773
ID_FIM = 2359000

DB_PATH = r"C:\Users\augusto.roxo\Documents\Scripts\BD\jogadores_fpf.db"
CLUBES_XLSX = r"C:\Users\augusto.roxo\Documents\Scripts\BD\Clubes.xlsx"
FIREFOX_BINARY = r"C:\Users\augusto.roxo\AppData\Local\Mozilla Firefox\firefox.exe"

BASE_URL = "https://www.fpf.pt/pt/Jogadores/Ficha-de-Jogador/playerId/"

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

# ======================================================
# CORREÇÃO DE UM ATLETA
# ======================================================

def corrigir_atleta(conn, driver, mapa_clubes, player_id):
    driver.get(f"{BASE_URL}{player_id}")

    try:
        WebDriverWait(driver, 12).until(
            EC.presence_of_element_located((By.TAG_NAME, "dl"))
        )
    except:
        return

    model = extrair_model_js(driver)
    clube = model.get("CurrentClub")

    if not clube:
        try:
            clube = driver.find_element(
                By.XPATH,
                "//table[contains(@class,'table')]//tbody/tr[1]/td[1]"
            ).text.strip()
        except:
            return

    distrito = mapa_clubes.get(normalizar_nome(clube))

    cur = conn.cursor()
    cur.execute("""
        UPDATE jogadores
        SET clube = ?, distrito = ?
        WHERE player_id = ?
    """, (clube, distrito, player_id))
    conn.commit()

    print(f"Corrigido: {player_id} → {clube} ({distrito})")

# ======================================================
# MAIN
# ======================================================

def main():
    mapa_clubes = carregar_clubes(CLUBES_XLSX)
    conn = sqlite3.connect(DB_PATH)
    driver = criar_driver()

    try:
        for pid in range(ID_INICIO, ID_FIM + 1):
            corrigir_atleta(conn, driver, mapa_clubes, pid)
            time.sleep(random.uniform(1.2, 2.5))
    finally:
        conn.close()
        driver.quit()
        print("Correção de clubes concluída.")

if __name__ == "__main__":
    main()