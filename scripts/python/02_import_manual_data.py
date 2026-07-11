"""
02_import_manual_data.py
--------------------------
Le os arquivos que VOCE baixou manualmente e salvou em
data/raw/manual/{gbd,globocan,ci5,vignat2022}/ e padroniza cada um
para um formato comum (iso3, ano, causa, medida, valor).

Como rodar (cmd, na raiz do projeto):
    python scripts\\python\\02_import_manual_data.py

IMPORTANTE: os nomes de coluna exatos podem variar um pouco dependendo
de como voce configurou o download em cada site. Se o script avisar
"nao encontrei a coluna X", abra o CSV, veja o nome real da coluna, e
ajuste a lista em COLUNAS_POSSIVEIS logo abaixo (e so isso).
"""

import glob
from pathlib import Path

import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[2]
MANUAL_DIR = BASE_DIR / "data" / "raw" / "manual"
OUT_DIR = BASE_DIR / "data" / "intermediate"

# nomes de coluna alternativos que cada fonte costuma usar --
# o script tenta cada um ate achar
COLUNAS_POSSIVEIS = {
    "iso3": ["location_iso3", "iso3", "ISO3", "location_id", "Code"],
    "pais": ["location_name", "location", "Country", "pais", "Location"],
    "ano": ["year", "Year", "date", "ano"],
    "medida": ["measure_name", "measure", "Measure"],
    "causa": ["cause_name", "cause", "Cause"],
    "metrica": ["metric_name", "metric", "Metric"],
    "sexo": ["sex_name", "sex", "Sex"],
    "faixa_etaria": ["age_name", "age", "Age"],
    "valor": ["val", "value", "Value", "valor"],
    "limite_inferior": ["lower", "Lower", "ci_lower"],
    "limite_superior": ["upper", "Upper", "ci_upper"],
}


def achar_coluna(df: pd.DataFrame, opcoes: list):
    for op in opcoes:
        if op in df.columns:
            return op
    return None


def padronizar(df: pd.DataFrame, fonte: str) -> pd.DataFrame:
    novo = {}
    faltando = []
    for nome_padrao, opcoes in COLUNAS_POSSIVEIS.items():
        col = achar_coluna(df, opcoes)
        if col is not None:
            novo[nome_padrao] = df[col]
        else:
            faltando.append(nome_padrao)

    if faltando:
        print(f"    [aviso] em '{fonte}', nao encontrei colunas para: {faltando}")
        print(f"    colunas disponiveis no arquivo: {list(df.columns)}")

    resultado = pd.DataFrame(novo)
    resultado["fonte"] = fonte
    return resultado


def ler_pasta(pasta: Path, fonte: str) -> pd.DataFrame:
    arquivos = list(pasta.glob("*.csv")) + list(pasta.glob("*.xlsx")) + list(pasta.glob("*.xls"))
    arquivos = [a for a in arquivos if not a.name.startswith("~")]

    if not arquivos:
        print(f"  [vazio] nenhum arquivo encontrado em {pasta} — pulei esta fonte."
              f" Veja o README.md dessa pasta para saber o que baixar.")
        return pd.DataFrame()

    partes = []
    for arq in arquivos:
        print(f"  lendo {arq.name} ...")
        try:
            if arq.suffix == ".csv":
                df = pd.read_csv(arq, low_memory=False)
            else:
                df = pd.read_excel(arq)
        except Exception as e:
            print(f"    [erro] nao consegui ler {arq.name}: {e}")
            continue
        partes.append(padronizar(df, fonte))

    if not partes:
        return pd.DataFrame()
    return pd.concat(partes, ignore_index=True)


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    fontes = {
        "gbd": MANUAL_DIR / "gbd",
        "globocan": MANUAL_DIR / "globocan",
        "ci5": MANUAL_DIR / "ci5",
        "vignat2022": MANUAL_DIR / "vignat2022",
    }

    for nome_fonte, pasta in fontes.items():
        print(f"\n=== {nome_fonte.upper()} ===")
        df = ler_pasta(pasta, nome_fonte)
        if df.empty:
            continue
        saida = OUT_DIR / f"{nome_fonte}_padronizado.csv"
        df.to_csv(saida, index=False, encoding="utf-8")
        print(f"  salvo em: {saida}  ({len(df)} linhas)")

    print("\nConcluido. Se alguma fonte ficou vazia, confira o README.md da pasta"
          " correspondente em data/raw/manual/.")


if __name__ == "__main__":
    main()
