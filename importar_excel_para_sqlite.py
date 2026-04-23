import pandas as pd
import sqlite3
from datetime import datetime

# Caminhos (ajusta se necessário)
EXCEL_PATH = r"C:\Users\augusto.roxo\Documents\Scripts\BD\jogadores.xlsx"
DB_PATH = r"C:\Users\augusto.roxo\Documents\Scripts\BD\jogadores_fpf.db"

EPOCA_ATUAL = "2025-2026"

# Ler Excel
df = pd.read_excel(EXCEL_PATH)

# Renomear colunas para o modelo da BD
df = df.rename(columns={
    "ID": "player_id",
    "Nome Completo": "nome",
    "Data de Nascimento": "data_nascimento",
    "Clube": "clube",
    "Distrito": "distrito"
})

# Manter apenas as colunas relevantes
df = df[[
    "player_id",
    "nome",
    "data_nascimento",
    "clube",
    "distrito"
]]

# Remover linhas sem ID
df = df.dropna(subset=["player_id"])

# Garantir tipos corretos
df["player_id"] = df["player_id"].astype(int)
df["epoca"] = EPOCA_ATUAL
df["data_importacao"] = datetime.now().isoformat()

# Ligar à BD
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Inserir dados (ignora duplicados automaticamente)
for _, row in df.iterrows():
    cursor.execute("""
        INSERT OR IGNORE INTO jogadores (
            player_id,
            nome,
            data_nascimento,
            clube,
            epoca,
            distrito,
            data_importacao
        )
        VALUES (?,?,?,?,?,?,?)
    """, (
        row["player_id"],
        row["nome"],
        str(row["data_nascimento"]),
        row["clube"],
        row["epoca"],
        row["distrito"],
        row["data_importacao"]
    ))

conn.commit()
conn.close()

print("✅ Importação do Excel concluída com sucesso.")
