from flask import (
    Flask, render_template, request, redirect,
    session, url_for, Response
)
import sqlite3
import os
import csv
from io import StringIO

# ======================================================
# APP E SEGURANÇA
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

DB_PATH = "jogadores_fpf.db"

# ======================================================
# BASE DE DADOS
# ======================================================

def get_db():
    # timeout evita "database is locked"
    return sqlite3.connect(DB_PATH, timeout=10)

# ======================================================
# CATEGORIA (A PARTIR DO ANO)
# ======================================================

def calcular_categoria_por_ano(ano_nascimento):
    if not ano_nascimento:
        return None

    mapa = {
        2021: "Sub-5",
        2020: "Sub-6",
        2019: "Sub-7",
        2018: "Sub-8",
        2017: "Sub-9",
        2016: "Sub-10",
        2015: "Sub-11",
        2014: "Sub-12",
        2013: "Sub-13",
        2012: "Sub-14",
        2011: "Sub-15",
        2010: "Sub-16",
        2009: "Sub-17",
        2008: "Sub-18",
        2007: "Sub-19",
    }

    return mapa.get(ano_nascimento, "Sénior")

# ======================================================
# LOGIN
# ======================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None

    if request.method == "POST":
        if request.form.get("password") == SITE_PASSWORD:
            session["autenticado"] = True
            return redirect(url_for("index"))
        else:
            erro = "Password incorreta"

    return render_template("login.html", erro=erro)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ======================================================
# QUERY PRINCIPAL
# ======================================================

def obter_jogadores(f):
    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT
            player_id,        -- r[0]
            nome,             -- r[1]
            data_nascimento,  -- r[2]
            ano_nascimento,   -- r[3]
            clube,            -- r[4]
            distrito,         -- r[5]
            naturalidade,     -- r[6]
            escalao           -- r[7]  (FPF)
        FROM jogadores
        WHERE 1=1
    """
    params = []
    filtros_ativos = False

    if f["nome"]:
        query += " AND nome LIKE ?"
        params.append(f"%{f['nome']}%")
        filtros_ativos = True

    if f["clube"]:
        query += " AND clube LIKE ?"
        params.append(f"%{f['clube']}%")
        filtros_ativos = True

    if f["ano_nasc"] and f["ano_nasc"].isdigit():
        query += " AND ano_nascimento = ?"
        params.append(int(f["ano_nasc"]))
        filtros_ativos = True

    if f["distrito"]:
        query += f" AND distrito IN ({','.join(['?'] * len(f['distrito']))})"
        params.extend(f["distrito"])
        filtros_ativos = True

    if f["naturalidade"]:
        query += f" AND naturalidade IN ({','.join(['?'] * len(f['naturalidade']))})"
        params.extend(f["naturalidade"])
        filtros_ativos = True

    COLUNAS_PERMITIDAS = [
        "player_id",
        "nome",
        "data_nascimento",
        "ano_nascimento",
        "clube",
        "distrito",
        "naturalidade",
        "escalao"
    ]

    if not filtros_ativos:
        query += " ORDER BY player_id DESC LIMIT 50"
    else:
        if f["sort"] in COLUNAS_PERMITIDAS:
            query += f" ORDER BY {f['sort']} {f['dir']}"
        else:
            query += " ORDER BY player_id DESC"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    jogadores = []
    for r in rows:
        categoria = calcular_categoria_por_ano(r[3])

        if f["escalao"] and categoria and categoria not in f["escalao"]:
            continue

        jogadores.append((
            r[0],      # ID
            r[1],      # Nome
            r[2],      # Nascimento
            r[4],      # Clube
            r[7],      # Escalão FPF
            categoria, # Categoria calculada
            r[5],      # Distrito
            r[6]       # Naturalidade
        ))

    return jogadores

# ======================================================
# PÁGINA PRINCIPAL
# ======================================================

@app.route("/")
def index():
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    f = {
        "nome": request.args.get("nome", ""),
        "clube": request.args.get("clube", ""),
        "ano_nasc": request.args.get("ano_nasc", ""),
        "escalao": request.args.getlist("escalao"),
        "distrito": request.args.getlist("distrito"),
        "naturalidade": request.args.getlist("naturalidade"),
        "sort": request.args.get("sort", "player_id"),
        "dir": request.args.get("dir", "ASC"),
    }

    jogadores = obter_jogadores(f)

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT distrito FROM jogadores WHERE distrito IS NOT NULL ORDER BY distrito")
    distritos = [r[0] for r in c.fetchall()]
    c.execute("SELECT DISTINCT naturalidade FROM jogadores WHERE naturalidade IS NOT NULL ORDER BY naturalidade")
    naturalidades = [r[0] for r in c.fetchall()]
    conn.close()

    escaloes = list(dict.fromkeys(j[5] for j in jogadores if j[5]))

    return render_template(
        "index.html",
        jogadores=jogadores,
        total=len(jogadores),
        distritos=distritos,
        naturalidades=naturalidades,
        escaloes=escaloes,
        filtros=f
    )

# ======================================================
# EXPORTAÇÃO PARA EXCEL
# ======================================================

@app.route("/exportar")
def exportar():
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    q = request.args.to_dict(flat=False)

    jogadores = obter_jogadores({
        "nome": q.get("nome", [""])[0],
        "clube": q.get("clube", [""])[0],
        "ano_nasc": q.get("ano_nasc", [""])[0],
        "escalao": q.get("escalao", []),
        "distrito": q.get("distrito", []),
        "naturalidade": q.get("naturalidade", []),
        "sort": q.get("sort", ["player_id"])[0],
        "dir": q.get("dir", ["ASC"])[0],
    })

    output = StringIO()
    writer = csv.writer(output, delimiter=";")

    writer.writerow([
        "ID", "Nome", "Nascimento",
        "Clube", "Escalão", "Categoria",
        "Distrito", "Naturalidade", "FPF"
    ])

    for j in jogadores:
        writer.writerow([
            j[0], j[1], j[2], j[3], j[4], j[5], j[6], j[7],
            f"https://www.fpf.pt/pt/Jogadores/Ficha-de-Jogador/playerId/{j[0]}"
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=jogadores.csv"}
    )

# ======================================================
# ARRANQUE
# ======================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)