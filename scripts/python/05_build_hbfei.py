"""
05_build_hbfei.py
-------------------
Constroi o Hot Beverage and Food Exposure Index (HBFEI) por PCA sobre
componentes padronizados (z-score):

    X1 = consumo per capita de cafe + cha/mate (FAOSTAT)
    X2 = proporcao que consome bebidas muito quentes
    X3 = classificacao etnografica ordinal 0-2

Gera:
    data/processed/painel_pais_ano_com_hbfei.csv
    data/processed/hbfei_pca_diagnostico.csv
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

BASE_DIR = Path(__file__).resolve().parents[2]
PROC_DIR = BASE_DIR / "data" / "processed"
MANUAL_DIR = BASE_DIR / "data" / "raw" / "manual" / "hbfei_x2_x3"


def carregar_painel() -> pd.DataFrame:
    caminho = PROC_DIR / "painel_pais_ano.csv"
    if not caminho.exists():
        raise FileNotFoundError(f"{caminho} nao existe — rode 04_build_panel.py antes.")
    painel = pd.read_csv(caminho, low_memory=False)
    if painel.duplicated(["iso3", "ano"]).any():
        raise ValueError("painel_pais_ano.csv possui chaves iso3+ano duplicadas")
    return painel


def _ler_csv_com_delimitador_flexivel(caminho: Path) -> pd.DataFrame:
    df = pd.read_csv(caminho, sep=None, engine="python")
    df.columns = [str(col).strip() for col in df.columns]

    cabecalho_corrompido = "x2_metodo_afericaox3_classificacao_0_2"
    if cabecalho_corrompido in df.columns:
        raise ValueError(
            "O cabecalho de template_x2_x3.csv esta corrompido: falta uma virgula "
            "entre x2_metodo_afericao e x3_classificacao_0_2."
        )
    return df


def _achar_coluna(df: pd.DataFrame, pistas: list[str]) -> str | None:
    for col in df.columns:
        nome = str(col).lower().replace(" ", "").replace("-", "_")
        if all(pista in nome for pista in pistas):
            return col
    return None


def carregar_x2_x3() -> pd.DataFrame:
    caminho = MANUAL_DIR / "template_x2_x3.csv"
    if not caminho.exists():
        raise FileNotFoundError(f"Nao encontrei {caminho}")

    df = _ler_csv_com_delimitador_flexivel(caminho)
    col_iso3 = _achar_coluna(df, ["iso3"])
    col_x2 = _achar_coluna(df, ["x2", "proporcao"])
    col_x3 = _achar_coluna(df, ["x3", "classific"])

    faltando = [
        nome
        for nome, col in [
            ("iso3", col_iso3),
            ("x2_proporcao_muito_quente", col_x2),
            ("x3_classificacao_0_2", col_x3),
        ]
        if col is None
    ]
    if faltando:
        raise KeyError(
            f"Colunas ausentes em template_x2_x3.csv: {faltando}. "
            f"Colunas existentes: {list(df.columns)}"
        )

    df = df.rename(
        columns={
            col_iso3: "iso3",
            col_x2: "x2_proporcao_muito_quente",
            col_x3: "x3_classificacao_0_2",
        }
    )
    df["iso3"] = df["iso3"].astype("string").str.strip().str.upper()
    df["x2_proporcao_muito_quente"] = pd.to_numeric(
        df["x2_proporcao_muito_quente"], errors="coerce"
    )
    df["x3_classificacao_0_2"] = pd.to_numeric(
        df["x3_classificacao_0_2"], errors="coerce"
    )

    iso_invalido = ~df["iso3"].str.fullmatch(r"[A-Z]{3}", na=False)
    if iso_invalido.any():
        valores = df.loc[iso_invalido, "iso3"].dropna().unique().tolist()
        raise ValueError(f"ISO3 invalidos no template X2/X3: {valores}")

    fora_x2 = df["x2_proporcao_muito_quente"].notna() & ~df["x2_proporcao_muito_quente"].between(0, 1)
    fora_x3 = df["x3_classificacao_0_2"].notna() & ~df["x3_classificacao_0_2"].between(0, 2)
    if fora_x2.any():
        raise ValueError("X2 deve ser proporcao entre 0 e 1")
    if fora_x3.any():
        raise ValueError("X3 deve estar na escala 0-2")

    duplicados = df["iso3"].duplicated(keep=False)
    if duplicados.any():
        raise ValueError(
            "Existem paises duplicados no template X2/X3: "
            + ", ".join(sorted(df.loc[duplicados, "iso3"].unique()))
        )

    preenchidos = df.dropna(
        subset=["x2_proporcao_muito_quente", "x3_classificacao_0_2"], how="all"
    )
    print(
        f"  curadoria X2/X3: {len(preenchidos)} paises com ao menos um componente; "
        f"X2={df['x2_proporcao_muito_quente'].notna().sum()}, "
        f"X3={df['x3_classificacao_0_2'].notna().sum()}"
    )

    return df[["iso3", "x2_proporcao_muito_quente", "x3_classificacao_0_2"]]


def identificar_colunas_x1(painel: pd.DataFrame) -> list[str]:
    return sorted(col for col in painel.columns if col.startswith("faostat_"))


def salvar_diagnostico_pca(
    componentes: list[str],
    scaler: StandardScaler,
    pca: PCA,
    sinal: float,
    n_linhas: int,
    n_paises: int,
):
    diagnostico = pd.DataFrame(
        {
            "componente": componentes,
            "media_original": scaler.mean_,
            "desvio_padrao_original": scaler.scale_,
            "carga_pc1": pca.components_[0] * sinal,
            "variancia_explicada_pc1": pca.explained_variance_ratio_[0],
            "n_linhas_completas": n_linhas,
            "n_paises_completos": n_paises,
        }
    )
    saida = PROC_DIR / "hbfei_pca_diagnostico.csv"
    diagnostico.to_csv(saida, index=False, encoding="utf-8")
    print(f"  diagnostico da PCA salvo em: {saida}")


def construir_hbfei(painel: pd.DataFrame) -> pd.DataFrame:
    x2_x3 = carregar_x2_x3()
    painel = painel.merge(x2_x3, on="iso3", how="left", validate="many_to_one")

    colunas_x1 = identificar_colunas_x1(painel)
    if not colunas_x1:
        raise RuntimeError(
            "Nenhuma coluna faostat_* encontrada no painel — verifique as etapas 01 e 04."
        )

    print(f"  colunas usadas em X1: {colunas_x1}")
    painel["x1_consumo_total"] = painel[colunas_x1].sum(axis=1, min_count=1)

    componentes = [
        "x1_consumo_total",
        "x2_proporcao_muito_quente",
        "x3_classificacao_0_2",
    ]
    disponiveis = [col for col in componentes if painel[col].notna().any()]
    if len(disponiveis) < 2:
        raise RuntimeError(
            f"PCA exige ao menos dois componentes com dados; disponiveis={disponiveis}"
        )

    dados = painel[disponiveis].copy()
    linhas_completas = dados.dropna()
    paises_completos = painel.loc[linhas_completas.index, "iso3"].nunique()

    if len(linhas_completas) < 10 or paises_completos < 5:
        raise RuntimeError(
            "Amostra insuficiente para PCA: "
            f"{len(linhas_completas)} pais-anos e {paises_completos} paises completos."
        )

    print(
        f"  PCA complete-case: {len(linhas_completas)} pais-anos, "
        f"{paises_completos} paises, componentes={disponiveis}"
    )

    scaler = StandardScaler()
    z = scaler.fit_transform(linhas_completas)
    pca = PCA(n_components=1)
    pc1_bruto = pca.fit_transform(z).ravel()

    # O sinal de um componente principal e arbitrario. Para que a interpretacao
    # seja estavel, orientamos o PC1 para carga positiva em X1: HBFEI maior deve
    # significar maior exposicao, nunca o contrario por mero detalhe numerico.
    indice_x1 = disponiveis.index("x1_consumo_total") if "x1_consumo_total" in disponiveis else 0
    sinal = 1.0 if pca.components_[0, indice_x1] >= 0 else -1.0
    pc1 = pc1_bruto * sinal

    painel["hbfei"] = np.nan
    painel.loc[linhas_completas.index, "hbfei"] = pc1

    variancia = pca.explained_variance_ratio_[0]
    cargas = dict(zip(disponiveis, (pca.components_[0] * sinal).round(6)))
    print(f"  variancia explicada pelo PC1: {variancia * 100:.1f}%")
    print(f"  cargas orientadas do PC1: {cargas}")

    salvar_diagnostico_pca(
        disponiveis,
        scaler,
        pca,
        sinal,
        len(linhas_completas),
        paises_completos,
    )
    return painel


def alfa_cronbach_padronizado(df: pd.DataFrame, colunas: list[str]) -> float:
    dados = df[colunas].dropna()
    if dados.shape[0] < 3 or dados.shape[1] < 2:
        return float("nan")

    z = (dados - dados.mean()) / dados.std(ddof=1)
    k = z.shape[1]
    variancias_itens = z.var(axis=0, ddof=1).sum()
    variancia_total = z.sum(axis=1).var(ddof=1)
    if variancia_total <= 0:
        return float("nan")
    return (k / (k - 1)) * (1 - variancias_itens / variancia_total)


def main():
    PROC_DIR.mkdir(parents=True, exist_ok=True)
    painel = carregar_painel()
    painel = construir_hbfei(painel)

    colunas_alfa = [
        col
        for col in [
            "x1_consumo_total",
            "x2_proporcao_muito_quente",
            "x3_classificacao_0_2",
        ]
        if col in painel.columns
    ]
    alfa = alfa_cronbach_padronizado(painel, colunas_alfa)
    if np.isnan(alfa):
        print("\nAlfa de Cronbach padronizado: nao calculavel")
    else:
        print(f"\nAlfa de Cronbach padronizado: {alfa:.3f}")

    saida = PROC_DIR / "painel_pais_ano_com_hbfei.csv"
    painel.to_csv(saida, index=False, encoding="utf-8")
    print(f"Salvo em: {saida}")


if __name__ == "__main__":
    main()
