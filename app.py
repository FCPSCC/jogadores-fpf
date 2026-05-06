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
# FUNÇÕES AUXILIARES
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

def normalizar_escalao(txt):
    if not txt:
        return txt
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

def obter_jogadores(f, sort_col, sort_dir, offset):
    conn = get_db()
    cur = conn.cursor()

    base_where = " WHERE 1=1 "
    filtros_sql = ""
    params = []

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

    if f.get("categoria") and f["categoria"].startswith("Sub-"):
        sub = int(f["categoria"].replace("Sub-", ""))
        ano_ref = obter_ano_referencia_epoca() - sub + 1
        filtros_sql += " AND ano_nascimento = %s"
        params.append(ano_ref)

    if f.get("distrito"):
        filtros_sql += " AND distrito = %s"
        params.append(f["distrito"])

    if f.get("naturalidade"):
        filtros_sql += " AND naturalidade = %s"
        params.append(f["naturalidade"])

    if f.get("escalao"):
        filtros_sql += " AND escalao = %s"
        params.append(f["escalao"])

    if f.get("acima_escalao") == "1":
        filtros_sql += " AND player_id IN (SELECT player_id FROM participacao_epoca_atual)"

    # TOTAL
    cur.execute(
        "SELECT COUNT(*) AS total FROM jogadores" + base_where + filtros_sql,
        params
    )
    total = cur.fetchone()["total"]

    # QUERY PRINCIPAL
    query = f"""
        SELECT
            player_id, nome, data_nascimento,
            clube, escalao, ano_nascimento,
            distrito, naturalidade
        FROM jogadores
        {base_where}
        {filtros_sql}
        ORDER BY player_id DESC
        LIMIT 100 OFFSET %s
    """

    cur.execute(query, params + [offset])
    rows = cur.fetchall()

    jogadores = []
    for r in rows:
        jogadores.append((
            r["player_id"],
            r["nome"],
            r["data_nascimento"],
            r["clube"],
            r["escalao"],
            r["ano_nascimento"],
            r["distrito"],
            r["naturalidade"]
        ))

    cur.close()
    conn.close()

    return jogadores, total

def obter_listas_filtros():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("SELECT DISTINCT escalao FROM jogadores WHERE escalao IS NOT NULL")
    escalaoes_raw = [r["escalao"] for r in cur.fetchall()]

    escalaoes = sorted(list(set(escalaoes_raw)))

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
        "escalao": request.args.get("escalao_fpf", "").strip(),
        "acima_escalao": request.args.get("acima_escalao", "")
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

    cur.execute(
        "SELECT * FROM jogadores WHERE player_id = %s",
        (player_id,)
    )
    jogador = cur.fetchone()
    if not jogador:
        return "Jogador não encontrado", 404

    cur.execute("""
        SELECT e.jogos, e.golos, e.competicao, e.epoca,
           e.ultima_atualizacao, e.zz_player_url, e.foto_url
        FROM estatisticas_zerozero e
        JOIN match_zerozero_fpf m
        ON e.player_id = m.id_zerozero_atleta
        WHERE m.player_id_fpf = %s
    """, (player_id,))
    zz = cur.fetchall()

    cur.execute("""
        SELECT total_jogos, total_golos, foto_url, joga_acima
        FROM vw_atleta_zerozero_resumo
        WHERE player_id = %s
    """, (player_id,))
    resumo_zz = cur.fetchone()

    cur.execute("""
    SELECT e.epoca, e.competicao, e.jogos, e.golos
    FROM estatisticas_zerozero e
    JOIN match_zerozero_fpf m
        ON e.player_id = m.id_zerozero_atleta
    WHERE m.player_id_fpf = %s
    ORDER BY e.epoca DESC, e.competicao
""", (player_id,))
rows = cur.fetchall()

historico_formatado = []
epoca_anterior = None

for row in rows:
    epoca = row["epoca"]

    if epoca != epoca_anterior:
        epoca_mostrar = epoca
        epoca_anterior = epoca
    else:
        epoca_mostrar = ""

    escalao_encontrado = None
    match = re.search(r"S(\d+)", row["competicao"])
    if match:
        escalao_encontrado = int(match.group(1))

    acima = False
    if (
        epoca == "2025/26" and
        escalao_encontrado is not None and
        escalao_teorico is not None and
        escalao_encontrado > escalao_teorico
    ):
        acima = True

    historico_formatado.append({
        "epoca": epoca_mostrar,
        "competicao": row["competicao"],
        "jogos": row["jogos"],
        "golos": row["golos"],
        "acima": acima
    })

import re

    for row in rows:
    texto = row["competicao"]

    escalao_encontrado = None
    match = re.search(r"S(\d+)", texto)
    if match:
        escalao_encontrado = int(match.group(1))

    row["acima"] = False

    if row["epoca"] == "2025/26" and escalao_encontrado and escalao_teorico:
        if escalao_encontrado > escalao_teorico:
            row["acima"] = True


        historico_formatado.append({
            "epoca": epoca_mostrar,
            "competicao": row["competicao"],
            "jogos": row["jogos"],
            "golos": row["golos"]
        })

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
        historico_zz=historico_formatado,
        participacao=participacao,
        escalao_teorico=escalao_teorico,
        escalao_real_max=escalao_real_max,
        joga_acima=joga_acima
    )


print("AAAA TESTE GIT")


# ======================================================
# RUN
# ======================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)