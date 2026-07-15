"""
05_build_hbfei.py
-------------------
Constroi o Hot Beverage and Food Exposure Index (HBFEI), seguindo a
Secao 10.3 do protocolo: PCA sobre os componentes padronizados
(z-score) X1, X2, X3 (e X4 se disponivel).

    X1 = consumo per capita de cha/cafe/mate (FAOSTAT, automatico)
    X2 = proporcao que consome "muito quente" (CURADORIA MANUAL —
         preencher data/raw/manual/hbfei_x2_x3/template_x2_x3.csv)
    X3 = classificacao etnografica 0-2 (CURADORIA MANUAL — mesma planilha)

Como rodar (cmd, na raiz do projeto):
    python scripts\\python\\05_build_hbfei.py

Gera: data/processed/painel_pais_ano_com_hbfei.csv
"""

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
    return pd.read_csv(caminho, low_memory=False)


def _ler_csv_com_delimitador_flexivel(caminho: Path) -> pd.DataFrame:
    """
    Le o CSV tentando descobrir o delimitador sozinho. E comum, ao editar
    uma planilha colada de outro lugar (Excel em pt-BR, Google Sheets,
    editor web do GitHub), o arquivo sair com ';' em vez de ',' — ou com
    espacos extras nos nomes das colunas. Esta funcao tenta lidar com
    isso automaticamente em vez de travar o pipeline inteiro.
    """
    df = pd.read_csv(caminho, sep=None, engine="python")
    df.columns = [c.strip() for c in df.columns]
    return df


def _achar_coluna(df: pd.DataFrame, pistas: list) -> str | None:
    """Acha uma coluna cujo nome contenha TODAS as pistas (case-insensitive)."""
    for col in df.columns:
        nome = col.lower().replace(" ", "").replace("-", "_")
        if all(pista in nome for pista in pistas):
            return col
    return None


def carregar_x2_x3() -> pd.DataFrame:
    caminho = MANUAL_DIR / "template_x2_x3.csv"
    df = _ler_csv_com_delimitador_flexivel(caminho)

    col_iso3 = _achar_coluna(df, ["iso3"])
    col_x2 = _achar_coluna(df, ["x2", "proporcao"])
    col_x3 = _achar_coluna(df, ["x3", "classific"])

    faltando = [nome for nome, col in
                [("iso3", col_iso3), ("x2_proporcao_muito_quente", col_x2), ("x3_classificacao_0_2", col_x3)]
                if col is None]
    if faltando:
        print(f"  [erro] nao encontrei as colunas {faltando} em template_x2_x3.csv")
        print(f"  Colunas que EXISTEM no arquivo agora: {list(df.columns)}")
        print("  Confira se o cabecalho da planilha nao foi alterado sem querer ao editar")
        print("  no navegador (nomes de coluna devem bater com o template original).")
        raise KeyError(f"colunas faltando em template_x2_x3.csv: {faltando}")

    df = df.rename(columns={
        col_iso3: "iso3",
        col_x2: "x2_proporcao_muito_quente",
        col_x3: "x3_classificacao_0_2",
    })

    # converte para numero; valores nao numericos (texto solto, "GAP" etc.) viram NaN
    # em vez de quebrar o script
    df["x2_proporcao_muito_quente"] = pd.to_numeric(df["x2_proporcao_muito_quente"], errors="coerce")
    df["x3_classificacao_0_2"] = pd.to_numeric(df["x3_classificacao_0_2"], errors="coerce")

    preenchidos = df.dropna(subset=["x2_proporcao_muito_quente", "x3_classificacao_0_2"], how="all")
    if preenchidos.empty:
        print("  [aviso] a planilha template_x2_x3.csv ainda esta vazia (sem X2/X3 preenchidos).")
        print("  O HBFEI sera calculado so com X1 (FAOSTAT) ate voce preencher essa planilha —")
        print("  isso e uma limitacao REAL do indice, nao um bug: X2/X3 exigem revisao de")
        print("  literatura (Secao 10.1 do protocolo), nao podem ser inventados.")
    else:
        print(f"  {len(preenchidos)} pais(es) com X2 e/ou X3 preenchido(s).")

    return df[["iso3", "x2_proporcao_muito_quente", "x3_classificacao_0_2"]]


def identificar_colunas_x1(painel: pd.DataFrame) -> list:
    return [c for c in painel.columns if c.startswith("faostat_")]


def construir_hbfei(painel: pd.DataFrame) -> pd.DataFrame:
    x2_x3 = carregar_x2_x3()
    painel = painel.merge(x2_x3, on="iso3", how="left")

    colunas_x1 = identificar_colunas_x1(painel)
    if not colunas_x1:
        raise RuntimeError("Nenhuma coluna faostat_* encontrada no painel — rode 01 e 04 antes.")

    # X1: soma dos componentes de cha/cafe/mate (kg/capita/ano)
    painel["x1_consumo_total"] = painel[colunas_x1].sum(axis=1, min_count=1)

    componentes = ["x1_consumo_total", "x2_proporcao_muito_quente", "x3_classificacao_0_2"]
    disponiveis = [c for c in componentes if painel[c].notna().any()]

    if len(disponiveis) < 2:
        print("  [aviso] menos de 2 componentes disponiveis — PCA nao e recomendavel ainda.")
        painel["hbfei"] = painel.get("x1_consumo_total")
        return painel

    dados = painel[disponiveis].copy()
    linhas_completas = dados.dropna()

    if len(linhas_completas) < 10:
        print(f"  [aviso] so {len(linhas_completas)} linhas completas para PCA — "
              f"preencha mais X2/X3 na planilha antes de confiar no HBFEI.")

    scaler = StandardScaler()
    z = scaler.fit_transform(linhas_completas)

    pca = PCA(n_components=1)
    pc1 = pca.fit_transform(z).flatten()

    print(f"  variancia explicada pelo PC1: {pca.explained_variance_ratio_[0]*100:.1f}%")

    painel["hbfei"] = np.nan
    painel.loc[linhas_completas.index, "hbfei"] = pc1

    return painel


def alfa_cronbach(df: pd.DataFrame, colunas: list) -> float:
    """Alfa de Cronbach simples, sem dependencia externa."""
    dados = df[colunas].dropna()
    if dados.shape[0] < 3 or dados.shape[1] < 2:
        return float("nan")
    k = dados.shape[1]
    variancias_itens = dados.var(axis=0, ddof=1).sum()
    variancia_total = dados.sum(axis=1).var(ddof=1)
    if variancia_total == 0:
        return float("nan")
    return (k / (k - 1)) * (1 - variancias_itens / variancia_total)


def main():
    painel = carregar_painel()
    painel = construir_hbfei(painel)

    colunas_alfa = [c for c in ["x1_consumo_total", "x2_proporcao_muito_quente", "x3_classificacao_0_2"]
                    if c in painel.columns]
    alfa = alfa_cronbach(painel, colunas_alfa)
    print(f"\nAlfa de Cronbach (componentes do HBFEI): {alfa:.3f}" if not np.isnan(alfa)
          else "\nAlfa de Cronbach: nao calculavel ainda (poucos dados completos)")

    saida = PROC_DIR / "painel_pais_ano_com_hbfei.csv"
    painel.to_csv(saida, index=False, encoding="utf-8")
    print(f"Salvo em: {saida}")
    print("\nProximo passo: rodar os scripts R (00_install_packages.R, depois "
          "06_imputation.R, 07_primary_models.R, 08_sensitivity_models.R)")


if __name__ == "__main__":
    main()
