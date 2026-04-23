import requests

url = "https://www.fpf.pt/pt/Jogadores/Ficha-de-Jogador/playerId/2352782"
r = requests.get(url)

with open("html_2352782.html", "w", encoding="utf-8") as f:
    f.write(r.text)

print("HTML guardado")