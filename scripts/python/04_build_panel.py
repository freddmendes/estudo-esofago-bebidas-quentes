"""
04_build_panel.py
-------------------
Junta as bases padronizadas em um painel pais-ano.

O FAOSTAT e lido do artefato canonico produzido pelo script 01:
    data/raw/api/faostat_consumo_cha_cafe_mate.csv
"""

from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
INTER_DIR = BASE_DIR / "data" / "intermediate"
PROC_DIR = BASE_DIR / "data" / "processed"


def normalizar_texto(texto) -> str:
    if not isinstance(texto, str):
        return ""
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(c for c in texto if not unicodedata.combining(c))
    return texto.lower()


def contem_alguma_palavra(serie: pd.Series, palavras: list) -> pd.Series:
    normalizado = serie.astype(str).apply(normalizar_texto)
    return normalizado.apply(lambda texto: any(palavra in texto for palavra in palavras))


PALAVRAS_ESOFAGO = ["esophageal", "esofago"]
PALAVRAS_TAXA = ["rate", "taxa"]
PALAVRAS_PADRONIZADA = ["standardiz", "padronizada"]

MAPA_MEDIDAS = {
    "incidencia": "incidence",
    "incidence": "incidence",
    "obitos": "deaths",
    "deaths": "deaths",
    "mortality": "deaths",
    "mortalidade": "deaths",
    "dalys": "dalys",
    "ylls": "ylls",
    "ylds": "ylds",
    "prevalencia": "prevalence",
    "prevalence": "prevalence",
}

FAOSTAT_COLUNAS = {
    "Coffee and products": "faostat_coffee_kg_capita",
    "Tea (including mate)": "faostat_tea_mate_kg_capita",
}


def mapear_medida(nome) -> str:
    chave = normalizar_texto(nome)
    return MAPA_MEDIDAS.get(chave, chave.replace(" ", "_"))


def carregar_desfecho_gbd() -> pd.DataFrame:
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
        print("  [aviso] nenhuma linha GBD restou apos os filtros.")
        return pd.DataFrame()

    df["medida_padrao"] = df["medida"].apply(mapear_medida)
    pivot = df.pivot_table(
        index=["iso3", "ano"], columns="medida_padrao", values="valor", aggfunc="mean"
    ).reset_index()
    pivot.columns = [col if col in ("iso3", "ano") else f"asr_{col}" for col in pivot.columns]
    return pivot


def carregar_covariaveis_wb() -> pd.DataFrame:
    caminho = BASE_DIR / "data" / "raw" / "api" / "world_bank_indicadores.csv"
    if not caminho.exists():
        print("  [aviso] dados do World Bank nao encontrados — rode 01_download_public_data.py")
        return pd.DataFrame()

    df = pd.read_csv(caminho, low_memory=False)
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce")
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
    df = df.dropna(subset=["iso3", "ano", "nome_indicador"])
    df["ano"] = df["ano"].astype(int)

    return df.pivot_table(
        index=["iso3", "ano"], columns="nome_indicador", values="valor", aggfunc="mean"
    ).reset_index()


def _slug_faostat(item: str) -> str:
    texto = normalizar_texto(str(item))
    texto = re.sub(r"[^a-z0-9]+", "_", texto).strip("_")
    return f"faostat_{texto}_kg_capita"


