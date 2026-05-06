import os
import psycopg2

conn = psycopg2.connect(os.environ["DATABASE_URL"])
cur = conn.cursor()

cur.execute("""
    UPDATE controlo
    SET valor = %s
    WHERE chave = 'ultimo_player_id'
""", ("2353397",))

conn.commit()
cur.close()
conn.close()

print("✅ ultimo_player_id definido para 2353397")