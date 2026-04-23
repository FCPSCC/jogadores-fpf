from flask import Flask, render_template, request, Response
import sqlite3
import os
import csv
from io import StringIO

app = Flask(__name__)

DB_PATH = "jogadores_fpf.db"


def get_db():
    return sqlite3.connect(DB_PATH)


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


def obter_jogadores(filtros):
    conn = get_db()
    cursor = conn.cursor()

    query = """
        SELECT player_id, nome, data_nascimento, clube, distrito, naturalidade
        FROM jogadores
        WHERE 1=1
    """
    params = []
    filtros_ativos = False

    if filtros["nome"]:
        query += " AND nome LIKE ?"
        params.append(f"%{filtros['nome']}%")
        filtros_ativos = True

    if filtros["clube"]:
        query += " AND clube LIKE ?"
        params.append(f"%{filtros['clube']}%")
        filtros_ativos = True

    if filtros["ano_nasc"]:
        query += " AND substr(data_nascimento, -4) = ?"
        params.append(filtros["ano_nasc"])
        filtros_ativos = True

    if filtros["distrito"]:
        query += f" AND distrito IN ({','.join(['?']*len(filtros['distrito']))})"
        params.extend(filtros["distrito"])
        filtros_ativos = True

    if filtros["naturalidade"]:
        query += f" AND naturalidade IN ({','.join(['?']*len(filtros['naturalidade']))})"
        params.extend(filtros["naturalidade"])
        filtros_ativos = True

    query += f" ORDER BY {filtros['sort']} {filtros['dir']}"

    if not filtros_ativos:
        query += " LIMIT 50"

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    jogadores = []
    for r in rows:
        escalao = calcular_escalao(r[2])
        if filtros["escalao"] and escalao not in filtros["escalao"]:
            continue

        jogadores.append((
            r[0], r[1], r[2], r[3],
            escalao, r[4], r[5]
        ))

    return jogadores


@app.route("/", methods=["GET"])
def index():
    filtros = {
        "nome": request.args.get("nome", ""),
        "clube": request.args.get("clube", ""),
        "ano_nasc": request.args.get("ano_nasc", ""),
        "distrito": request.args.getlist("distrito"),
        "naturalidade": request.args.getlist("naturalidade"),
        "escalao": request.args.getlist("escalao"),
        "sort": request.args.get("sort", "player_id"),
        "dir": request.args.get("dir", "DESC")
    }

    jogadores = obter_jogadores(filtros)

    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT DISTINCT distrito FROM jogadores WHERE distrito IS NOT NULL")
    distritos = [r[0] for r in c.fetchall()]
    c.execute("SELECT DISTINCT naturalidade FROM jogadores WHERE naturalidade IS NOT NULL")
    naturalidades = [r[0] for r in c.fetchall()]
    c.execute("SELECT valor FROM controlo WHERE chave='ultimo_player_id'")
    ultimo_id = c.fetchone()[0]
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
        filtros=filtros,
        ultimo_id=ultimo_id
    )


@app.route("/exportar")
def exportar_excel():
    filtros = request.args.to_dict(flat=False)
    jogadores = obter_jogadores({
        "nome": filtros.get("nome", [""])[0],
        "clube": filtros.get("clube", [""])[0],
        "ano_nasc": filtros.get("ano_nasc", [""])[0],
        "distrito": filtros.get("distrito", []),
        "naturalidade": filtros.get("naturalidade", []),
        "escalao": filtros.get("escalao", []),
        "sort": filtros.get("sort", ["player_id"])[0],
        "dir": filtros.get("dir", ["DESC"])[0],
    })

    output = StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["ID","Nome","Nascimento","Clube","Escalão","Distrito","Naturalidade","FPF"])

    for j in jogadores:
        writer.writerow([
            j[0], j[1], j[2], j[3],
            j[4], j[5], j[6],
            f"https://www.fpf.pt/pt/Jogadores/Ficha-de-Jogador/playerId/{j[0]}"
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=jogadores.csv"}
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)