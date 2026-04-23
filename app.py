from flask import (
    Flask, render_template, request, redirect,
    session, url_for, Response
)
import sqlite3
import os
import csv
from io import StringIO

app = Flask(__name__)

# ======================================================
# SEGURANÇA
# ======================================================

app.secret_key = os.environ.get("SECRET_KEY", "chave-temporaria-123")
SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "MUDAR123")

# ======================================================
# BASE DE DADOS
# ======================================================

DB_PATH = "jogadores_fpf.db"

def get_db():
    return sqlite3.connect(DB_PATH)

# ======================================================
# LOGIN
# ======================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    erro = None

    if request.method == "POST":
        password = request.form.get("password")

        if password == SITE_PASSWORD:
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
# LÓGICA NEGÓCIO
# ======================================================

def calcular_escalao(data_nascimento):
    try:
        ano = int(data_nascimento.split("-")[2])
    except:
        return "Desconhecido"

    mapa = {
        2021: "Petizes - Sub-5",
        2020: "Petizes - Sub-6",
        2019: "Petizes - Sub-7",
        2018: "Traquinas - Sub-8",
        2017: "Traquinas - Sub-9",
        2016: "Benjamins - Sub-10",
        2015: "Benjamins - Sub-11",
        2014: "Infantis - Sub-12",
        2013: "Infantis - Sub-13",
        2012: "Iniciados - Sub-14",
        2011: "Iniciados - Sub-15",
        2010: "Juvenis - Sub-16",
        2009: "Juvenis - Sub-17",
        2008: "Juniores - Sub-18",
        2007: "Juniores - Sub-19",
    }
    return mapa.get(ano, "Sénior")

def obter_jogadores(f):
    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT player_id, nome, data_nascimento,
               clube, distrito, naturalidade
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

    if f["ano_nasc"]:
        query += " AND substr(data_nascimento, -4) = ?"
        params.append(f["ano_nasc"])
        filtros_ativos = True

    if f["distrito"]:
        query += f" AND distrito IN ({','.join(['?']*len(f['distrito']))})"
        params.extend(f["distrito"])
        filtros_ativos = True

    if f["naturalidade"]:
        query += f" AND naturalidade IN ({','.join(['?']*len(f['naturalidade']))})"
        params.extend(f["naturalidade"])
        filtros_ativos = True

    query += f" ORDER BY {f['sort']} {f['dir']}"

    if not filtros_ativos:
        query += " LIMIT 50"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    jogadores = []
    for r in rows:
        escalao = calcular_escalao(r[2])
        if f["escalao"] and escalao not in f["escalao"]:
            continue

        jogadores.append((
            r[0], r[1], r[2], r[3],
            escalao, r[4], r[5]
        ))

    return jogadores

# ======================================================
# ROTAS PROTEGIDAS
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
        "dir": request.args.get("dir", "ASC")
    }

    jogadores = obter_jogadores(f)

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT distrito FROM jogadores WHERE distrito IS NOT NULL")
    distritos = [r[0] for r in c.fetchall()]
    c.execute("SELECT DISTINCT naturalidade FROM jogadores WHERE naturalidade IS NOT NULL")
    naturalidades = [r[0] for r in c.fetchall()]
    conn.close()

    escaloes = [
        "Petizes - Sub-5","Petizes - Sub-6","Petizes - Sub-7",
        "Traquinas - Sub-8","Traquinas - Sub-9",
        "Benjamins - Sub-10","Benjamins - Sub-11",
        "Infantis - Sub-12","Infantis - Sub-13",
        "Iniciados - Sub-14","Iniciados - Sub-15",
        "Juvenis - Sub-16","Juvenis - Sub-17",
        "Juniores - Sub-18","Juniores - Sub-19","Sénior"
    ]

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
# EXPORTAÇÃO
# ======================================================

@app.route("/exportar")
def exportar():
    if not session.get("autenticado"):
        return redirect(url_for("login"))

    f = request.args.to_dict(flat=False)

    jogadores = obter_jogadores({
        "nome": f.get("nome", [""])[0],
        "clube": f.get("clube", [""])[0],
        "ano_nasc": f.get("ano_nasc", [""])[0],
        "escalao": f.get("escalao", []),
        "distrito": f.get("distrito", []),
        "naturalidade": f.get("naturalidade", []),
        "sort": f.get("sort", ["player_id"])[0],
        "dir": f.get("dir", ["ASC"])[0],
    })

    output = StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID","Nome","Nascimento","Clube","Escalão","Distrito","Naturalidade","FPF"])

    for j in jogadores:
        writer.writerow([
            j[0], j[1], j[2], j[3], j[4], j[5], j[6],
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