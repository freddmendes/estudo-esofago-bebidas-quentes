"""
03_harmonize_countries.py
---------------------------
Harmoniza todas as bases para ISO3.

Correção central desta versão:
- arquivos GBD exportados em português trazem `location_id` na coluna
  temporariamente chamada `iso3` pelo importador da etapa 02;
- nomes em português não devem ser enviados diretamente ao fuzzy matching do
  pycountry, pois isso pode excluir países ou, pior, mapear um país para outro
  (por exemplo, "Irã" -> IRQ);
- para o GBD, usa-se uma tabela explícita e auditável location_id -> ISO3.

A tabela de referência fica em:
    data/reference/gbd_location_id_to_iso3.csv
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd
import pycountry

BASE_DIR = Path(__file__).resolve().parents[2]
INTER_DIR = BASE_DIR / "data" / "intermediate"
API_DIR = BASE_DIR / "data" / "raw" / "api"
REFERENCE_DIR = BASE_DIR / "data" / "reference"
GBD_MAP_PATH = REFERENCE_DIR / "gbd_location_id_to_iso3.csv"


# Apelidos usados como fallback em fontes não-GBD.
APELIDOS = {
    # Inglês / nomes institucionais
    "Russia": "RUS", "Russian Federation": "RUS",
    "South Korea": "KOR", "Korea, Rep.": "KOR", "Republic of Korea": "KOR",
    "North Korea": "PRK", "Korea, Dem. People's Rep.": "PRK",
    "Iran": "IRN", "Iran, Islamic Rep.": "IRN", "Iran (Islamic Republic of)": "IRN",
    "Vietnam": "VNM", "Viet Nam": "VNM",
    "Turkiye": "TUR", "Turkey": "TUR",
    "Laos": "LAO", "Lao PDR": "LAO",
    "Syria": "SYR", "Syrian Arab Republic": "SYR",
    "Tanzania": "TZA", "United Republic of Tanzania": "TZA",
    "Bolivia": "BOL", "Bolivia (Plurinational State of)": "BOL",
    "Venezuela": "VEN", "Venezuela (Bolivarian Republic of)": "VEN",
    "Moldova": "MDA", "Republic of Moldova": "MDA",
    "Brunei": "BRN", "Brunei Darussalam": "BRN",
    "Cote d'Ivoire": "CIV", "Côte d’Ivoire": "CIV", "Ivory Coast": "CIV",
    "Cabo Verde": "CPV", "Cape Verde": "CPV",
    "Democratic Republic of Congo": "COD", "Democratic Republic of the Congo": "COD",
    "Congo, Dem. Rep.": "COD", "Congo, Rep.": "COG",
    "Micronesia": "FSM", "Micronesia (Federated States of)": "FSM",
    "Eswatini": "SWZ", "Swaziland": "SWZ",
    "United States": "USA", "United States of America": "USA",
    "United Kingdom": "GBR",
    "Egypt": "EGY", "Egypt, Arab Rep.": "EGY",
    "Slovak Republic": "SVK",
    "Czechia": "CZE", "Czech Republic": "CZE",
    "Hong Kong": "HKG", "Hong Kong SAR, China": "HKG", "China, Hong Kong SAR": "HKG",
    "Macao": "MAC", "Macao SAR, China": "MAC", "China, Macao SAR": "MAC",
    "Taiwan": "TWN", "China, Taiwan Province of": "TWN",
    "Palestine": "PSE", "State of Palestine": "PSE", "West Bank and Gaza": "PSE",
    # Português — fallback para arquivos que não tragam location_id
    "Irã": "IRN", "Quênia": "KEN", "Brasil": "BRA", "Alemanha": "DEU",
    "Afeganistão": "AFG", "Argélia": "DZA", "Arábia Saudita": "SAU",
    "África do Sul": "ZAF", "Estados Unidos": "USA", "Reino Unido": "GBR",
    "Coreia do Sul": "KOR", "Coreia do Norte": "PRK", "Costa do Marfim": "CIV",
    "República Democrática do Congo": "COD", "República Tcheca": "CZE",
    "Tanzânia": "TZA", "Turquia": "TUR", "Vietnã": "VNM",
    "Global": None, "World": None,
}


def normalizar_texto(texto: str) -> str:
    if not isinstance(texto, str):
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    texto = re.sub(r"\s+", " ", texto).strip().casefold()
    return texto


APELIDOS_NORMALIZADOS = {normalizar_texto(k): v for k, v in APELIDOS.items()}


def carregar_mapa_gbd() -> dict[int, str]:
    if not GBD_MAP_PATH.exists():
        raise FileNotFoundError(
            f"Tabela de referência ausente: {GBD_MAP_PATH}. "
            "Envie data/reference/gbd_location_id_to_iso3.csv ao repositório."
        )

    mapa = pd.read_csv(GBD_MAP_PATH)
    requeridas = {"location_id", "iso3"}
    faltando = requeridas - set(mapa.columns)
    if faltando:
        raise ValueError(f"Mapa GBD inválido; faltam colunas: {sorted(faltando)}")

    mapa["location_id"] = pd.to_numeric(mapa["location_id"], errors="coerce")
    mapa["iso3"] = mapa["iso3"].astype("string").str.strip().str.upper()
    mapa = mapa.dropna(subset=["location_id", "iso3"]).copy()
    mapa["location_id"] = mapa["location_id"].astype(int)

    if mapa["location_id"].duplicated().any():
        raise ValueError("Mapa GBD contém location_id duplicado")
    if not mapa["iso3"].str.fullmatch(r"[A-Z]{3}", na=False).all():
        raise ValueError("Mapa GBD contém ISO3 inválido")

    return dict(zip(mapa["location_id"], mapa["iso3"]))


def nome_para_iso3(nome: str):
    if not isinstance(nome, str) or not nome.strip():
        return None

    chave = normalizar_texto(nome)
    if chave in APELIDOS_NORMALIZADOS:
        return APELIDOS_NORMALIZADOS[chave]

    # O fuzzy matching é apenas fallback para nomes internacionais. Ele não é
    # usado como fonte principal para o GBD em português.
    try:
        resultado = pycountry.countries.search_fuzzy(nome.strip())
        return resultado[0].alpha_3
    except LookupError:
        return None


def _extrair_location_id(valor):
    if pd.isna(valor):
        return None
    texto = str(valor).strip()
    try:
        return int(float(texto))
    except (TypeError, ValueError):
        return None


def _arquivo_eh_gbd(caminho: Path, df: pd.DataFrame) -> bool:
    if caminho.name.lower().startswith("gbd_"):
        return True
    if "fonte" in df.columns:
        fontes = set(df["fonte"].dropna().astype(str).str.casefold().unique())
        return fontes == {"gbd"}
    return False


def processar_arquivo(caminho: Path, mapa_gbd: dict[int, str]):
    print(f"\n=== {caminho.name} ===")
    df = pd.read_csv(caminho, low_memory=False)

    if "iso3" not in df.columns:
        print("  [erro] arquivo não tem coluna 'iso3' nem identificador padronizado — pulei.")
        return None

    eh_gbd = _arquivo_eh_gbd(caminho, df)

    def resolver(row):
        valor = row.get("iso3")

        # Mantém ISO3 já válido.
        if isinstance(valor, str):
            candidato = valor.strip().upper()
            if re.fullmatch(r"[A-Z]{3}", candidato):
                return candidato

        # Para GBD, o valor é location_id. Esta é a via prioritária e segura.
        if eh_gbd:
            location_id = _extrair_location_id(valor)
            if location_id is not None:
                return mapa_gbd.get(location_id)

        # Fallback por nome para demais fontes.
        return nome_para_iso3(row.get("pais", ""))

    df["iso3_resolvido"] = df.apply(resolver, axis=1)
    nao_identificados = df[df["iso3_resolvido"].isna()].copy()

    if not nao_identificados.empty:
        cols = [c for c in ["fonte", "pais", "iso3"] if c in df.columns]
        resumo = nao_identificados[cols].drop_duplicates()
        print(f"  [aviso] {len(resumo)} países/territórios não identificados.")

        # Para GBD, perder países silenciosamente invalida o painel. Interrompe.
        if eh_gbd:
            saida_erro = INTER_DIR / "gbd_localizacoes_nao_identificadas.csv"
            resumo.to_csv(saida_erro, index=False, encoding="utf-8")
            raise RuntimeError(
                "Harmonização GBD incompleta. Revise "
                f"{saida_erro}; nenhuma linha GBD foi salva."
            )

    df["iso3"] = df["iso3_resolvido"]
    df = df.drop(columns=["iso3_resolvido"])
    df = df[df["iso3"].notna()].copy()

    # Diagnóstico específico do GBD: um ISO3 não pode representar dois
    # location_id diferentes.
    if eh_gbd:
        pares = df[["iso3"]].copy()
        if "pais" in df.columns:
            pares["pais"] = df["pais"]
        n_iso = df["iso3"].nunique()
        print(f"  GBD harmonizado: {n_iso} ISO3 únicos")

    saida = INTER_DIR / caminho.name.replace(".csv", "_iso3.csv")
    df.to_csv(saida, index=False, encoding="utf-8")
    print(f"  salvo em: {saida}  ({len(df)} linhas)")

    if not nao_identificados.empty:
        cols = [c for c in ["fonte", "pais", "iso3"] if c in nao_identificados.columns]
        return nao_identificados[cols].drop_duplicates()
    return None


def main():
    INTER_DIR.mkdir(parents=True, exist_ok=True)
    mapa_gbd = carregar_mapa_gbd()

    arquivos = list(INTER_DIR.glob("*_padronizado.csv")) + list(API_DIR.glob("*.csv"))
    todos_nao_identificados = []

    for arquivo in arquivos:
        resultado = processar_arquivo(arquivo, mapa_gbd)
        if resultado is not None and not resultado.empty:
            todos_nao_identificados.append(resultado)

    if todos_nao_identificados:
        painel = pd.concat(todos_nao_identificados, ignore_index=True).drop_duplicates()
        saida = INTER_DIR / "paises_nao_identificados.csv"
        painel.to_csv(saida, index=False, encoding="utf-8")
        print(f"\n[ATENÇÃO] Revise manualmente: {saida}")
    else:
        print("\nTodos os países foram identificados com sucesso.")


if __name__ == "__main__":
    main()
