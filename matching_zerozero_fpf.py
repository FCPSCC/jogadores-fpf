# -*- coding: utf-8 -*-

import os
import psycopg2
import unicodedata
from difflib import SequenceMatcher

DATABASE_URL = os.environ["DATABASE_URL"]

SCORE_CONFIRMADO = 70
SCORE_PENDENTE = 50

# ======================================================
# UTILITÁRIOS
# ======================================================

def normalizar(txt):
    if not txt:
        return ""
    txt = txt.lower()
    txt = unicodedata.normalize("NFD", txt)
    txt = "".join(c for c in txt if unicodedata.category(c) != "Mn")
    return " ".join(txt.split())

def similaridade(a, b):
    return SequenceMatcher(None, a, b).ratio()

def clube_compativel(zz_clube, fpf_clube):
    if not zz_clube or not fpf_clube:
        return False
    a = normalizar(zz_clube)
    b = normalizar(fpf_clube)
    return a in b or b in a

# ======================================================
# BD
# ======================================================

def obter_atletas_zerozero(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT id_zerozero_atleta, nome_completo
        FROM zerozero_atleta
        WHERE nome_completo IS NOT NULL
    """)
    return cur.fetchall()

def obter_contexto_zerozero(conn, zz_id):
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT clube, escalao
        FROM zerozero_plantel
        WHERE id_zerozero_atleta = %s
    """, (zz_id,))
    return cur.fetchall()

def obter_jogadores_fpf(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT
            player_id,
            nome,
            ano_nascimento,
            clube,
            escalao
        FROM jogadores
    """)
    return cur.fetchall()

def inserir_match(conn, zz_id, fpf_id, score, metodo, estado):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO match_zerozero_fpf (
            id_zerozero_atleta,
            player_id_fpf,
            score_confianca,
            metodo,
            estado
        )
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (id_zerozero_atleta) DO NOTHING
    """, (zz_id, fpf_id, score, metodo, estado))

# ======================================================
# MATCHING
# ======================================================

def calcular_score(
    nome_zz, nome_fpf,
    clube_zz, clube_fpf,
    escalao_zz, escalao_fpf
):
    score = 0
    metodo = []

    n1 = normalizar(nome_zz)
    n2 = normalizar(nome_fpf)

    sim = similaridade(n1, n2)

    if sim >= 0.80:
        score += 50
        metodo.append("nome≈")
    elif sim >= 0.70:
        score += 35
        metodo.append("nome~")
    else:
        return 0, None

    if clube_compativel(clube_zz, clube_fpf):
        score += 20
        metodo.append("clube")

    if escalao_zz and escalao_fpf and escalao_zz == escalao_fpf:
        score += 15
        metodo.append("escalao")

    return score, ",".join(metodo)

# ======================================================
# MAIN
# ======================================================

def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False

    atletas_zz = obter_atletas_zerozero(conn)
    jogadores_fpf = obter_jogadores_fpf(conn)

    print(f"✅ Atletas ZeroZero a processar: {len(atletas_zz)}")

    confirmados = 0
    pendentes = 0

    for zz_id, nome_zz in atletas_zz:
        contextos = obter_contexto_zerozero(conn, zz_id)
        melhor = None  # (score, player_id, metodo, estado)

        for clube_zz, escalao_zz in contextos:
            for (
                player_id, nome_fpf, _, clube_fpf, escalao_fpf
            ) in jogadores_fpf:

                score, metodo = calcular_score(
                    nome_zz, nome_fpf,
                    clube_zz, clube_fpf,
                    escalao_zz, escalao_fpf
                )

                if score < SCORE_PENDENTE:
                    continue

                estado = (
                    "confirmado" if score >= SCORE_CONFIRMADO
                    else "pendente"
                )

                if melhor is None or score > melhor[0]:
                    melhor = (score, player_id, metodo, estado)

        if melhor:
            inserir_match(
                conn,
                zz_id,
                melhor[1],
                melhor[0],
                melhor[2],
                melhor[3]
            )

            if melhor[3] == "confirmado":
                confirmados += 1
            else:
                pendentes += 1

            conn.commit()

    conn.close()

    print("\n✅ Matching concluído")
    print(f"Confirmados: {confirmados}")
    print(f"Pendentes: {pendentes}")

if __name__ == "__main__":
    main()