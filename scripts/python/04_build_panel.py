"""
04_build_panel.py
-------------------
Junta todas as bases ja padronizadas e harmonizadas (saida do script 03)
num UNICO painel pais-ano, que e a unidade de analise de todo o
protocolo (Secao 5).

Como rodar (cmd, na raiz do projeto):
    python scripts\\python\\04_build_panel.py

Gera: data/processed/painel_pais_ano.csv
"""

import unicodedata
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
INTER_DIR = BASE_DIR / "data" / "intermediate"
PROC_DIR = BASE_DIR / "data" / "processed"

# ------------------------------------------------------------------
# O GBD Results Tool exporta os textos (causa/medida/metrica/faixa
# etaria) no idioma do navegador de quem baixou — pode vir em ingles
# ("Esophageal cancer", "Rate", "Deaths") ou em portugues ("Cancer de
# esofago", "Taxa", "Obitos"). As funcoes abaixo reconhecem os dois,
# ignorando acentuacao, para o filtro nao depender do idioma de quem
# baixou o arquivo.
# ------------------------------------------------------------------
def normalizar_texto(texto) -> str:
    if not isinstance(texto, str):
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()


def contem_alguma_palavra(serie: pd.Series, palavras: list) -> pd.Series:
    normalizado = serie.astype(str).apply(normalizar_texto)
    return normalizado.apply(lambda t: any(p in t for p in palavras))


PALAVRAS_ESOFAGO = ["esophageal", "esofago"]
PALAVRAS_TAXA = ["rate", "taxa"]
PALAVRAS_PADRONIZADA = ["standardiz", "padronizada"]

# nomes canonicos (sempre em ingles) para as colunas finais do painel,
# independente do idioma em que o GBD foi baixado
MAPA_MEDIDAS = {
    "incidencia": "incidence", "incidence": "incidence",
    "obitos": "deaths", "deaths": "deaths", "mortality": "deaths", "mortalidade": "deaths",
    "dalys": "dalys",
    "ylls": "ylls",
    "ylds": "ylds",
    "prevalencia": "prevalence", "prevalence": "prevalence",
}


def mapear_medida(nome) -> str:
    chave = normalizar_texto(nome)
    return MAPA_MEDIDAS.get(chave, chave.replace(" ", "_"))


def carregar_desfecho_gbd() -> pd.DataFrame:
    """
    Desfecho primario e secundarios (Secao 8): ASR de incidencia,
    mortalidade, DALY, YLL, YLD do cancer de esofago TOTAL (o painel
    anual completo). A estratificacao ESCC/EAC entra depois, como
    analise confirmatoria separada (ver 05_build_hbfei.py e os
    scripts R 07/08) — NAO tente forcar ESCC/EAC no painel anual
    completo, porque essa serie historica nao existe (CI5 so cobre
    2013-2017; Vignat et al. e uma foto de 2020).
    """
    caminho = INTER_DIR / "gbd_padronizado_iso3.csv"
    if not caminho.exists():
        print(f"  [aviso] {caminho.name} nao encontrado — rode antes 02 e 03.")
        return pd.DataFrame()

    df = pd.read_csv(caminho, low_memory=False)

    df = df[contem_alguma_palavra(df["causa"], PALAVRAS_ESOFAGO)]
    df = df[contem_alguma_palavra(df["metrica"], PALAVRAS_TAXA)]
    if "faixa_etaria" in df.columns:
        df = df[contem_alguma_palavra(df["faixa_etaria"], PALAVRAS_PADRONIZADA)]

    if df.empty:
        print("  [aviso] nenhuma linha sobrou apos os filtros de causa/metrica/faixa etaria.")
        print("  Abra data/intermediate/gbd_padronizado_iso3.csv e confira os valores reais")
        print("  das colunas 'causa', 'metrica' e 'faixa_etaria' (podem ter vindo em outro")
        print("  idioma que este script ainda nao reconhece — me avise qual apareceu).")
        return pd.DataFrame()

    df["medida_padrao"] = df["medida"].apply(mapear_medida)

    # uma coluna por medida (incidence/deaths/dalys/ylls/ylds), sempre com nome em ingles
    pivot = df.pivot_table(
        index=["iso3", "ano"], columns="medida_padrao", values="valor", aggfunc="mean"
    ).reset_index()
    pivot.columns = [c if c in ("iso3", "ano") else f"asr_{c}" for c in pivot.columns]
    return pivot


