from flask import (
    Flask, render_template, request, redirect,
    session, url_for, Response
)
import sqlite3
import os
import csv
from io import StringIO
from datetime import date

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

DB_PATH = "jogadores_fpf.db"

# ======================================================
# BASE DE DADOS
# ======================================================

def get_db():
    return sqlite3.connect(DB_PATH, timeout=10)

# ======================================================
# ÉPOCA ATUAL (AUTOMÁTICA)
# ======================================================

def obter_ano_referencia_epoca():
    """
    Devolve o ano base da época desportiva atual.
    Ex:
      2025/26 -> 2025
    """
    hoje = date.today()
    if hoje.month >= 7:
        return hoje.year
    return hoje.year - 1

# ======================================================
# CATEGORIA FEDERATIVA (CORRETA)
# ======================================================

def calcular_categoria_por_ano(ano_nascimento):
    if not ano_nascimento:
        return None

    ano_epoca = obter_ano_referencia_epoca()
    idade = ano_epoca - ano_nascimento

    if idade < 5:
        return "Sub-5"
    if 5 <= idade <= 19:
        return f"Sub-{idade}"
    return "Sénior"

# ======================================================
# ORDEM DO ESCALÃO FPF
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
# QUERY PRINCIPAL
# ======================================================

def obter_jogadores(f):
    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT
            player_id,
            nome,
            data_nascimento,
            ano_nascimento,
            clube,
            distrito,
            naturalidade,
            escalao
        FROM jogadores
        WHERE 1=1
    """
    params = []

    if f["nome"]:
        query += " AND nome LIKE ?"
        params.append(f"%{f['nome']}%")

    if f["clube"]:
        query += " AND clube LIKE ?"
        params.append(f"%{f['clube']}%")

    if f["ano_nasc"].isdigit():
        query += " AND ano_nascimento = ?"
        params.append(int(f["ano_nasc"]))

    if f["distrito"]:
        query += f" AND distrito IN ({','.join(['?'] * len(f['distrito']))})"
        params.extend(f["distrito"])

    if f["naturalidade"]:
        query += f" AND naturalidade IN ({','.join(['?'] * len(f['naturalidade']))})"
        params.extend(f["naturalidade"])

    COLUNAS_OK = {
        "player_id", "nome", "data_nascimento",
        "ano_nascimento", "clube",
        "distrito", "naturalidade", "escalao"
    }

    ordem = "player_id DESC"
    if f["sort"] in COLUNAS_OK:
        direcao = "ASC" if f["dir"].upper() == "ASC" else "DESC"
        ordem = f"{f['sort']} {direcao}"

    sem_filtros = not any([
        f["nome"], f["clube"], f["ano_nasc"],
        f["categoria"], f["escalao_fpf"],
        f["distrito"], f["naturalidade"]
    ])

    if sem_filtros:
        query += f" ORDER BY {ordem} LIMIT 30"
    else:
        query += f" ORDER BY {ordem}"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    jogadores = []
    for r in rows:
        categoria = calcular_categoria_por_ano(r[3])

        if f["categoria"]:
            if not categoria or categoria not in f["categoria"]:
                continue

        if f["escalao_fpf"]:
            if not r[7] or r[7] not in f["escalao_fpf"]:
                continue

        jogadores.append((
            r[0], r[1], r[2], r[4],
            r[7], categoria, r[5], r[6]
        ))

    return jogadores

# ======================================================
# INDEX
# ======================================================

@app.route("/")
def index():
    if not session.get("autenticado"):
        return redirect("/login")

    f = {
        "nome": request.args.get("nome", ""),
        "clube": request.args.get("clube", ""),
        "ano_nasc": request.args.get("ano_nasc", ""),
        "categoria": request.args.getlist("categoria"),
        "escalao_fpf": request.args.getlist("escalao_fpf"),
        "distrito": request.args.getlist("distrito"),
        "naturalidade": request.args.getlist("naturalidade"),
        "sort": request.args.get("sort", "player_id"),
        "dir": request.args.get("dir", "DESC"),
    }

    jogadores = obter_jogadores(f)

    # ✅ LISTA COMPLETA E FIXA DE CATEGORIAS
    categorias = [f"Sub-{i}" for i in range(5, 20)] + ["Sénior"]

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT DISTINCT escalao
        FROM jogadores
        WHERE escalao IS NOT NULL AND escalao != ''
    """)

    escalaoes_fpf = sorted(
        [r[0] for r in c.fetchall()],
        key=ordem_escaloes_fpf
    )

    c.execute("SELECT DISTINCT distrito FROM jogadores WHERE distrito IS NOT NULL")
    distritos = sorted(r[0] for r in c.fetchall())

    c.execute("SELECT DISTINCT naturalidade FROM jogadores WHERE naturalidade IS NOT NULL")
    naturalidades = sorted(r[0] for r in c.fetchall())

    conn.close()

    return render_template(
        "index.html",
        jogadores=jogadores,
        total=len(jogadores),
        categorias=categorias,
        escalaoes_fpf=escalaoes_fpf,
        distritos=distritos,
        naturalidades=naturalidades,
        filtros=f
    )

# ======================================================
# EXPORTAR
# ======================================================

@app.route("/exportar")
def exportar():
    if not session.get("autenticado"):
        return redirect("/login")

    q = request.args.to_dict(flat=False)

    jogadores = obter_jogadores({
        "nome": q.get("nome", [""])[0],
        "clube": q.get("clube", [""])[0],
        "ano_nasc": q.get("ano_nasc", [""])[0],
        "categoria": q.get("categoria", []),
        "escalao_fpf": q.get("escalao_fpf", []),
        "distrito": q.get("distrito", []),
        "naturalidade": q.get("naturalidade", []),
        "sort": q.get("sort", ["player_id"])[0],
        "dir": q.get("dir", ["DESC"])[0],
    })

    output = StringIO()
    writer = csv.writer(output, delimiter=";")

    writer.writerow([
        "ID","Nome","Nascimento","Clube",
        "Escalão","Categoria",
        "Distrito","Naturalidade","FPF"
    ])

    for j in jogadores:
        writer.writerow([
            j[0], j[1], j[2], j[3],
            j[4], j[5], j[6], j[7],
            f"https://www.fpf.pt/pt/Jogadores/Ficha-de-Jogador/playerId/{j[0]}"
        ])

    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=jogadores.csv"}
    )

# ======================================================
# RUN
# ======================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
