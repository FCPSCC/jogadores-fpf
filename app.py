from flask import (
    Flask, render_template, request, redirect,
    session, url_for
)
from datetime import date
import os
import re
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
# ÉPOCA / CATEGORIAS
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
# NORMALIZAÇÃO DE ESCALÃO FPF
# ======================================================

def normalizar_escalao(txt):
    if not txt:
        return txt
    # remove espaço antes do parêntesis
    return re.sub(r"\s+\(", "(", txt)

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
# LISTAS PARA FILTROS
# ======================================================

def obter_listas_filtros():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT escalao FROM jogadores WHERE escalao IS NOT NULL")
    escalaoes_raw = [r["escalao"] for r in cur.fetchall()]

    escalaoes = sorted(
        list({normalizar_escalao(e) for e in escalaoes_raw}),
        key=ordem_escaloes_fpf
    )

    cur.execute("""
        SELECT DISTINCT distrito
        FROM jogadores
        WHERE distrito IS NOT NULL
        ORDER BY distrito
    """)
    distritos = [r["distrito"] for r in cur.fetchall()]

    cur.execute("""
        SELECT DISTINCT naturalidade
        FROM jogadores
        WHERE naturalidade IS NOT NULL
        ORDER BY naturalidade
    """)
    naturalidades = [r["naturalidade"] for r in cur.fetchall()]

    cur.close()
    conn.close()

    categorias = [f"Sub-{i}" for i in range(5, 20)] + ["Sénior"]

    return categorias, escalaoes, distritos, naturalidades

# ======================================================
# QUERY PRINCIPAL (LISTAGEM + TOTAL)
# ======================================================

def obter_jogadores(f, sort_col, sort_dir, offset):
    conn = get_db()
    cur = conn.cursor()

    base_where = " WHERE 1=1 "
    filtros_sql = ""
    params = []

    # Nome por termos
    if f.get("nome"):
        for termo in f["nome"].split():
            filtros_sql += " AND nome ILIKE %s"
            params.append(f"%{termo}%")

    if f.get("clube"):
        filtros_sql += " AND clube ILIKE %s"
        params.append(f"%{f['clube']}%")

    if f.get("ano_nasc"):
        filtros_sql += " AND ano_nascimento = %s"
        params.append(int(f["ano_nasc"]))

    if f.get("distrito"):
        filtros_sql += " AND distrito = %s"
        params.append(f["distrito"])

    if f.get("naturalidade"):
        filtros_sql += " AND naturalidade = %s"
        params.append(f["naturalidade"])

    if f.get("escalao"):
        filtros_sql += " AND REPLACE(escalao, ' (', '(') = %s"
        params.append(f["escalao"])

    if f.get("categoria") and f["categoria"].startswith("Sub-"):
        sub = int(f["categoria"].replace("Sub-", ""))
        ano_ref = obter_ano_referencia_epoca() - sub + 1
        filtros_sql += " AND ano_nascimento = %s"
        params.append(ano_ref)

    # TOTAL (sem LIMIT)
    count_query = "SELECT COUNT(*) AS total FROM jogadores" + base_where + filtros_sql
    cur.execute(count_query, params)
    total = cur.fetchone()["total"]

    # ORDENAÇÃO
    coluna = sort_col if sort_col in [
        "player_id", "nome", "data_nascimento",
        "clube", "escalao", "ano_nascimento"
    ] else "player_id"

    direcao = "ASC" if sort_dir == "asc" else "DESC"

    if coluna == "clube":
        order_clause = f" ORDER BY LOWER(clube) {direcao}"
    else:
        order_clause = f" ORDER BY {coluna} {direcao}"

    # QUERY PRINCIPAL COM LIMIT
    query = f"""
        SELECT
            player_id, nome, data_nascimento,
            clube, escalao, ano_nascimento,
            distrito, naturalidade
        FROM jogadores
        {base_where}
        {filtros_sql}
        {order_clause}
        LIMIT 100 OFFSET %s
    """
    cur.execute(query, params + [offset])
    rows = cur.fetchall()

    cur.close()
    conn.close()

    jogadores = []
    for r in rows:
        categoria = calcular_categoria_por_ano(r["ano_nascimento"])
        jogadores.append((
            r["player_id"],                # ID
            r["nome"],
            r["data_nascimento"],
            r["clube"],
            normalizar_escalao(r["escalao"]),
            categoria,
            r["distrito"],
            r["naturalidade"]
        ))

    return jogadores, total

# ======================================================
# INDEX
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
        "naturalidade": request.args.get("naturalidade", "").strip(),
        "categoria": request.args.get("categoria", "").strip(),
        "escalao": request.args.get("escalao_fpf", "").strip()
    }

    sort_col = request.args.get("sort", "player_id")
    sort_dir = request.args.get("dir", "desc")
    page = int(request.args.get("page", 0))
    offset = page * 100

    jogadores = []
    total = 0

    if any(v for v in f.values()):
        jogadores, total = obter_jogadores(f, sort_col, sort_dir, offset)

    categorias, escalaoes, distritos, naturalidades = obter_listas_filtros()

    return render_template(
        "index.html",
        jogadores=jogadores,
        total=total,
        filtros=f,
        categorias=categorias,
        escalaoes_fpf=escalaoes,
        distritos=distritos,
        naturalidades=naturalidades,
        page=page
    )

# ======================================================
# FICHA DO JOGADOR
# ======================================================

@app.route("/jogador/<int:player_id>")
def ficha_jogador(player_id):
    if not session.get("autenticado"):
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    # Dados base
    cur.execute("SELECT * FROM jogadores WHERE player_id = %s", (player_id,))
    jogador = cur.fetchone()
    if not jogador:
        return "Jogador não encontrado", 404

    # ZeroZero
    cur.execute("""
        SELECT jogos, golos, competicao, epoca,
               ultima_atualizacao, zz_player_url, foto_url
        FROM estatisticas_zerozero
        WHERE player_id = %s
    """, (player_id,))
    zz = cur.fetchone()

# ✅ NOVO — resumo agregado
cur.execute("""
    SELECT total_jogos, total_golos, foto_url, joga_acima
    FROM vw_atleta_zerozero_resumo
    WHERE player_id = %s
""", (player_id,))
resumo_zz = cur.fetchone()

# ✅ NOVO — histórico completo
cur.execute("""
    SELECT epoca, competicao, jogos, golos
    FROM vw_atleta_zerozero_historico
    WHERE player_id = %s
""", (player_id,))
historico_zz = cur.fetchall()

    # Histórico competitivo
    cur.execute("""
        SELECT modalidade, clube, escalao,
               escalao_texto, jogos, golos
        FROM participacao_epoca_atual
        WHERE player_id = %s
        ORDER BY escalao DESC, jogos DESC
    """, (player_id,))
    participacao = cur.fetchall()

    cur.close()
    conn.close()

    cat_teorica = calcular_categoria_por_ano(jogador["ano_nascimento"])
    escalao_teorico = extrair_numero_escalao(cat_teorica)

    escalao_real_max = max(
        (p["escalao"] for p in participacao),
        default=None
    )

    joga_acima = (
        escalao_teorico is not None
        and escalao_real_max is not None
        and escalao_real_max > escalao_teorico
    )

    return render_template(
        "jogador.html",
        jogador=jogador,
        zz=zz,
	resumo_zz=resumo_zz,
	historico_zz=historico_zz,
        participacao=participacao,
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