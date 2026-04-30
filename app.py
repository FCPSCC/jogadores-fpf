from flask import (
    Flask, render_template.secret_key = os.environ.get(    Flask, render_template, request, redirect,
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
# CATEGORIA FEDERATIVA (TEÓRICA)
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
    if not cat or not cat.startswith("Sub-"):
        return None
    try:
        return int(cat.replace("Sub-", ""))
    except:
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
# QUERY PRINCIPAL (COM ORDENAÇÃO)
# ======================================================

def obter_jogadores(f, sort_col, sort_dir):
    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT
            j.player_id,
            j.nome,
            j.data_nascimento,
            j.clube,
            j.escalao,
            j.ano_nascimento,
            j.distrito,
            j.naturalidade
        FROM jogadores j
        WHERE 1=1
    """
    params = []
    tem_filtros = False

    if f["nome"]:
        query += " AND j.nome LIKE ?"
        params.append(f"%{f['nome']}%")
        tem_filtros = True

    if f["clube"]:
        query += " AND j.clube LIKE ?"
        params.append(f"%{f['clube']}%")
        tem_filtros = True

    if f["ano_nasc"].isdigit():
        query += " AND j.ano_nascimento = ?"
        params.append(int(f["ano_nasc"]))
        tem_filtros = True

    if f["distrito"]:
        query += f" AND j.distrito IN ({','.join(['?'] * len(f['distrito']))})"
        params.extend(f["distrito"])
        tem_filtros = True

    if f["naturalidade"]:
        query += f" AND j.naturalidade IN ({','.join(['?'] * len(f['naturalidade']))})"
        params.extend(f["naturalidade"])
        tem_filtros = True

    # >>> PATCH PASSO 3 — filtro "A competir acima do escalão"
    if f.get("joga_acima"):
        query += """
            AND EXISTS (
                SELECT 1
                FROM participacao_epoca_atual p
                WHERE p.player_id = j.player_id
                  AND p.escalao > (? - j.ano_nascimento + 1)
            )
        """
        params.append(obter_ano_referencia_epoca())
        tem_filtros = True
    # <<< PATCH PASSO 3

    colunas_validas = {
        "player_id": "j.player_id",
        "nome": "j.nome",
        "data_nascimento": "j.data_nascimento",
        "clube": "j.clube",
        "escalao": "j.escalao",
        "categoria": "j.ano_nascimento",
        "distrito": "j.distrito",
        "naturalidade": "j.naturalidade"
    }

    coluna = colunas_validas.get(sort_col, "j.player_id")
    direcao = "ASC" if sort_dir == "asc" else "DESC"

    if not tem_filtros:
        query += f" ORDER BY {coluna} {direcao} LIMIT 100"
    else:
        query += f" ORDER BY {coluna} {direcao}"

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
            r[0], r[1], r[2], r[3],
            r[4], categoria, r[6], r[7]
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
        # >>> PATCH PASSO 3
        "joga_acima": request.args.get("joga_acima") == "1",
        # <<< PATCH PASSO 3
    }

    sort_col = request.args.get("sort", "player_id")
    sort_dir = request.args.get("dir", "desc")

    jogadores = obter_jogadores(f, sort_col, sort_dir)

    categorias = [f"Sub-{i}" for i in range(5, 20)] + ["Sénior"]

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT DISTINCT escalao FROM jogadores WHERE escalao IS NOT NULL AND escalao != ''")
    escalaoes_fpf = sorted([r[0] for r in c.fetchall()], key=ordem_escaloes_fpf)

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
# FICHA DO ATLETA (PASSO 2)
# ======================================================

# >>> PATCH PASSO 3 — correção da rota (HTML escapado)
@app.route("/jogador/<int:player_id>")
# <<< PATCH PASSO 3
def ficha_jogador(player_id):
    if not session.get("autenticado"):
        return redirect("/login")

    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
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
            zz_player_url,
            foto_url
        FROM estatisticas_zerozero
        WHERE player_id = ?
    """, (player_id,))
    zz = c.fetchone()

    c.execute("""
        SELECT
            modalidade,
            clube,
            escalao,
            escalao_texto,
            jogos,
            golos
        FROM participacao_epoca_atual
        WHERE player_id = ?
        ORDER BY escalao DESC
    """, (player_id,))
    participacao = c.fetchall()

    cat_teorica = calcular_categoria_por_ano(jogador["data_nascimento"].year)
    escalao_teorico = extrair_numero_escalao(cat_teorica)

    escalao_real_max = None
    if participacao:
        escalao_real_max = max(p["escalao"] for p in participacao)

    joga_acima = (
        escalao_teorico is not None
        and escalao_real_max is not None
        and escalao_real_max > escalao_teorico
    )

    conn.close()

    return render_template(
        "jogador.html",
        jogador=jogador,
        zz=zz,
        participacao=participacao,
        escalao_teorico=escalao_teorico,
        escalao_real_max=escalao_real_max,
        joga_acima=joga_acima
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

    jogadores = obter_jogadores(f, "player_id", "desc")

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

