import os
import psycopg2

SQL = """
CREATE TABLE IF NOT EXISTS clube_zerozero_base (
    id SERIAL PRIMARY KEY,

    clube_fpf TEXT NOT NULL,
    id_zerozero_equipa_base INTEGER NOT NULL,
    url_zerozero_base TEXT NOT NULL,

    ativo BOOLEAN DEFAULT TRUE,
    criado_em TIMESTAMP DEFAULT NOW(),

    UNIQUE (clube_fpf),
    UNIQUE (id_zerozero_equipa_base)
);
"""

def main():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL não definida")

    conn = psycopg2.connect(database_url)
    cur = conn.cursor()

    cur.execute(SQL)
    conn.commit()

    cur.close()
    conn.close()

    print("✅ Tabela clube_zerozero_base criada com sucesso")

if __name__ == "__main__":
    main()