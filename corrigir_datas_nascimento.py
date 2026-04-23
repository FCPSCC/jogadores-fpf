import sqlite3
import re

DB_PATH = r"C:\Users\augusto.roxo\Documents\Scripts\BD\jogadores_fpf.db"

def converter_iso_para_ddmmyyyy(data):
    """
    Converte:
      AAAA-MM-DD
      AAAA-MM-DD HH:MM:SS
    para:
      DD-MM-AAAA
    """
    if not data:
        return None

    data = data.strip()

    # apanhar datas que COMECEM por 4 dígitos (ano)
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", data)
    if not m:
        return None  # já está OK ou é outro formato

    ano, mes, dia = m.groups()
    return f"{dia}-{mes}-{ano}"

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT player_id, data_nascimento FROM jogadores")
    linhas = cur.fetchall()

    total = 0
    convertidas = 0

    for player_id, data_antiga in linhas:
        total += 1
        nova = converter_iso_para_ddmmyyyy(data_antiga)

        if nova:
            cur.execute(
                "UPDATE jogadores SET data_nascimento = ? WHERE player_id = ?",
                (nova, player_id)
            )
            convertidas += 1

    conn.commit()
    conn.close()

    print(f"Registos analisados: {total}")
    print(f"Datas convertidas: {convertidas}")
    print("Conversão concluída com sucesso.")

if __name__ == "__main__":
    main()