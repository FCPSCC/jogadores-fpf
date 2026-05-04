from flask import (
    Flask, render_template, request, redirect,
    session, url_for
)
from datetime import date
import os
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

# ======================================================
# ÉPOCA / CATEGORIA
# ======================================================

def obter_ano_referencia_epoca():
    hoje = date.today()
    return hoje.year if hoje.month >= 7 else hoje.year - 1

def calcular_categoria_por_ano(ano_nascimento):
    if not ano_nascimento:
        return None

    sub = obter_ano_referencia_epoca() - ano_nascimento + 1

    if sub < 5:
        return None
    if sub <= 19:
        return f"Sub-{sub}"
    return "Sénior"

def extrair_numero_escalao(cat):
    if cat and cat.startswith("Sub-"):
        return int(cat.replace("Sub-", ""))
    return None

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
# LISTAS PARA FILTROS (DROPDOWNS)
# ======================================================

def obter_listas_filtros():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT escalao FROM jogadores WHERE escalao IS NOT NULL")
    escalaoes = sorted(
        [r["escalao"] for r in cur.fetchall()],
        key=ordem_escaloes_fpf
    )

    cur.execute("SELECT DISTINCT distrito FROM jogadores WHERE distrito IS NOT NULL ORDER BY distrito")
    distritos = [r["distrito"] for r in cur.fetchall()]

    cur.execute("SELECT DISTINCT naturalidade FROM jogadores WHERE naturalidade IS NOT NULL ORDER BY naturalidade")
    naturalidades = [r["naturalidade"] for r in cur.fetchall()]

    cur.close()
    conn.close()

    categorias = [f"Sub-{i}" for i in range(5, 20)] + ["Sénior"]

    return categorias, escalaoes, distritos, naturalidades

# ======================================================
# QUERY PRINCIPAL (SEMPRE LIMITADA)
# ======================================================

def obter_jogadores(f, sort_col, sort_dir, offset=0):
    conn = get_db()
    cur = conn.cursor()

    query = """
        SELECT
            player_id, nome, data_nascimento,
            clube, escalao, ano_nascimento,
            distrito, naturalidade
        FROM jogadores
        WHERE 1=1
    """
    params = []

    if f.get("nome"):
        query += " AND nome ILIKE %s"
        params.append(f"%{f['nome']}%")

    if f.get("clube"):
        query += " AND clube ILIKE %s"
        params.append(f"%{f['clube']}%")

    if f.get("ano_nasc"):
        query += " AND ano_nascimento = %s"
        params.append(int(f["ano_nasc"]))

    if f.get("distrito"):
        query += " AND distrito = %s"
        params.append(f["distrito"])

    if f.get("naturalidade"):
        query += " AND naturalidade = %s"
        params.append(f["naturalidade"])

    coluna = sort_col if sort_col in [
        "player_id", "nome", "data_nascimento",
        "clube", "escalao", "ano_nascimento"
    ] else "player_id"

    direcao = "ASC" if sort_dir == "asc" else "DESC"

    query += f" ORDER BY {coluna} {direcao} LIMIT 100 OFFSET %s"
    params.append(offset)

    cur.execute(query, params)
    rows = cur.fetchall()

    cur.close()
    conn.close()

    jogadores = []
    for r in rows:
        categoria = calcular_categoria_por_ano(r["ano_nascimento"])
        jogadores.append((
            r["player_id"],          # 0
            r["nome"],               # 1
            r["data_nascimento"],    # 2
            r["clube"],              # 3
            r["escalao"],            # 4
            categoria,               # 5 categoria teórica
            r["distrito"],           # 6
            r["naturalidade"]        # 7
        ))

    return jogadores

# ======================================================
# INDEX (SEM OOM)
# ======================================================

@app.route("/")
def index():
    if not session.get("autenticado"):
        return redirect("/login")

    f = {
        "nome": request.args.get("nome", "").strip(),
        "clube": request.args.get("clube", "").strip(),
        "ano_nasc": request.args.get("ano_nasc", "").strip(),
        "distrito": request.args.get("distrito", "").strip(),
        "naturalidade": request.args.get("naturalidade", "").strip()
    }

    sort_col = request.args.get("sort", "player_id")
    sort_dir = request.args.get("dir", "desc")
    page = int(request.args.get("page", 0))
    offset = page * 100

    jogadores = []
    tem_filtros = any(v for v in f.values())

    if tem_filtros:
        jogadores = obter_jogadores(f, sort_col, sort_dir, offset)

    categorias, escalaoes, distritos, naturalidades = obter_listas_filtros()

    return render_template(
        "index.html",
        jogadores=jogadores,
        filtros=f,
        categorias=categorias,
        escalaoes_fpf=escalaoes,
        distritos=distritos,
        naturalidades=naturalidades,
        page=page
    )

# ======================================================
# FICHA INDIVIDUAL
# ======================================================

@app.route("/jogador/<int:player_id>")
def ficha_jogador(player_id):
    if not session.get("autenticado"):
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT * FROM jogadores WHERE player_id = %s", (player_id,))
    jogador = cur.fetchone()

    if not jogador:
        return "Jogador não encontrado", 404

    cur.execute("""
        SELECT escalao
        FROM participacao_epoca_atual
        WHERE player_id = %s
    """, (player_id,))
    participacoes = [r["escalao"] for r in cur.fetchall()]

    cur.close()
    conn.close()

    cat_teorica = calcular_categoria_por_ano(jogador["ano_nascimento"])
    escalao_teorico = extrair_numero_escalao(cat_teorica)
    escalao_real_max = max(participacoes) if participacoes else None

    joga_acima = (
        escalao_teorico is not None
        and escalao_real_max is not None
        and escalao_real_max > escalao_teorico
    )

    return render_template(
        "jogador.html",
        jogador=jogador,
        escalao_teorico=escalao_teorico,
        escalao_real_max=escalao_real_max,
        joga_acima=joga_acima
    )

# ======================================================
# RUN
# ======================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)