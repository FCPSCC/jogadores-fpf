import requests
from bs4 import BeautifulSoup
import pandas as pd
import time

headers = {"User-Agent": "Mozilla/5.0"}
base = "https://www.zerozero.pt"

# secções válidas
sec_validas = [
    "Futebol",
    "Futsal",
    "Futebol de 9",
    "Futebol de 7",
    "Act. Lúdicas"
]

equipas_final = []

page = 1
slugs_validos = set()

# =========================
# PASSO 1 — apanhar slugs
# =========================
while True:
    print(f"Página {page}")
    
    url = f"{base}/equipas/futebol/portugal?page={page}"
    r = requests.get(url, headers=headers)
    
    if r.status_code != 200:
        break
    
    soup = BeautifulSoup(r.text, "html.parser")
    
    links = soup.find_all("a", href=True)
    
    novos = 0
    
    for link in links:
        href = link["href"]
        
        if not href.startswith("/equipa/"):
            continue
        
        if "?" in href:
            continue
        
        partes = href.split("/")
        
        if len(partes) < 3:
            continue
        
        slug = partes[2]
        
        if slug.isnumeric() or slug == "":
            continue
        
        if slug not in slugs_validos:
            slugs_validos.add(slug)
            novos += 1
    
    print(f"+{novos} slugs")
    
    if novos == 0:
        break
    
    page += 1
    time.sleep(1)

print(f"Total slugs encontrados: {len(slugs_validos)}")

# =========================
# PASSO 2 — validar clubes PT
# =========================

slugs_portugal = []

for i, slug in enumerate(slugs_validos):
    print(f"Validar {i+1}/{len(slugs_validos)} - {slug}")
    
    url = f"{base}/equipa/{slug}"
    
    try:
        r = requests.get(url, headers=headers, timeout=10)
    except:
        continue
    
    if r.status_code != 200:
        continue
    
    # 🔥 filtro chave
    if "Portugal" in r.text:
        slugs_portugal.append(slug)
    
    time.sleep(0.5)

print(f"Clubes portugueses: {len(slugs_portugal)}")

# =========================
# PASSO 3 — extrair equipas
# =========================

for i, slug in enumerate(slugs_portugal):
    print(f"{i+1}/{len(slugs_portugal)} - {slug}")
    
    url = f"{base}/equipa/{slug}"
    
    try:
        r = requests.get(url, headers=headers)
    except:
        continue
    
    if r.status_code != 200:
        continue
    
    soup = BeautifulSoup(r.text, "html.parser")
    
    sections = soup.find_all("div", class_="section")
    
    for section in sections:
        nome_sec = section.get_text(strip=True)
        
        if not any(s in nome_sec for s in sec_validas):
            continue
        
        lista = section.find_next_sibling("div", class_="rbtextlist")
        
        if not lista:
            continue
        
        links = lista.find_all("a")
        
        for link in links:
            href = link.get("href")
            
            if not href or "/equipa/" not in href:
                continue
            
            # 🔥 garantir que tem ID
            if href.count("/") < 4:
                continue
            
            equipas_final.append({
                "clube": slug,
                "secao": nome_sec,
                "equipa": link.get_text(strip=True),
                "url": base + href
            })
    
    time.sleep(0.7)

# =========================
# EXPORT
# =========================

df = pd.DataFrame(equipas_final).drop_duplicates()
df.to_excel("zerozero_equipas_final.xlsx", index=False)

print("Ficheiro final criado!")