def carregar_faostat() -> pd.DataFrame:
    caminho = BASE_DIR / "data" / "raw" / "api" / "faostat_consumo_cha_cafe_mate.csv"
    if not caminho.exists():
        print(
            "  [aviso] artefato FAOSTAT nao encontrado. Coloque faostat_manual.csv em "
            "data/raw/manual/ e rode 01_download_public_data.py."
        )
        return pd.DataFrame()

    df = pd.read_csv(caminho, low_memory=False)
    requeridas = {"iso3", "ano", "item", "consumo_kg_capita"}
    faltando = sorted(requeridas - set(df.columns))
    if faltando:
        raise ValueError(
            f"Formato FAOSTAT inesperado; faltam colunas {faltando}. "
            "Rode novamente o script 01 atualizado."
        )

    df["iso3"] = df["iso3"].astype("string").str.strip().str.upper()
    df["ano"] = pd.to_numeric(df["ano"], errors="coerce")
    df["consumo_kg_capita"] = pd.to_numeric(df["consumo_kg_capita"], errors="coerce")
    df = df.dropna(subset=["iso3", "ano", "item", "consumo_kg_capita"]).copy()
    df["ano"] = df["ano"].astype(int)

    duplicadas = df.duplicated(["iso3", "ano", "item"], keep=False)
    if duplicadas.any():
        exemplo = df.loc[duplicadas, ["iso3", "ano", "item"]].head(10)
        raise ValueError(
            "FAOSTAT possui duplicidades em iso3+ano+item. Exemplos:\n"
            + exemplo.to_string(index=False)
        )

    pivot = df.pivot(index=["iso3", "ano"], columns="item", values="consumo_kg_capita").reset_index()
    pivot = pivot.rename(
        columns={
            item: FAOSTAT_COLUNAS.get(item, _slug_faostat(item))
            for item in pivot.columns
            if item not in ("iso3", "ano")
        }
    )

    colunas_x1 = [col for col in pivot.columns if col.startswith("faostat_")]
    print(
        f"  FAOSTAT carregado: {pivot['iso3'].nunique()} paises/territorios, "
        f"{pivot['ano'].min()}-{pivot['ano'].max()}, colunas X1={colunas_x1}"
    )
    return pivot


def carregar_who_gho() -> pd.DataFrame:
    caminho = BASE_DIR / "data" / "raw" / "api" / "who_gho_indicadores.csv"
    if not caminho.exists():
        print("  [aviso] dados do WHO GHO ainda nao encontrados.")
        return pd.DataFrame()

    df = pd.read_csv(caminho, low_memory=False)
    col_iso = "SpatialDim" if "SpatialDim" in df.columns else None
    col_ano = "TimeDim" if "TimeDim" in df.columns else None
    col_valor = "NumericValue" if "NumericValue" in df.columns else None
    if not all([col_iso, col_ano, col_valor, "tema" in df.columns]):
        print("  [aviso] formato inesperado do WHO GHO.")
        return pd.DataFrame()

    df = df.rename(columns={col_iso: "iso3", col_ano: "ano", col_valor: "valor"})
    pivot = df.pivot_table(
        index=["iso3", "ano"], columns="tema", values="valor", aggfunc="mean"
    ).reset_index()
    pivot.columns = [col if col in ("iso3", "ano") else f"who_{col}" for col in pivot.columns]
    return pivot


def validar_chaves(df: pd.DataFrame, nome: str):
    if df.empty:
        return
    if not {"iso3", "ano"}.issubset(df.columns):
        raise ValueError(f"{nome}: faltam as chaves iso3/ano")
    duplicadas = df.duplicated(["iso3", "ano"], keep=False)
    if duplicadas.any():
        raise ValueError(f"{nome}: existem chaves iso3+ano duplicadas")


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

    fontes = {
        "GBD": desfechos,
        "World Bank": wb,
        "FAOSTAT": fao,
        "WHO GHO": gho,
    }
    for nome, parte in fontes.items():
        validar_chaves(parte, nome)

    partes = [parte for parte in fontes.values() if not parte.empty]
    if not partes:
        raise RuntimeError("nenhuma base disponivel — rode os scripts 01/02/03 primeiro")

    painel = partes[0]
    for parte in partes[1:]:
        painel = painel.merge(parte, on=["iso3", "ano"], how="outer", validate="one_to_one")

    painel = painel.sort_values(["iso3", "ano"], kind="stable").reset_index(drop=True)
    saida = PROC_DIR / "painel_pais_ano.csv"
    painel.to_csv(saida, index=False, encoding="utf-8")

    colunas_fao = [col for col in painel.columns if col.startswith("faostat_")]
    print(f"\nPainel pais-ano salvo em: {saida}")
    print(f"Dimensoes: {painel.shape[0]} linhas x {painel.shape[1]} colunas")
    print(f"Paises/territorios ISO3 unicos: {painel['iso3'].nunique()}")
    print(f"Colunas FAOSTAT incorporadas: {colunas_fao}")


if __name__ == "__main__":
    main()
