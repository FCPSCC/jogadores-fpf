import os
import psycopg2

# ======================================================
# SCRIPT PARA CRIAR AS TABELAS ZEROZERO
# ======================================================

SQL = """
-- =====================================================
-- TABELA: zerozero_equipa
-- Representa uma equipa concreta (clube + escalão + época)
-- =====================================================

CREATE TABLE IF NOT EXISTS zerozero_equipa (
    id_zerozero_equipa     INTEGER PRIMARY KEY,
    nome_equipa            TEXT NOT NULL,
    clube                  TEXT NOT NULL,
    escalao                TEXT,
    epoca                  TEXT,
    url_zerozero           TEXT,
    ultima_atualizacao     TIMESTAMP DEFAULT NOW()
);

-- =====================================================
-- TABELA: zerozero_atleta
-- Representa um atleta único no universo ZeroZero
-- =====================================================

CREATE TABLE IF NOT EXISTS zerozero_atleta (
    id_zerozero_atleta     INTEGER PRIMARY KEY,
    nome_completo          TEXT NOT NULL,
    url_zerozero           TEXT
);

-- =====================================================
-- TABELA: zerozero_plantel
-- Representa a participação de um atleta numa equipa
-- =====================================================

CREATE TABLE IF NOT EXISTS zerozero_plantel (
    id                     SERIAL PRIMARY KEY,

    id_zerozero_equipa     INTEGER NOT NULL
        REFERENCES zerozero_equipa (id_zerozero_equipa)
        ON DELETE CASCADE,

    id_zerozero_atleta     INTEGER NOT NULL
        REFERENCES zerozero_atleta (id_zerozero_atleta)
        ON DELETE CASCADE,

    nome_atleta            TEXT NOT NULL,
    clube                  TEXT NOT NULL,
    escalao                TEXT,
    epoca                  TEXT,

    posicao                TEXT,
    numero_camisola        INTEGER,

    origem                 TEXT DEFAULT 'plantel',
    confianca_origem       INTEGER DEFAULT 100,

    ultima_atualizacao     TIMESTAMP DEFAULT NOW(),

    UNIQUE (id_zerozero_equipa, id_zerozero_atleta)
);

-- =====================================================
-- TABELA: match_zerozero_fpf
-- Liga atletas ZeroZero a atletas FPF com score
-- =====================================================

CREATE TABLE IF NOT EXISTS match_zerozero_fpf (
    id                      SERIAL PRIMARY KEY,

    id_zerozero_atleta      INTEGER NOT NULL
        REFERENCES zerozero_atleta (id_zerozero_atleta)
        ON DELETE CASCADE,

    player_id_fpf           INTEGER NOT NULL
        REFERENCES jogadores (player_id)
        ON DELETE CASCADE,

    score_confianca         INTEGER NOT NULL,
    metodo                  TEXT NOT NULL,
    estado                  TEXT NOT NULL CHECK (
        estado IN ('confirmado', 'pendente', 'rejeitado')
    ),

    data_match              TIMESTAMP DEFAULT NOW(),

    UNIQUE (id_zerozero_atleta)
);
"""

def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL não definida nas variáveis de ambiente")

    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    cur.execute(SQL)

    conn.commit()
    cur.close()
    conn.close()

    print("✅ Tabelas ZeroZero criadas com sucesso.")

# ======================================================
# ENTRY POINT
# ======================================================

if __name__ == "__main__":
    main()