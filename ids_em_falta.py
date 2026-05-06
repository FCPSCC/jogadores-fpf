import sqlite3

DB_PATH = "jogadores_fpf.db"
ID_INICIO = 2353301
ID_FIM = 2353474

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()

c.execute("SELECT player_id FROM jogadores")
existentes = {r[0] for r in c.fetchall()}

conn.close()

faltam = [i for i in range(ID_INICIO, ID_FIM + 1) if i not in existentes]

print(f"IDs em falta: {len(faltam)}")

# guardar num ficheiro
with open("ids_em_falta.txt", "w") as f:
    for pid in faltam:
        f.write(f"{pid}\n")

print("✅ IDs guardados em ids_em_falta.txt")
