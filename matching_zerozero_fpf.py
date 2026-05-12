# -*- coding: utf-8 -*-

import os
import time
import psycopg2
import unicodedata

DATABASE_URL = os.environ["DATABASE_URL"]

# ======================================================
# NORMALIZAÇÃO
# ======================================================

def normalizar_texto(txt):
    if not txt:
        return ""

    txt = txt.lower()
    txt = unicodedata.normalize('NFD', txt)
    txt = txt.encode('ascii', 'ignore').decode("utf-8")

    txt = txt.replace("-", " ")
    txt = " ".join(txt.split())

    return txt.strip()


def normalizar_clube(nome):

    nome = normalizar_texto(nome)

    palavras_remover = [
        "futebol clube", "futebol clube do", "clube de futebol",
        "fc", "cf", "sc", "sl", "cd", "gd"
    ]

    for p in palavras_remover:
        nome = nome.replace(p, "")

    return " ".join(nome.split())

# ======================================================
# DB
# ======================================================

def obter_zerozero(conn):
    cur = conn.cursor()

    cur.execute("""
        SELECT id_zerozero_atleta, nome_completo
        FROM zerozero_atleta
    """)

    return cur.fetchall()


def obter_fpf(conn):
    cur = conn.cursor()

    cur.execute("""
        SELECT player_id, nome, data_nascimento, clube
        FROM jogadores
    """)

    return cur.fetchall()


def reconnect_db():
    while True:
        try:
            print("🔄 Reconectar BD...")
            conn = psycopg2.connect(DATABASE_URL)
            conn.autocommit = False
            print("✅ BD reconectada")
            return conn
        except Exception as e:
            print("⚠️ erro BD:", e)
            time.sleep(5)

# ======================================================
# MATCH
# ======================================================

def calcular_score(nome_zz, nome_fpf, clube_fpf):

    score = 0

    nome_zz_n = normalizar_texto(nome_zz)
    nome_fpf_n = normalizar_texto(nome_fpf)

    clube_fpf_n = normalizar_clube(clube_fpf)

    # ✅ nome
    if nome_zz_n == nome_fpf_n:
        score += 50
    elif nome_zz_n in nome_fpf_n or nome_fpf_n in nome_zz_n:
        score += 40

    # ✅ clube (só FPF → simples)
    if clube_fpf_n:
        score += 20

    return score


def inserir_match(conn, zz_id, fpf_id, score):

    while True:
        try:
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO match_zerozero_fpf (
                    id_zerozero_atleta,
                    player_id_fpf,
                    score_confianca,
                    metodo,
                    estado
                )
                VALUES (%s,%s,%s,'auto','confirmado')
                ON CONFLICT (id_zerozero_atleta) DO NOTHING
            """, (zz_id, fpf_id, score))

            conn.commit()
            break

        except Exception as e:
            print("⚠️ erro BD:", e)
            time.sleep(3)
            conn = reconnect_db()

# ======================================================
# MAIN
# ======================================================

def main():

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False

    zz = obter_zerozero(conn)
    fpf = obter_fpf(conn)

    print(f"✅ ZeroZero: {len(zz)}")
    print(f"✅ FPF: {len(fpf)}")

    total = len(zz)

    start_time = time.time()

    for i, z in enumerate(zz):

        zz_id = z[0]
        nome_zz = z[1]

        melhor_score = 0
        melhor_fpf = None

        for f in fpf:

            fpf_id = f[0]
            nome_fpf = f[1]
            clube_fpf = f[3]

            score = calcular_score(nome_zz, nome_fpf, clube_fpf)

            if score > melhor_score:
                melhor_score = score
                melhor_fpf = fpf_id

        if melhor_score >= 70:
            inserir_match(conn, zz_id, melhor_fpf, melhor_score)

        # ✅ PROGRESSO
        if i % 100 == 0:
            elapsed = time.time() - start_time
            percent = (i / total) * 100

            if i > 0:
                eta = elapsed / i * (total - i)
            else:
                eta = 0

            print(f"{i}/{total} | {percent:.2f}% | ⏱ {elapsed/60:.1f} min | ETA {eta/60:.1f} min")

    conn.close()

    print("\n✅ MATCHING CONCLUÍDO")


if __name__ == "__main__":
    main()