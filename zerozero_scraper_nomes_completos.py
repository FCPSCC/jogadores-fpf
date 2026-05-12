# -*- coding: utf-8 -*-

import os
import re
import time
import subprocess
import psycopg2
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.firefox.options import Options

# ======================================================
# CONFIG
# ======================================================

DATABASE_URL = os.environ["DATABASE_URL"]

FIREFOX_BINARY = r"C:\Users\augusto.roxo\AppData\Local\Mozilla Firefox\firefox.exe"
GECKO_PATH = r"C:\Users\augusto.roxo\Documents\Scripts\drivers\geckodriver.exe"

DELAY = 1.0
RESET_DRIVER_EVERY = 200

# ======================================================
# BD
# ======================================================

def obter_jogadores(conn):
    cur = conn.cursor()

    cur.execute("""
        SELECT id_zerozero_atleta, url_zerozero
        FROM zerozero_atleta
        WHERE 
            nome_completo IS NULL
            OR nome_completo = ''
            OR array_length(string_to_array(nome_completo, ' '), 1) <= 2
        ORDER BY id_zerozero_atleta
    """)

    return cur.fetchall()

def reconnect_db():
    while True:
        try:
            print("🔄 tentar reconectar BD...")
            conn = psycopg2.connect(DATABASE_URL)
            conn.autocommit = False
            print("✅ BD reconectada")
            return conn
        except Exception as e:
            print("⚠️ erro BD:", e)
            time.sleep(5)

# ======================================================
# FIREFOX
# ======================================================

def criar_driver():
    opts = Options()
    opts.add_argument("--headless")
    opts.binary_location = FIREFOX_BINARY

    service = Service(GECKO_PATH)

    return webdriver.Firefox(service=service, options=opts)

def matar_processos_firefox():
    try:
        subprocess.run("taskkill /f /im firefox.exe", shell=True, stdout=subprocess.DEVNULL)
        subprocess.run("taskkill /f /im geckodriver.exe", shell=True, stdout=subprocess.DEVNULL)
    except:
        pass

def safe_criar_driver():
    while True:
        try:
            return criar_driver()
        except Exception as e:
            print("⚠️ erro driver → limpar e retry")
            print(e)
            matar_processos_firefox()
            time.sleep(5)

# ======================================================
# EXTRAÇÃO NOME
# ======================================================

def extrair_nome(soup):

    # ✅ método principal
    rows = soup.select(".card-data__row")

    for r in rows:
        label = r.select_one(".card-data__label")
        value = r.select_one(".card-data__value")

        if label and "Nome" in label.get_text():
            return value.get_text(strip=True)

    # ✅ fallback meta
    meta = soup.find("meta", {"name": "description"})
    if meta:
        content = meta.get("content", "")
        if "::" in content:
            return content.split("::")[0].strip()

    # ✅ fallback FAQ
    faqs = soup.select(".faq.answer .text")
    for f in faqs:
        txt = f.get_text()
        if "O nome completo é" in txt:
            return txt.replace("O nome completo é", "").replace(".", "").strip()

    return None

# ======================================================
# MAIN
# ======================================================

def main():

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False

    jogadores = obter_jogadores(conn)
    total = len(jogadores)

    print(f"✅ Jogadores a processar: {total}")

    driver = safe_criar_driver()
    cur = conn.cursor()

    success = 0
    erros = 0

    for i, (id_atleta, url) in enumerate(jogadores):

        # ✅ reiniciar driver
        if i > 0 and i % RESET_DRIVER_EVERY == 0:
            print("🔄 reiniciar driver...")
            try:
                driver.quit()
            except:
                pass
            matar_processos_firefox()
            driver = safe_criar_driver()

        print(f"{i+1}/{total} → {id_atleta}")

        try:
            # ✅ retry página
            for tentativa in range(3):
                try:
                    driver.get(url)
                    break
                except:
                    print("🌐 erro rede, retry...")
                    time.sleep(3)

            time.sleep(0.5)

            soup = BeautifulSoup(driver.page_source, "html.parser")

            nome = extrair_nome(soup)

            if nome:
                cur.execute("""
                    UPDATE zerozero_atleta
                    SET nome_completo = %s
                    WHERE id_zerozero_atleta = %s
                """, (nome, id_atleta))

                success += 1
                print("✅", nome)
            else:
                erros += 1
                print("⚠️ nome não encontrado")

        except Exception as e:
            print("❌ erro:", e)
            erros += 1

            try:
                conn.rollback()
            except:
                pass

            # ✅ recuperar BD
            conn = reconnect_db()
            cur = conn.cursor()

            # ✅ recuperar driver
            try:
                driver.quit()
            except:
                pass
            matar_processos_firefox()
            driver = safe_criar_driver()

        # ✅ commit protegido
        try:
            conn.commit()
        except:
            print("⚠️ erro commit")
            conn = reconnect_db()
            cur = conn.cursor()

        time.sleep(DELAY)

    try:
        driver.quit()
    except:
        pass

    conn.close()

    print("\n✅ FINAL")
    print("Sucesso:", success)
    print("Erros:", erros)


if __name__ == "__main__":
    main()