from flask import (
    Flask, render_template, request, redirect,
    session, url_for, Response
)
from io import StringIO
from datetime import date
import os
import csv

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

def garantir_tabela_jogadores():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS jogadores (
            player_id INTEGER PRIMARY KEY,
            nome TEXT,
            data_nascimento DATE,
            ano_nascimento INTEGER,
            clube TEXT,
            escalao TEXT,
            distrito TEXT,
            naturalidade TEXT
        )
    """)

    conn.commit()
    cur.close()
    conn.close()

def garantir_tabela_estatisticas_zerozero():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS estatisticas_zerozero (
            id SERIAL PRIMARY KEY,
            player_id INTEGER,
            jogos INTEGER,
            golos INTEGER,
            competicao TEXT,
            epoca TEXT,
            ultima_atualizacao TEXT,
            zz_player_url TEXT,
            foto_url TEXT
        )
    """)

    conn.commit()
    cur.close()
    conn.close()


# ======================================================
# ÉPOCA ATUAL
# ======================================================

def obter_ano_referencia_epoca():
    hoje = date.today()
    return hoje.year if hoje.month >= 7 else hoje.year - 1

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

def extrair_numero_escalao(cat):
    if cat and cat.startswith("Sub-"):
        return int(cat.replace("Sub-", ""))
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
# QUERY PRINCIPAL
# ======================================================

def obter_jogadores(f, sort_col, sort_dir):
    conn = get_db()
    c = conn.cursor()

    query = """
        SELECT
            j.player_id, j.nome, j.data_nascimento,
            j.clube, j.escalao, j.ano_nascimento,
            j.distrito, j.naturalidade
        FROM jogadores j
        WHERE 1=1
    """
    params = []
    tem_filtros = False

    if f["nome"]:
        query += " AND j.nome ILIKE %s"
        params.append(f"%{f['nome']}%")
        tem_filtros = True

    if f["clube"]:
        query += " AND j.clube ILIKE %s"
        params.append(f"%{f['clube']}%")
        tem_filtros = True

    if f["ano_nasc"].isdigit():
        query += " AND j.ano_nascimento = %s"
        params.append(int(f["ano_nasc"]))
        tem_filtros = True

    if f["distrito"]:
        query += " AND j.distrito = ANY(%s)"
        params.append(f["distrito"])
        tem_filtros = True

    if f["naturalidade"]:
        query += " AND j.naturalidade = ANY(%s)"
        params.append(f["naturalidade"])
        tem_filtros = True

    if f.get("joga_acima"):
        query += """
            AND EXISTS (
                SELECT 1
                FROM participacao_epoca_atual p
                WHERE p.player_id = j.player_id
                  AND p.escalao > (%s - j.ano_nascimento + 1)
            )
        """
        params.append(obter_ano_referencia_epoca())
        tem_filtros = True

    coluna = sort_col if sort_col in [
        "player_id", "nome", "data_nascimento", "clube",
        "escalao", "ano_nascimento", "distrito", "naturalidade"
    ] else "player_id"

    direcao = "ASC" if sort_dir == "asc" else "DESC"

    query += f" ORDER BY j.{coluna} {direcao}"
    if not tem_filtros:
        query += " LIMIT 100"

    c.execute(query, params)
    rows = c.fetchall()

    c.close()
    conn.close()

    jogadores = []
    for r in rows:
        categoria = calcular_categoria_por_ano(r["ano_nascimento"])
        jogadores.append((
            r["player_id"], r["nome"], r["data_nascimento"],
            r["clube"], r["escalao"], categoria,
            r["distrito"], r["naturalidade"]
        ))

    return jogadores

# ======================================================
# INDEX
# ======================================================

@app.route("/")
def index():
    if not session.get("autenticado"):
        return redirect("/login")

    garantir_tabela_participacao()
garantir_tabela_jogadores()
garantir_tabela_estatisticas_zerozero()

    f = {
        "nome": request.args.get("nome", ""),
        "clube": request.args.get("clube", ""),
        "ano_nasc": request.args.get("ano_nasc", ""),
        "categoria": request.args.getlist("categoria"),
        "escalao_fpf": request.args.getlist("escalao_fpf"),
        "distrito": request.args.getlist("distrito"),
        "naturalidade": request.args.getlist("naturalidade"),
        "joga_acima": request.args.get("joga_acima") == "1"
    }

    sort_col = request.args.get("sort", "player_id")
    sort_dir = request.args.get("dir", "desc")

    jogadores = obter_jogadores(f, sort_col, sort_dir)

    conn = get_db()
    c = conn.cursor()

    c.execute("SELECT DISTINCT escalao FROM jogadores WHERE escalao IS NOT NULL AND escalao != ''")
    escalaoes_fpf = sorted([r["escalao"] for r in c.fetchall()], key=lambda x: ordem_escaloes_fpf(x))

    c.execute("SELECT DISTINCT distrito FROM jogadores WHERE distrito IS NOT NULL")
    distritos = sorted(r["distrito"] for r in c.fetchall())

    c.execute("SELECT DISTINCT naturalidade FROM jogadores WHERE naturalidade IS NOT NULL")
    naturalidades = sorted(r["naturalidade"] for r in c.fetchall())

    c.close()
    conn.close()

    categorias = [f"Sub-{i}" for i in range(5, 20)] + ["Sénior"]

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

