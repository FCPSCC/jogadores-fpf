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

# ======================================================
# OBTER JOGADORES
# ======================================================

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
        filtros_sql += """
            AND player_id IN (
                SELECT m.player_id_fpf
                FROM estatisticas_zerozero e
                JOIN match_zerozero_fpf m
                    ON e.player_id = m.id_zerozero_atleta
                WHERE e.epoca = '2025/26'
            )
        """

    cur.execute(
        "SELECT COUNT(*) AS total FROM jogadores" + base_where + filtros_sql,
        params
    )
    total = cur.fetchone()["total"]

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
        categoria = calcular_categoria_por_ano(r["ano_nascimento"])

        jogadores.append((
            r["player_id"],
            r["nome"],
            r["data_nascimento"],
            r["clube"],
            r["escalao"],
            categoria,
            r["distrito"],
            r["naturalidade"]
        ))

    cur.close()
    conn.close()

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
        "escalao": request.args.get("escalao_fpf", "").strip(),
        "acima_escalao": request.args.get("acima_escalao", "")
    }

    page = int(request.args.get("page", 0))
    offset = page * 100

    jogadores = []
    total = 0

    if any(v for v in f.values()):
        jogadores, total = obter_jogadores(f, "player_id", "desc", offset)

    return render_template(
        "index.html",
        jogadores=jogadores,
        total=total,
        filtros=f,
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

    # Jogador
    cur.execute(
        "SELECT * FROM jogadores WHERE player_id = %s",
        (player_id,)
    )
    jogador = cur.fetchone()

    if not jogador:
        return "Jogador não encontrado", 404

    # Histórico
    cur.execute("""
        SELECT e.epoca, e.competicao, e.jogos, e.golos
        FROM estatisticas_zerozero e
        JOIN match_zerozero_fpf m
            ON e.player_id = m.id_zerozero_atleta
        WHERE m.player_id_fpf = %s
        ORDER BY e.epoca DESC, e.competicao
    """, (player_id,))
    rows = cur.fetchall()

    # Flag época atual (corrigido)
    tem_epoca_atual = any(
        r["epoca"] == "2025/26" and ((r.get("jogos") or 0) > 0 or (r.get("golos") or 0) > 0)
        for r in rows
    )

    # Escalão teórico
    escalao_teorico = obter_ano_referencia_epoca() - jogador["ano_nascimento"] + 1

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
            epoca == "2025/26"
            and escalao_encontrado is not None
            and escalao_encontrado > escalao_teorico
        ):
            acima = True

        historico_formatado.append({
            "epoca": epoca_mostrar,
            "competicao": row["competicao"],
            "jogos": row["jogos"] or 0,
            "golos": row["golos"] or 0,
            "acima": acima
        })

    # Foto (ANTES de fechar cursor ✅)
    cur.execute("""
        SELECT foto_url
        FROM estatisticas_zerozero e
        JOIN match_zerozero_fpf m
            ON e.player_id = m.id_zerozero_atleta
        WHERE m.player_id_fpf = %s
        LIMIT 1
    """, (player_id,))
    foto = cur.fetchone()
    foto_url = foto["foto_url"] if foto else None

    # ✅ FECHAR AQUI (dentro da função)
    cur.close()
    conn.close()

    return render_template(
        "jogador.html",
        jogador=jogador,
        historico_zz=historico_formatado,
        escalao_teorico=escalao_teorico,
        tem_epoca_atual=tem_epoca_atual,
        foto_url=foto_url
    )


# ======================================================
# RUN
# ======================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)