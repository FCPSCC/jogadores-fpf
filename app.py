from flask import (
    Flask, render_template, request, redirect,
    session, url_for, Response
)
from io import StringIO
from datetime import date, datetime
import os
import csv

import psycopg2
import psycopg2.extras

# ======================================================
# APP
# ======================================================

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "chave-temporaria-123"
)

SITE_PASSWORD = os.environ.get(
    "SITE_PASSWORD",
    "MUDAR123"
)

# ======================================================
# BASE DE DADOS
# ======================================================

def get_db():
    return psycopg2.connect(
        os.environ["DATABASE_URL"],
        cursor_factory=psycopg2.extras.RealDictCursor
    )

def garantir_tabela_jogadores():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS jogadores (
            player_id INTEGER PRIMARY KEY,
            nome TEXT,
            data_nascimento DATE,
            ano_nascimento INTEGER,
            clube TEXT,
            escalao TEXT,
            distrito TEXT,
            naturalidade TEXT
        )
    """)

    conn.commit()
    cur.close()
    conn.close()

def garantir_tabela_estatisticas_zerozero():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS estatisticas_zerozero (
            id SERIAL PRIMARY KEY,
            player_id INTEGER,
            jogos INTEGER,
            golos INTEGER,
            competicao TEXT,
            epoca TEXT,
            ultima_atualizacao TEXT,
            zz_player_url TEXT,
            foto_url TEXT
        )
    """)

    conn.commit()
    cur.close()
    conn.close()

def garantir_tabela_participacao():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS participacao_epoca_atual (
            id SERIAL PRIMARY KEY,
            player_id INTEGER,
            modalidade TEXT,
            clube TEXT,
            escalao INTEGER,
            escalao_texto TEXT,
            jogos INTEGER,
            golos INTEGER
        )
    """)

    conn.commit()
    cur.close()
    conn.close()

# ======================================================
# ÉPOCA ATUAL
# ======================================================

def obter_ano_referencia_epoca():
    hoje = date.today()
    return hoje.year if hoje.month >= 7 else hoje.year - 1

# ======================================================
# CATEGORIA FEDERATIVA
# ======================================================

def calcular_categoria_por_ano(ano_nascimento):
    if not ano_nascimento:
        return None

    ano_epoca = obter_ano_referencia_epoca()
    sub = ano_epoca - ano_nascimento + 1

    if sub < 5:
        return None
    if 5 <= sub <= 19:
        return f"Sub-{sub}"
    return "Sénior"

def extrair_numero_escalao(cat):
    if cat and cat.startswith("Sub-"):
        return int(cat.replace("Sub-", ""))
    return None

# ======================================================
# ORDEM ESCALÃO FPF
# ======================================================

def ordem_escaloes_fpf(txt):
    if not txt:
        return 99
    t = txt.lower()
    if "petiz" in t: return 1
    if "traquina" in t: return 2
    if "benjamim" in t: return 3
    if "infantil" in t: return 4
    if "iniciado" in t: return 5
    if "juvenil" in t: return 6
    if "junior" in t or "júnior" in t: return 7
    if "senior" in t or "sénior" in t: return 8
    return 99

# ======================================================
# LOGIN
# ======================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None
    if request.method == "POST":
        if request.form.get("password") == SITE_PASSWORD:
            session["autenticado"] = True
            return redirect("/")
        erro = "Password incorreta"
    return render_template("login.html", erro=erro)

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ======================================================
# QUERY PRINCIPAL (COM LIMIT / OFFSET)
# ======================================================

def obter_jogadores(f, sort_col, sort_dir, offset=0):
    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT
            j.player_id, j.nome, j.data_nascimento,
            j.clube, j.escalao, j.ano_nascimento,
            j.distrito, j.naturalidade
        FROM jogadores j
        WHERE 1=1
    """
    params = []

    if f.get("nome"):
        query += " AND j.nome ILIKE %s"
        params.append(f"%{f['nome']}%")

    coluna = sort_col if sort_col in [
        "player_id", "nome", "data_nascimento", "clube",
        "escalao", "ano_nascimento", "distrito", "naturalidade"
    ] else "player_id"

    direcao = "ASC" if sort_dir == "asc" else "DESC"

    query += f" ORDER BY j.{coluna} {direcao} LIMIT 100 OFFSET %s"
    params.append(offset)

    c.execute(query, params)
    rows = c.fetchall()

    c.close()
    conn.close()

    jogadores = []
    for r in rows:
        categoria = calcular_categoria_por_ano(r["ano_nascimento"])
        jogadores.append((
            r["player_id"], r["nome"], r["data_nascimento"],
            r["clube"], r["escalao"], categoria,
            r["distrito"], r["naturalidade"]
        ))

    return jogadores

# ======================================================
# INDEX (PÁGINA SEGURA PARA 195K JOGADORES)
# ======================================================

@app.route("/")
def index():
    if not session.get("autenticado"):
        return redirect("/login")

    garantir_tabela_participacao()

    f = {
        "nome": request.args.get("nome", "")
    }

    sort_col = request.args.get("sort", "player_id")
    sort_dir = request.args.get("dir", "desc")
    page = int(request.args.get("page", 0))
    offset = page * 100

    jogadores = []
    if f["nome"]:
        jogadores = obter_jogadores(f, sort_col, sort_dir, offset)

    return render_template(
        "index.html",
        jogadores=jogadores,
        total=len(jogadores),
        categorias=[f"Sub-{i}" for i in range(5, 20)] + ["Sénior"],
        escalaoes_fpf=[],
        distritos=[],
        naturalidades=[],
        filtros=f,
        page=page
    )

# ======================================================
# RUN
# ======================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)