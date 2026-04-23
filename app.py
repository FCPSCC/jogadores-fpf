from flask import Flask, render_template, request
import sqlite3
import os

app = Flask(__name__)

DB_PATH = "jogadores_fpf.db"

def get_db():
    return sqlite3.connect(DB_PATH)


def calcular_escalao(data_nascimento):
    try:
        ano = int(data_nascimento.split("-")[2])  # DD-MM-AAAA
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


@app.route("/")
def index():
    nome = request.args.get("nome", "").strip()
    clube = request.args.get("clube", "").strip()
    ano_nasc = request.args.get("ano_nasc", "").strip()

    distritos_sel = request.args.getlist("distrito")
    naturalidades_sel = request.args.getlist("naturalidade")
    escaloes_sel = request.args.getlist("escalao")

    sort = request.args.get("sort", "player_id")
    direcao = request.args.get("dir", "desc")

    colunas_validas = {
        "player_id": "player_id",
        "nome": "nome",
        "data_nascimento": "data_nascimento",
        "clube": "clube",
        "epoca": "epoca",
        "distrito": "distrito",
        "naturalidade": "naturalidade"
    }

    coluna_sort = colunas_validas.get(sort, "player_id")
    direcao_sql = "ASC" if direcao == "asc" else "DESC"

    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("SELECT DISTINCT distrito FROM jogadores WHERE distrito IS NOT NULL ORDER BY distrito")
    distritos = [d[0] for d in cursor.fetchall()]

    cursor.execute("SELECT DISTINCT naturalidade FROM jogadores WHERE naturalidade IS NOT NULL ORDER BY naturalidade")
    naturalidades = [n[0] for n in cursor.fetchall()]

    query = """
        SELECT
            player_id,
            nome,
            data_nascimento,
            clube,
            epoca,
            distrito,
            naturalidade
        FROM jogadores
        WHERE 1=1
    """
    params = []
    filtros_ativos = False

    if nome:
        query += " AND nome LIKE ?"
        params.append(f"%{nome}%")
        filtros_ativos = True

    if clube:
        query += " AND clube LIKE ?"
        params.append(f"%{clube}%")
        filtros_ativos = True

    if ano_nasc:
        query += " AND substr(data_nascimento, -4) = ?"
        params.append(ano_nasc)
        filtros_ativos = True

    if distritos_sel:
        query += f" AND distrito IN ({','.join(['?'] * len(distritos_sel))})"
        params.extend(distritos_sel)
        filtros_ativos = True

    if naturalidades_sel:
        query += f" AND naturalidade IN ({','.join(['?'] * len(naturalidades_sel))})"
        params.extend(naturalidades_sel)
        filtros_ativos = True

    query += f" ORDER BY {coluna_sort} {direcao_sql}"

    if not filtros_ativos:
        query += " LIMIT 50"

    cursor.execute(query, params)
    linhas = cursor.fetchall()

    jogadores = []
    for j in linhas:
        escalao = calcular_escalao(j[2])
        if escaloes_sel and escalao not in escaloes_sel:
            continue

        jogadores.append((
            j[0], j[1], j[2], escalao,
            j[3], j[4], j[5], j[6]
        ))

    total_resultados = len(jogadores)

    cursor.execute("SELECT valor FROM controlo WHERE chave='ultimo_player_id'")
    ultimo_id = cursor.fetchone()[0]

    conn.close()

    escaloes = [
        "Petizes - Sub-5","Petizes - Sub-6","Petizes - Sub-7",
        "Traquinas - Sub-8","Traquinas - Sub-9",
        "Benjamins - Sub-10","Benjamins - Sub-11",
        "Infantis - Sub-12","Infantis - Sub-13",
        "Iniciados - Sub-14","Iniciados - Sub-15",
        "Juvenis - Sub-16","Juvenis - Sub-17",
        "Juniores - Sub-18","Juniores - Sub-19",
        "Sénior"
    ]

    return render_template(
        "index.html",
        jogadores=jogadores,
        total_resultados=total_resultados,
        ultimo_id=ultimo_id,
        distritos=distritos,
        naturalidades=naturalidades,
        escaloes=escaloes,
        sort=sort,
        direcao=direcao,
        filtros={
            "nome": nome,
            "clube": clube,
            "ano_nasc": ano_nasc,
            "distrito": distritos_sel,
            "naturalidade": naturalidades_sel,
            "escalao": escaloes_sel
        }
    )


if __name__ == "__main__":
    import os
    print("BD usada:", os.path.abspath(DB_PATH))

    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
