import sqlite3
import time
import random

from atualizar_fpf import (
    criar_driver,
    obter_dados_jogador,
    inserir_jogador,
    carregar_mapa_clubes
)

DB_PATH = "jogadores_fpf.db"
IDS_FILE = "ids_em_falta.txt"

def main():
    with open(IDS_FILE) as f:
        ids = [int(line.strip()) for line in f if line.strip()]

    print(f"🔎 IDs a tentar recuperar: {len(ids)}")

    mapa_clubes = carregar_mapa_clubes()
    driver = criar_driver()

    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA busy_timeout = 30000")
    conn.execute("BEGIN")

    recuperados = 0

    for pid in ids:
        print(f"▶️ A testar ID {pid}")
        dados = obter_dados_jogador(driver, pid)

        if dados:
            inserir_jogador(conn, dados, mapa_clubes)
            recuperados += 1
            print(f"✅ Recuperado: {dados['nome']}")
        else:
            print("❌ Ainda indisponível")

        time.sleep(random.uniform(0.8, 1.4))

    driver.quit()
    conn.commit()
    conn.close()

    print(f"✅ Recuperados {recuperados} / {len(ids)}")

if __name__ == "__main__":
    main()