def carregar_covariaveis_wb() -> pd.DataFrame:
    caminho = BASE_DIR / "data" / "raw" / "api" / "world_bank_indicadores_iso3.csv"
    if not caminho.exists():
        caminho = BASE_DIR / "data" / "raw" / "api" / "world_bank_indicadores.csv"
    if not caminho.exists():
        print("  [aviso] dados do World Bank nao encontrados — rode 01_download_public_data.py")
        return pd.DataFrame()

    df = pd.read_csv(caminho, low_memory=False)
    pivot = df.pivot_table(
        index=["iso3", "ano"], columns="nome_indicador", values="valor", aggfunc="mean"
    ).reset_index()
    return pivot


def carregar_faostat() -> pd.DataFrame:
    caminho = BASE_DIR / "data" / "raw" / "api" / "faostat_consumo_cha_cafe_mate.csv"
    if not caminho.exists():
        print("  [aviso] dados do FAOSTAT nao encontrados — rode 01_download_public_data.py")
        return pd.DataFrame()

    df = pd.read_csv(caminho, low_memory=False)
    # nomes de coluna do FAOSTAT variam; tentativa robusta:
    col_area = [c for c in df.columns if "Area" in c and "Code" not in c][0]
    col_iso = [c for c in df.columns if "Area Code (ISO3)" in c or c == "Area Code"][0]
    col_ano = [c for c in df.columns if c.strip() == "Year"][0]
    col_item = [c for c in df.columns if c.strip() == "Item"][0]
    col_valor = [c for c in df.columns if c.strip() == "Value"][0]

    df = df.rename(columns={col_iso: "iso3", col_ano: "ano", col_item: "item", col_valor: "consumo_kg_capita"})
    pivot = df.pivot_table(
        index=["iso3", "ano"], columns="item", values="consumo_kg_capita", aggfunc="mean"
    ).reset_index()
    pivot.columns = [c if c in ("iso3", "ano") else f"faostat_{str(c).lower().replace(' ', '_')}"
                     for c in pivot.columns]
    return pivot


def carregar_who_gho() -> pd.DataFrame:
    caminho = BASE_DIR / "data" / "raw" / "api" / "who_gho_indicadores.csv"
    if not caminho.exists():
        print("  [aviso] dados do WHO GHO nao encontrados ainda "
              "(normal se voce ainda nao confirmou os codigos em config.yaml)")
        return pd.DataFrame()

    df = pd.read_csv(caminho, low_memory=False)
    col_iso = "SpatialDim" if "SpatialDim" in df.columns else None
    col_ano = "TimeDim" if "TimeDim" in df.columns else None
    col_valor = "NumericValue" if "NumericValue" in df.columns else None
    if not all([col_iso, col_ano, col_valor]):
        print("  [aviso] formato inesperado do WHO GHO — confira o CSV manualmente.")
        return pd.DataFrame()

    df = df.rename(columns={col_iso: "iso3", col_ano: "ano", col_valor: "valor"})
    pivot = df.pivot_table(
        index=["iso3", "ano"], columns="tema", values="valor", aggfunc="mean"
    ).reset_index()
    pivot.columns = [c if c in ("iso3", "ano") else f"who_{c}" for c in pivot.columns]
    return pivot


def main():
    PROC_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Carregando desfechos (GBD) ===")
    desfechos = carregar_desfecho_gbd()

    print("\n=== Carregando covariaveis (World Bank) ===")
    wb = carregar_covariaveis_wb()

    print("\n=== Carregando exposicao (FAOSTAT) ===")
    fao = carregar_faostat()

    print("\n=== Carregando covariaveis (WHO GHO) ===")
    gho = carregar_who_gho()

    partes = [d for d in [desfechos, wb, fao, gho] if not d.empty]
    if not partes:
        print("\n[erro] nenhuma base disponivel ainda — rode os scripts 01/02/03 primeiro.")
        return

    painel = partes[0]
    for parte in partes[1:]:
        painel = painel.merge(parte, on=["iso3", "ano"], how="outer")

    saida = PROC_DIR / "painel_pais_ano.csv"
    painel.to_csv(saida, index=False, encoding="utf-8")
    print(f"\nPainel pais-ano salvo em: {saida}")
    print(f"Dimensoes: {painel.shape[0]} linhas x {painel.shape[1]} colunas")
    print(f"Paises unicos: {painel['iso3'].nunique()}")


if __name__ == "__main__":
    main()
