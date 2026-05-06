# -*- coding: utf-8 -*-

import os
import psycopg2
import unicodedata
from difflib import SequenceMatcher

DATABASE_URL = os.environ["DATABASE_URL"]

LIMIAR = 0.75

# ======================================================
# NORMALIZAÇÃO
# ======================================================

def normalizar(txt):
    if not txt:
        return ""

    txt = txt.lower()

    txt = unicodedata.normalize("NFD", txt)
    txt = "".join(c for c in txt if unicodedata.category(c) != "Mn")

    txt = txt.replace(".", "")
    txt = txt.replace("-", " ")

    remover = ["fc", "sc", "cd", "ac", "clube", "futebol"]
    for r in remover:
        txt = txt.replace(r, "")

    palavras = txt.split()
    palavras = [p for p in palavras if not p.isdigit()]

    return " ".join(palavras)

def similaridade(a, b):
    return SequenceMatcher(None, a, b).ratio()

# ======================================================
# BD
# ======================================================

def clubes_fpf(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT clube
        FROM jogadores
        WHERE clube IS NOT NULL
    """)
    return [r[0] for r in cur.fetchall()]

def clubes_zz(conn):
    cur = conn.cursor()
    cur.execute("""
        SELECT DISTINCT clube
        FROM zerozero_equipa
    """)
    return [r[0] for r in cur.fetchall()]

def inserir(conn, fpf, zz):
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO clube_zerozero_base (clube_fpf, url_zerozero_base, ativo)
        VALUES (%s, %s, TRUE)
        ON CONFLICT (clube_fpf)
        DO NOTHING
    """, (fpf, zz))

# ======================================================
# MATCHING
# ======================================================

def main():
    conn = psycopg2.connect(DATABASE_URL)

    fpf = clubes_fpf(conn)
    zz = clubes_zz(conn)

    print(f"FPF: {len(fpf)}")
    print(f"ZZ: {len(zz)}")

    matchs = 0
    falhados = 0

    for c1 in fpf:

        n1 = normalizar(c1)

        best = None
        best_score = 0

        for c2 in zz:

            n2 = normalizar(c2)

            score = similaridade(n1, n2)

            if score > best_score:
                best_score = score
                best = c2

        if best_score >= LIMIAR:
            print(f"✅ {c1} → {best} ({best_score:.2f})")
            inserir(conn, c1, best)
            matchs += 1
        else:
            print(f"❌ {c1} ({best_score:.2f})")
            falhados += 1

    conn.commit()
    conn.close()

    print("\n✅ RESULTADO")
    print(f"✔ Matches: {matchs}")
    print(f"❌ Falhados: {falhados}")

if __name__ == "__main__":
    main()