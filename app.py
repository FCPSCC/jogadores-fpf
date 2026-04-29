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
    hoje = date.today()
    if hoje.month >= 7:
        return hoje.year
    return hoje.year - 1

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
# QUERY PRINCIPAL (CORRIGIDA – LIMIT SE NÃO HOUVER FILTROS)
# ======================================================

def obter_jogadores(f):
    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT
            player_id,
            nome,
            data_nascimento,
            clube,
            escalao,
            ano_nascimento,
            distrito,
            naturalidade
        FROM jogadores
        WHERE 1=1
    """
    params = []

    tem_filtros = False

    if f["nome"]:
        query += " AND nome LIKE ?"
        params.append(f"%{f['nome']}%")
        tem_filtros = True

    if f["clube"]:
        query += " AND clube LIKE ?"
        params.append(f"%{f['clube']}%")
        tem_filtros = True

    if f["ano_nasc"].isdigit():
        query += " AND ano_nascimento = ?"
        params.append(int(f["ano_nasc"]))
        tem_filtros = True

    if f["distrito"]:
        query += f" AND distrito IN ({','.join(['?'] * len(f['distrito']))})"
        params.extend(f["distrito"])
        tem_filtros = True

    if f["naturalidade"]:
        query += f" AND naturalidade IN ({','.join(['?'] * len(f['naturalidade']))})"
        params.extend(f["naturalidade"])
        tem_filtros = True

    # ✅ CORREÇÃO DO ERRO 502 / OOM
    if not tem_filtros:
        query += " ORDER BY player_id DESC LIMIT 100"
    else:
        query += " ORDER BY player_id DESC"

    c.execute(query, params)
    rows = c.fetchall()
    conn.close()

    jogadores = []
    for r in rows:
        categoria = calcular_categoria_por_ano(r[5])

        if f["categoria"]:
            if not categoria or categoria not in f["categoria"]:
                continue

        if f["escalao_fpf"]:
            if not r[4] or r[4] not in f["escalao_fpf"]:
                continue

        jogadores.append((
            r[0],      # ID
            r[1],      # Nome
            r[2],      # Nascimento
            r[3],      # Clube
            r[4],      # Escalão
            categoria, # Categoria
            r[6],      # Distrito
            r[7],      # Naturalidade
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
    }

    jogadores = obter_jogadores(f)

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
# FICHA DO ATLETA
# ======================================================

@app.route("/jogador/<int:player_id>")
def ficha_jogador(player_id):
    if not session.get("autenticado"):
        return redirect("/login")

    conn = get_db()
    c = conn.cursor()

    c.execute("""
        SELECT
            player_id,
            nome,
            data_nascimento,
            clube,
            naturalidade,
            escalao
        FROM jogadores
        WHERE player_id = ?
    """, (player_id,))
    jogador = c.fetchone()

    if not jogador:
        conn.close()
        return "Jogador não encontrado", 404

    c.execute("""
        SELECT
            jogos,
            golos,
            competicao,
            epoca,
            ultima_atualizacao,
            zz_player_url
        FROM estatisticas_zerozero
        WHERE player_id = ?
    """, (player_id,))
    zz = c.fetchone()

    conn.close()

    return render_template(
        "jogador.html",
        jogador=jogador,
        zz=zz
    )

# ======================================================
# EXPORTAR
# ======================================================

@app.route("/exportar")
def exportar():
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
    }

    jogadores = obter_jogadores(f)

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