@app.route("/admin/import-jogadores")
def admin_import_jogadores():
    if request.args.get("key") != SITE_PASSWORD:
        return "Acesso negado", 403

    garantir_tabela_jogadores()

    conn = get_db()
    cur = conn.cursor()

    with open("jogadores.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cur.execute("""
                INSERT INTO jogadores
                (player_id, nome, data_nascimento, ano_nascimento, clube, escalao, distrito, naturalidade)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (player_id) DO NOTHING
            """, (
                int(row["player_id"]),
                row["nome"],
                row["data_nascimento"],
                int(row["ano_nascimento"]),
                row["clube"],
                row["escalao"],
                row["distrito"],
                row["naturalidade"]
            ))

    conn.commit()
    cur.close()
    conn.close()

    return "Jogadores importados ✅"

@app.route("/admin/import-zz")
def admin_import_zz():
    if request.args.get("key") != SITE_PASSWORD:
        return "Acesso negado", 403

    garantir_tabela_estatisticas_zerozero()

    conn = get_db()
    cur = conn.cursor()

    with open("estatisticas_zerozero.csv", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cur.execute("""
                INSERT INTO estatisticas_zerozero
                (player_id, jogos, golos, competicao, epoca, ultima_atualizacao, zz_player_url, foto_url)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                int(row["player_id"]),
                int(row["jogos"]),
                int(row["golos"]),
                row["competicao"],
                row["epoca"],
                row["ultima_atualizacao"],
                row["zz_player_url"],
                row["foto_url"]
            ))

    conn.commit()
    cur.close()
    conn.close()

    return "Estatísticas ZeroZero importadas ✅"

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
        SELECT player_id, nome, data_nascimento, ano_nascimento,
               clube, naturalidade, escalao
        FROM jogadores
        WHERE player_id = %s
    """, (player_id,))
    jogador = c.fetchone()

    if not jogador:
        c.close()
        conn.close()
        return "Jogador não encontrado", 404

    c.execute("""
        SELECT jogos, golos, competicao, epoca,
               ultima_atualizacao, zz_player_url, foto_url
        FROM estatisticas_zerozero
        WHERE player_id = %s
    """, (player_id,))
    zz = c.fetchone()

    c.execute("""
        SELECT modalidade, clube, escalao, escalao_texto, jogos, golos
        FROM participacao_epoca_atual
        WHERE player_id = %s
        ORDER BY escalao DESC
    """, (player_id,))
    participacao = c.fetchall()

    c.close()
    conn.close()

    cat_teorica = calcular_categoria_por_ano(jogador["ano_nascimento"])
    escalao_teorico = extrair_numero_escalao(cat_teorica)
    escalao_real_max = max((p["escalao"] for p in participacao), default=None)

    joga_acima = (
        escalao_teorico is not None
        and escalao_real_max is not None
        and escalao_real_max > escalao_teorico
    )

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

    jogadores = obter_jogadores({}, "player_id", "desc")

    output = StringIO()
    writer = csv.writer(output, delimiter=";")

    writer.writerow([
        "ID","Nome","Nascimento","Clube",
        "Escalão","Categoria","Distrito","Naturalidade","FPF"
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
# ADMIN IMPORT
# ======================================================

@app.route("/admin/import")
def admin_import():
    if request.args.get("key") != os.environ.get("SITE_PASSWORD", "MUDAR123"):
        return "Acesso negado", 403

    try:
        garantir_tabela_participacao()

        ficheiro = "participacao_epoca_atual.csv"
        if not os.path.exists(ficheiro):
            return f"ERRO: ficheiro '{ficheiro}' não encontrado", 500

        conn = get_db()
        c = conn.cursor()

        with open(ficheiro, newline="", encoding="utf-8") as csvfile:
            reader = csv.DictReader(csvfile)
            linhas = 0
            for row in reader:
                c.execute("""
                    INSERT INTO participacao_epoca_atual
                    (player_id, modalidade, clube, escalao, escalao_texto, jogos, golos)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    int(row["player_id"]),
                    row["modalidade"],
                    row["clube"],
                    int(row["escalao"]),
                    row["escalao_texto"],
                    int(row["jogos"]),
                    int(row["golos"])
                ))
                linhas += 1

        conn.commit()
        c.close()
        conn.close()

        return f"Importação concluída ✅ ({linhas} linhas inseridas)"

    except Exception as e:
        return f"ERRO NA IMPORTAÇÃO: {type(e).__name__}: {e}", 500

# ======================================================
# RUN
# ======================================================

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)