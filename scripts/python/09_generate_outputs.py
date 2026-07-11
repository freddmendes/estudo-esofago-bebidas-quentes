"""
09_generate_outputs.py
------------------------
Le as tabelas geradas pelos scripts R (outputs/tables/*.csv) e monta
as figuras descritivas basicas do manuscrito (Secao 21 do protocolo):
    - Figura 2: dispersao HBFEI x log(ASR), ESCC vs EAC
    - Figura 4: forest plot das analises de sensibilidade

Como rodar (cmd, na raiz do projeto):
    python scripts\\python\\09_generate_outputs.py

As Figuras 1 (mapas) e 3 (splines) ja sao produzidas dentro dos
proprios scripts R (pacotes sf/rnaturalearth e rms), pois dependem
diretamente dos objetos de modelo la gerados.
"""

from pathlib import Path

import pandas as pd
import matplotlib.pyplot as plt

BASE_DIR = Path(__file__).resolve().parents[2]
PROC_DIR = BASE_DIR / "data" / "processed"
TABLES_DIR = BASE_DIR / "outputs" / "tables"
FIGURES_DIR = BASE_DIR / "outputs" / "figures"


def figura_dispersao_hbfei():
    caminho = PROC_DIR / "painel_pais_ano_com_hbfei.csv"
    if not caminho.exists():
        print("  [aviso] painel com HBFEI nao encontrado — rode 05_build_hbfei.py")
        return

    df = pd.read_csv(caminho, low_memory=False)
    if "hbfei" not in df.columns or "asr_incidence" not in df.columns:
        print("  [aviso] colunas hbfei/asr_incidence nao encontradas no painel")
        return

    df_plot = df.dropna(subset=["hbfei", "asr_incidence"])
    df_plot = df_plot[df_plot["asr_incidence"] > 0]

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.scatter(df_plot["hbfei"], df_plot["asr_incidence"].apply(lambda x: x).__pow__(1), alpha=0.5)
    ax.set_yscale("log")
    ax.set_xlabel("HBFEI (indice de exposicao)")
    ax.set_ylabel("ASR incidencia cancer de esofago (log)")
    ax.set_title("Figura 2 (preliminar) — HBFEI x ASR")
    fig.tight_layout()

    saida = FIGURES_DIR / "figura2_dispersao_hbfei_asr.png"
    fig.savefig(saida, dpi=300)
    plt.close(fig)
    print(f"  salvo: {saida}")


def figura_forest_sensibilidade():
    caminho = TABLES_DIR / "jackknife_leave_one_out.csv"
    if not caminho.exists():
        print("  [aviso] jackknife_leave_one_out.csv nao encontrado — rode 08_sensitivity_models.R")
        return

    df = pd.read_csv(caminho).sort_values("coeficiente_hbfei")

    fig, ax = plt.subplots(figsize=(7, max(4, len(df) * 0.25)))
    ax.errorbar(df["coeficiente_hbfei"], range(len(df)), fmt="o", capsize=3)
    ax.set_yticks(range(len(df)))
    ax.set_yticklabels(df["pais_excluido"], fontsize=6)
    ax.axvline(x=df["coeficiente_hbfei"].median(), linestyle="--", color="gray")
    ax.set_xlabel("Coeficiente do HBFEI (excluindo 1 pais por vez)")
    ax.set_title("Figura 4 (preliminar) — Leave-one-country-out")
    fig.tight_layout()

    saida = FIGURES_DIR / "figura4_jackknife.png"
    fig.savefig(saida, dpi=300)
    plt.close(fig)
    print(f"  salvo: {saida}")


def tabela1_descritiva():
    caminho = PROC_DIR / "painel_pais_ano_com_hbfei.csv"
    if not caminho.exists():
        return
    df = pd.read_csv(caminho, low_memory=False)
    if "hbfei" not in df.columns:
        return

    df = df.dropna(subset=["hbfei"]).copy()
    df["quartil_hbfei"] = pd.qcut(df["hbfei"], 4, labels=["Q1", "Q2", "Q3", "Q4"], duplicates="drop")

    colunas_resumo = [c for c in df.columns if c.startswith("asr_") or c in
                      ["tabagismo", "alcool", "frutas", "vegetais", "sdi"]]
    if not colunas_resumo:
        return

    tabela1 = df.groupby("quartil_hbfei")[colunas_resumo].mean(numeric_only=True)
    saida = TABLES_DIR / "tabela1_descritiva_por_quartil.csv"
    tabela1.to_csv(saida)
    print(f"  salvo: {saida}")


def main():
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    print("=== Tabela 1 (descritiva por quartil do HBFEI) ===")
    tabela1_descritiva()

    print("\n=== Figura 2 (dispersao HBFEI x ASR) ===")
    figura_dispersao_hbfei()

    print("\n=== Figura 4 (forest plot jackknife) ===")
    figura_forest_sensibilidade()

    print("\nConcluido. Veja outputs/tables/ e outputs/figures/")


if __name__ == "__main__":
    main()
