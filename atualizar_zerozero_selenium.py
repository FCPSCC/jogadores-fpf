# -*- coding: utf-8 -*-

import sqlite3
import requests
import re
import time
from datetime import datetime

# ======================================================
# CONFIGURAÇÃO
# ======================================================

DB_PATH = "jogadores_fpf.db"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

PAUSA_ENTRE_JOGADORES = 2  # segundos

# ======================================================
# EXTRAÇÃO ZEROZERO (HTML REAL)
# ======================================================

def extrair_dados_zerozero(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
    except Exception:
        return None

    html = r.text

    # ----------------------------
    # FOTO (background-image)
    # ----------------------------
    foto_url = None
    foto_match = re.search(
        r'background-image\s*:\s*url\([\'"]?(https://cdn-img\.staticzz\.com/[^\'")]+)',
        html,
        re.IGNORECASE
    )
    if foto_match:
        foto_url = foto_match.group(1)

    # ----------------------------
    # ÉPOCA + COMPETIÇÃO (HEADER)
    # ----------------------------
    epoca = None
    competicao = None

    header_match = re.search(
        r'Resumo\s+(\d{4}/\d{2}).*?<span>\s*\[(.*?)\]\s*</span>',
        html,
        re.DOTALL | re.IGNORECASE
    )
    if header_match:
        epoca = header_match.group(1)
        competicao = header_match.group(2)

    # ----------------------------
    # JOGOS E GOLOS
    # ----------------------------
    jogos = None
    golos = None

    jm = re.search(
        r'<div class="number">\s*(\d+)\s*</div>\s*<div class="label">\s*Jogos\s*</div>',
        html,
        re.IGNORECASE
    )
    gm = re.search(
        r'<div class="number">\s*(\d+)\s*</div>\s*<div class="label">\s*Golos\s*</div>',
        html,
        re.IGNORECASE
    )

    if jm:
        jogos = int(jm.group(1))
    if gm:
        golos = int(gm.group(1))

    if jogos is None or golos is None:
        return None

    return {
        "jogos": jogos,
        "golos": golos,
        "epoca": epoca,
        "competicao": competicao,
        "foto_url": foto_url
    }

# ======================================================
# SCRIPT PRINCIPAL
# ======================================================

def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    c.execute("""
        SELECT player_id, zz_player_url
        FROM estatisticas_zerozero
        WHERE zz_player_url IS NOT NULL
          AND (
              ultima_atualizacao IS NULL
              OR ultima_atualizacao < datetime('now', '-7 days')
          )
    """)

    jogadores = c.fetchall()
    print(f"Jogadores a atualizar: {len(jogadores)}")

    for player_id, zz_url in jogadores:
        print(f"▶️ Atualizar player_id {player_id}")

        dados = extrair_dados_zerozero(zz_url)
        if not dados:
            print("❌ Falhou extração")
            continue

        c.execute("""
            UPDATE estatisticas_zerozero
            SET jogos = ?,
                golos = ?,
                epoca = ?,
                competicao = ?,
                foto_url = ?,
                ultima_atualizacao = ?
            WHERE player_id = ?
        """, (
            dados["jogos"],
            dados["golos"],
            dados["epoca"],
            dados["competicao"],
            dados["foto_url"],
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            player_id
        ))

        conn.commit()

        print(
            f"✅ Jogos: {dados['jogos']} | "
            f"Golos: {dados['golos']} | "
            f"{dados['competicao']} | "
            f"{dados['epoca']} | "
            f"Foto: {'OK' if dados['foto_url'] else '—'}"
        )

        time.sleep(PAUSA_ENTRE_JOGADORES)

    conn.close()
    print("✅ Atualização ZeroZero concluída.")

# ======================================================
# ENTRY POINT
# ======================================================

if __name__ == "__main__":
    main()
