from flask import (
    Flask, render_template, request, redirect,
    session, url_for
)
from datetime import date
import os
import re
import psycopg2
import psycopg2.extras

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "chave-temporaria-123")
SITE_PASSWORD = os.environ.get("SITE_PASSWORD", "MUDAR123")

def get_db():
    return psycopg2.connect(
        os.environ["DATABASE_URL"],
        cursor_factory=psycopg2.extras.RealDictCursor
    )

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
        SELECT player_id, nome, data_nascimento,
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
            r["player_id"], r["nome"], r["data_nascimento"],
            r["clube"], r["escalao"], categoria,
            r["distrito"], r["naturalidade"]
        ))

    cur.close()
    conn.close()

    return jogadores, total

# ✅ INDEX CORRIGIDO
@app.route("/")
def index():
    if not session.get("autenticado"):
        return redirect("/login")

    conn = get_db()
    cur = conn.cursor()

    # ✅ LISTAS PARA OS FILTROS
    cur.execute("SELECT DISTINCT distrito FROM jogadores ORDER BY distrito")
    distritos = [r["distrito"] for r in cur.fetchall() if r["distrito"]]

    cur.execute("SELECT DISTINCT naturalidade FROM jogadores ORDER BY naturalidade")
    naturalidades = [r["naturalidade"] for r in cur.fetchall() if r["naturalidade"]]

    cur.execute("SELECT DISTINCT escalao FROM jogadores ORDER BY escalao")
    escalaoes_fpf = [r["escalao"] for r in cur.fetchall() if r["escalao"]]

    categorias = [f"Sub-{i}" for i in range(6, 20)] + ["Sénior"]

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

    cur.close()
    conn.close()

    return render_template(
        "index.html",
        jogadores=jogadores,
        total=total,
        filtros=request.args,
        page=page,
        categorias=categorias,
        escalaoes_fpf=escalaoes_fpf,
        distritos=distritos,
        naturalidades=naturalidades
    )

# ✅ FICHA JOGADOR CORRIGIDA
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
        SELECT e.epoca, e.competicao, e.jogos, e.golos
        FROM estatisticas_zerozero e
        JOIN match_zerozero_fpf m
            ON e.player_id = m.id_zerozero_atleta
        WHERE m.player_id_fpf = %s
        ORDER BY e.epoca DESC
    """, (player_id,))

    rows = cur.fetchall()

    cur.execute("""
        SELECT z.foto_url
        FROM match_zerozero_fpf m
        JOIN zerozero_atleta z
            ON m.id_zerozero_atleta = z.id_zerozero_atleta
        WHERE m.player_id_fpf = %s
        LIMIT 1
    """, (player_id,))

    foto = cur.fetchone()
    foto_url = foto["foto_url"] if foto else None

    escalao_teorico = obter_ano_referencia_epoca() - jogador["ano_nascimento"] + 1

    historico_formatado = []

    for row in rows:
        match = re.search(r"S(\d+)", row["competicao"])
        escalao_encontrado = int(match.group(1)) if match else None

        acima = False
        if (
            row["epoca"] == "2025/26"
            and escalao_encontrado
            and escalao_teorico <= 19
            and escalao_encontrado > escalao_teorico
        ):
            acima = True

        # 🧠 IGNORAR SENIORES
        if "Seniores" in row["competicao"]:
            acima = False

        historico_formatado.append({
            "epoca": row["epoca"],
            "competicao": row["competicao"],
            "jogos": row["jogos"] or 0,
            "golos": row["golos"] or 0,
            "acima": acima
        })

    cur.close()
    conn.close()

    return render_template(
        "jogador.html",
        jogador=jogador,
        historico_zz=historico_formatado,
        escalao_teorico=escalao_teorico,
        foto_url=foto_url
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)