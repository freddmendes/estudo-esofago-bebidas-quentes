"""
03_harmonize_countries.py
---------------------------
Garante que TODAS as bases (World Bank, FAOSTAT, WHO GHO, GBD,
GLOBOCAN, CI5, Vignat) usem o mesmo codigo de pais: ISO3 (ex: BRA,
IRN, CHN). Sem isso, o merge das bases no painel pais-ano (script 04)
sai errado silenciosamente.

Como rodar (cmd, na raiz do projeto):
    python scripts\\python\\03_harmonize_countries.py

Paises que o script NAO conseguir identificar automaticamente vao
para data/intermediate/paises_nao_identificados.csv — you precisa
completar esses ISO3 manualmente (geralmente e questao de nome
diferente, ex: "Vietnam" vs "Viet Nam", "Turkiye" vs "Turkey").
"""

from pathlib import Path

import pandas as pd
import pycountry

BASE_DIR = Path(__file__).resolve().parents[2]
INTER_DIR = BASE_DIR / "data" / "intermediate"
API_DIR = BASE_DIR / "data" / "raw" / "api"

# apelidos comuns que o pycountry nao reconhece de primeira
APELIDOS = {
    "Russia": "RUS", "Russian Federation": "RUS",
    "South Korea": "KOR", "Korea, Rep.": "KOR", "Republic of Korea": "KOR",
    "North Korea": "PRK", "Korea, Dem. People's Rep.": "PRK",
    "Iran": "IRN", "Iran, Islamic Rep.": "IRN",
    "Vietnam": "VNM", "Viet Nam": "VNM",
    "Turkiye": "TUR", "Turkey": "TUR",
    "Laos": "LAO", "Lao PDR": "LAO",
    "Syria": "SYR", "Syrian Arab Republic": "SYR",
    "Tanzania": "TZA", "United Republic of Tanzania": "TZA",
    "Bolivia": "BOL",
    "Venezuela": "VEN",
    "Moldova": "MDA",
    "Brunei": "BRN",
    "Cote d'Ivoire": "CIV", "Ivory Coast": "CIV",
    "Cabo Verde": "CPV", "Cape Verde": "CPV",
    "Democratic Republic of Congo": "COD", "Congo, Dem. Rep.": "COD",
    "Congo, Rep.": "COG",
    "Micronesia": "FSM",
    "Eswatini": "SWZ", "Swaziland": "SWZ",
    "United States": "USA", "United States of America": "USA",
    "United Kingdom": "GBR",
    "Egypt": "EGY", "Egypt, Arab Rep.": "EGY",
    "Slovak Republic": "SVK",
    "Czechia": "CZE", "Czech Republic": "CZE",
    "Hong Kong": "HKG", "Hong Kong SAR, China": "HKG",
    "Macao": "MAC", "Macao SAR, China": "MAC",
    "Taiwan": "TWN",
    "Palestine": "PSE", "West Bank and Gaza": "PSE",
    "Global": None, "World": None,  # nao sao paises, descartar
}


def nome_para_iso3(nome: str):
    if not isinstance(nome, str) or not nome.strip():
        return None
    nome = nome.strip()
    if nome in APELIDOS:
        return APELIDOS[nome]
    try:
        resultado = pycountry.countries.search_fuzzy(nome)
        return resultado[0].alpha_3
    except LookupError:
        return None


def processar_arquivo(caminho: Path):
    print(f"\n=== {caminho.name} ===")
    df = pd.read_csv(caminho, low_memory=False)

    if "iso3" not in df.columns:
        print("  [erro] arquivo nao tem coluna 'iso3' nem 'pais' padronizada — pulei.")
        return None

    # se ja tem iso3 valido (3 letras maiusculas), mantem; senao, tenta converter pelo nome
    def resolver(row):
        val = row.get("iso3")
        if isinstance(val, str) and len(val) == 3 and val.isupper() and val.isalpha():
            return val
        return nome_para_iso3(row.get("pais", ""))

    df["iso3_resolvido"] = df.apply(resolver, axis=1)

    nao_identificados = df[df["iso3_resolvido"].isna()]
    if not nao_identificados.empty:
        cols_pais = [c for c in ["pais", "iso3"] if c in df.columns]
        print(f"  [aviso] {nao_identificados[cols_pais].drop_duplicates().shape[0]} "
              f"paises/territorios nao identificados automaticamente.")

    df["iso3"] = df["iso3_resolvido"]
    df = df.drop(columns=["iso3_resolvido"])
    df = df[df["iso3"].notna()]

    saida = INTER_DIR / caminho.name.replace(".csv", "_iso3.csv")
    df.to_csv(saida, index=False, encoding="utf-8")
    print(f"  salvo em: {saida}  ({len(df)} linhas)")

    if not nao_identificados.empty:
        return nao_identificados[cols_pais].drop_duplicates()
    return None


def main():
    arquivos = list(INTER_DIR.glob("*_padronizado.csv")) + list(API_DIR.glob("*.csv"))
    todos_nao_identificados = []

    for arq in arquivos:
        resultado = processar_arquivo(arq)
        if resultado is not None:
            todos_nao_identificados.append(resultado)

    if todos_nao_identificados:
        painel = pd.concat(todos_nao_identificados, ignore_index=True).drop_duplicates()
        saida = INTER_DIR / "paises_nao_identificados.csv"
        painel.to_csv(saida, index=False, encoding="utf-8")
        print(f"\n[ATENCAO] Revise manualmente: {saida}")
        print("Adicione os nomes que faltam ao dicionario APELIDOS neste script"
              " e rode de novo.")
    else:
        print("\nTodos os paises foram identificados com sucesso.")


if __name__ == "__main__":
    main()
