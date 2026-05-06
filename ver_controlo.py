import os
import psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

cur.execute("""
    SELECT chave, valor
    FROM controlo
""")

for row in cur.fetchall():
    print(row)

cur.close()
conn.close()
