# -*- coding: utf-8 -*-

import sqlite3
import requests
import re
import time

# ======================================================
# CONFIGURAÇÃO
# ======================================================

DB_PATH = "jogadores_fpf.db"
EPOCA_ATUAL = "2025/26"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-PT,pt;q=0.9,en-US;q=0.8,en;q=0.7",
}

PAUSA_ENTRE_JOGADORES = 2

# ======================================================
# EXTRAÇÃO DA PARTICIPAÇÃO NA ÉPOCA ATUAL
# ======================================================

def extrair_participacao_epoca_atual(html):
    resultados = []

    # dividir por secções Futebol / Futsal
    blocos = re.split(
        r'<div class="section">\s*<span>(Futebol|Futsal)</span>\s*</div>',
        html,
        flags=re.IGNORECASE
    )

    for i in range(1, len(blocos), 2):
        modalidade = blocos[i]
        bloco_html = blocos[i + 1]

        # cada tabela career pertence a esta modalidade
        tables = re.findall(
            r'<table[^>]*class="career"[^>]*>(.*?)</table>',
            bloco_html,
            re.DOTALL
        )

        for table in tables:
            rows = re.findall(
                r'<tr[^>]*>(.*?)</tr>',
                table,
                re.DOTALL
            )

            for row in rows:
                cols = re.findall(
                    r'<td[^>]*>(.*?)</td>',
                    row,
                    re.DOTALL
                )

                if len(cols) < 5:
                    continue

                epoca = re.sub(r'<.*?>', '', cols[1]).strip()
                if epoca != EPOCA_ATUAL:
                    continue  # ignorar outras épocas

                # clube
                clube_match = re.search(r'>([^<]+)</a>', cols[2])
                clube = clube_match.group(1).strip() if clube_match else None

                # etiqueta com escalão (ex: [Fut.9 Jun.D S12])
                etiqueta_match = re.search(r'\[(.*?)\]', cols[2])
                etiqueta = etiqueta_match.group(1).strip() if etiqueta_match else None

                # extrair escalão SXX
                escalao = None
                if etiqueta:
                    esc_match = re.search(r'S(\d{1,2})', etiqueta)
                    if esc_match:
                        escalao = int(esc_match.group(1))

                # jogos e golos
                try:
                    jogos = int(re.sub(r'<.*?>', '', cols[3]).strip())
                except:
                    jogos = 0

                try:
                    golos = int(re.sub(r'<.*?>', '', cols[4]).strip())
                except:
                    golos = 0

                if clube and escalao:
                    resultados.append({
                        "modalidade": modalidade,
                        "clube": clube,
                        "escalao": escalao,
                        "escalao_texto": etiqueta,
                        "jogos": jogos,
                        "golos": golos
                    })

    return resultados

# ======================================================
# SCRIPT PRINCIPAL
# ======================================================

def main():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # garantir tabela
    c.execute("""
        CREATE TABLE IF NOT EXISTS participacao_epoca_atual (
            player_id INTEGER,
            modalidade TEXT,
            clube TEXT,
            escalao INTEGER,
            escalao_texto TEXT,
            jogos INTEGER,
            golos INTEGER,
            PRIMARY KEY (player_id, modalidade, clube, escalao_texto)
        )
    """)
    conn.commit()

    c.execute("""
        SELECT player_id, zz_player_url
        FROM estatisticas_zerozero
        WHERE zz_player_url IS NOT NULL
    """)

    jogadores = c.fetchall()
    print(f"Jogadores a analisar: {len(jogadores)}")

    for player_id, zz_url in jogadores:
        print(f"▶️ Analisar player_id {player_id}")

        try:
            r = requests.get(zz_url, headers=HEADERS, timeout=20)
            r.raise_for_status()
        except:
            print("❌ Falha ao carregar página")
            continue

        participacoes = extrair_participacao_epoca_atual(r.text)

        # limpar entradas anteriores da época atual
        c.execute("""
            DELETE FROM participacao_epoca_atual
            WHERE player_id = ?
        """, (player_id,))
        conn.commit()

        for p in participacoes:
            c.execute("""
                INSERT OR REPLACE INTO participacao_epoca_atual
                (player_id, modalidade, clube, escalao, escalao_texto, jogos, golos)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                player_id,
                p["modalidade"],
                p["clube"],
                p["escalao"],
                p["escalao_texto"],
                p["jogos"],
                p["golos"]
            ))
            print(
                f"  ✅ {p['modalidade']} | {p['clube']} | S{p['escalao']} | "
                f"{p['jogos']}J {p['golos']}G"
            )

        conn.commit()
        time.sleep(PAUSA_ENTRE_JOGADORES)

    conn.close()
    print("✅ Participação na época atual atualizada com sucesso.")

# ======================================================
# ENTRY POINT
# ======================================================

if __name__ == "__main__":
    main()