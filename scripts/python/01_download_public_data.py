"""
01_download_public_data.py
---------------------------
Baixa automaticamente, via API publica (sem necessidade de chave), os
dados de:
    - World Bank (PIB, urbanizacao, expectativa de vida, alfabetizacao)
    - FAOSTAT (consumo per capita de cha/cafe/mate -> componente X1 do HBFEI)
    - WHO GHO (tabagismo, alcool, IMC, indice UHC)

Como rodar (cmd, na raiz do projeto):
    python scripts\\python\\01_download_public_data.py

Nao precisa de nenhuma chave de API. Todas as fontes aqui sao publicas.
"""

import sys
import time
import json
from pathlib import Path

import requests
import pandas as pd
import yaml

BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "config.yaml"
RAW_API_DIR = BASE_DIR / "data" / "raw" / "api"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "pesquisa-academica-unip-sorocaba/1.0"})


def carregar_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ============================================================
# WORLD BANK
# ============================================================
def baixar_world_bank(indicador_codigo: str, ano_ini: int, ano_fim: int) -> pd.DataFrame:
    """Baixa uma serie de indicador do World Bank para todos os paises."""
    url = (
        f"https://api.worldbank.org/v2/country/all/indicator/{indicador_codigo}"
        f"?format=json&date={ano_ini}:{ano_fim}&per_page=20000"
    )
    resp = SESSION.get(url, timeout=60)
    resp.raise_for_status()
    payload = resp.json()

    if not isinstance(payload, list) or len(payload) < 2 or payload[1] is None:
        print(f"  [aviso] resposta vazia para o indicador {indicador_codigo}")
        return pd.DataFrame()

    registros = payload[1]
    linhas = []
    for r in registros:
        linhas.append({
            "iso3": r.get("countryiso3code"),
            "pais": r.get("country", {}).get("value"),
            "ano": int(r["date"]) if r.get("date") else None,
            "indicador": indicador_codigo,
            "valor": r.get("value"),
        })
    return pd.DataFrame(linhas)


def rodar_world_bank(cfg: dict):
    print("\n=== World Bank (WDI) ===")
    ano_ini = cfg["periodo"]["ano_inicio"]
    ano_fim = cfg["periodo"]["ano_fim"]
    indicadores = cfg["world_bank_indicadores"]

    todos = []
    for nome, codigo in indicadores.items():
        print(f"  baixando {nome} ({codigo}) ...")
        df = baixar_world_bank(codigo, ano_ini, ano_fim)
        if not df.empty:
            df["nome_indicador"] = nome
            todos.append(df)
        time.sleep(0.5)  # gentileza com o servidor

    if todos:
        painel = pd.concat(todos, ignore_index=True)
        saida = RAW_API_DIR / "world_bank_indicadores.csv"
        painel.to_csv(saida, index=False, encoding="utf-8")
        print(f"  salvo em: {saida}  ({len(painel)} linhas)")
    else:
        print("  [erro] nenhum dado do World Bank foi baixado")


# ============================================================
# FAOSTAT
# ============================================================
FAOSTAT_BASE = "https://fenixservices.fao.org/faostat/api/v1/en"


def buscar_itens_faostat(dominio: str, palavra_chave: str) -> pd.DataFrame:
    """Procura codigos de item do FAOSTAT que contenham a palavra-chave."""
    url = f"{FAOSTAT_BASE}/definitions/types/item?datasource={dominio}"
    resp = SESSION.get(url, timeout=60)
    resp.raise_for_status()
    dados = resp.json().get("data", [])
    df = pd.DataFrame(dados)
    if df.empty:
        return df
    col_nome = "Item" if "Item" in df.columns else df.columns[df.columns.str.contains("Item", case=False)][0]
    filtro = df[col_nome].astype(str).str.contains(palavra_chave, case=False, na=False)
    return df[filtro]


def buscar_elementos_faostat(dominio: str, palavra_chave: str) -> pd.DataFrame:
    url = f"{FAOSTAT_BASE}/definitions/types/element?datasource={dominio}"
    resp = SESSION.get(url, timeout=60)
    resp.raise_for_status()
    dados = resp.json().get("data", [])
    df = pd.DataFrame(dados)
    if df.empty:
        return df
    col_nome = "Element" if "Element" in df.columns else df.columns[df.columns.str.contains("Element", case=False)][0]
    filtro = df[col_nome].astype(str).str.contains(palavra_chave, case=False, na=False)
    return df[filtro]


def baixar_faostat(dominio: str, item_codes: list, element_codes: list, ano_ini: int, ano_fim: int) -> pd.DataFrame:
    anos = ",".join(str(a) for a in range(ano_ini, ano_fim + 1))
    itens = ",".join(str(c) for c in item_codes)
    elementos = ",".join(str(c) for c in element_codes)
    url = (
        f"{FAOSTAT_BASE}/data/{dominio}"
        f"?area_cs=ISO3&item={itens}&item_cs=FAO&element={elementos}&element_cs=FAO"
        f"&year={anos}&show_codes=true&show_unit=true&show_flags=false"
        f"&null_values=false&output_type=csv"
    )
    resp = SESSION.get(url, timeout=120)
    resp.raise_for_status()
    from io import StringIO
    return pd.read_csv(StringIO(resp.text))


def rodar_faostat(cfg: dict):
    print("\n=== FAOSTAT ===")
    dominio = cfg["faostat"]["dominio"]
    ano_ini = cfg["periodo"]["ano_inicio"]
    ano_fim = cfg["periodo"]["ano_fim"]

    print(f"  buscando elemento '{cfg['faostat']['elemento_busca']}' ...")
    elementos_df = buscar_elementos_faostat(dominio, "Food supply quantity")
    if elementos_df.empty:
        print("  [erro] nao encontrei o elemento no FAOSTAT — confira manualmente em:")
        print(f"  {FAOSTAT_BASE}/definitions/types/element?datasource={dominio}")
        return
    col_cod_elem = [c for c in elementos_df.columns if "Code" in c][0]
    element_codes = elementos_df[col_cod_elem].tolist()

    item_codes = []
    itens_encontrados = []
    for palavra in cfg["faostat"]["itens_busca"]:
        print(f"  buscando item '{palavra}' ...")
        itens_df = buscar_itens_faostat(dominio, palavra)
        if itens_df.empty:
            print(f"    [aviso] nenhum item encontrado para '{palavra}'")
            continue
        col_cod_item = [c for c in itens_df.columns if "Code" in c][0]
        item_codes.extend(itens_df[col_cod_item].tolist())
        itens_encontrados.append(itens_df)

    if not item_codes:
        print("  [erro] nenhum item encontrado — abortando FAOSTAT")
        return

    # salva o que foi encontrado para auditoria/conferencia
    if itens_encontrados:
        pd.concat(itens_encontrados, ignore_index=True).to_csv(
            RAW_API_DIR / "faostat_itens_encontrados.csv", index=False
        )

    print(f"  baixando dados ({len(item_codes)} itens, {len(element_codes)} elementos) ...")
    try:
        df = baixar_faostat(dominio, item_codes, element_codes, ano_ini, ano_fim)
    except Exception as e:
        print(f"  [erro] falha ao baixar FAOSTAT: {e}")
        print(f"  Baixe manualmente em https://www.fao.org/faostat/en/#data/{dominio} como alternativa.")
        return

    saida = RAW_API_DIR / "faostat_consumo_cha_cafe_mate.csv"
    df.to_csv(saida, index=False, encoding="utf-8")
    print(f"  salvo em: {saida}  ({len(df)} linhas)")


# ============================================================
# WHO GHO
# ============================================================
GHO_BASE = "https://ghoapi.azureedge.net/api"


def buscar_indicadores_gho(palavra_chave: str) -> pd.DataFrame:
    url = f"{GHO_BASE}/Indicator?$filter=contains(IndicatorName,'{palavra_chave}')"
    resp = SESSION.get(url, timeout=60)
    resp.raise_for_status()
    return pd.DataFrame(resp.json().get("value", []))


def baixar_indicador_gho(codigo: str) -> pd.DataFrame:
    url = f"{GHO_BASE}/{codigo}"
    resp = SESSION.get(url, timeout=120)
    resp.raise_for_status()
    return pd.DataFrame(resp.json().get("value", []))


def rodar_who_gho(cfg: dict):
    print("\n=== WHO GHO ===")
    confirmados = cfg["who_gho"].get("codigos_confirmados") or {}

    if not confirmados:
        print("  Nenhum codigo confirmado em config.yaml ainda.")
        print("  Vou BUSCAR candidatos pelas palavras-chave e salvar um CSV para voce escolher.")
        candidatos = []
        for tema, palavra in cfg["who_gho"]["palavras_chave_busca"].items():
            print(f"  buscando candidatos para '{tema}' ({palavra}) ...")
            try:
                df = buscar_indicadores_gho(palavra)
            except Exception as e:
                print(f"    [erro] {e}")
                continue
            if not df.empty:
                df["tema"] = tema
                candidatos.append(df[["tema", "IndicatorCode", "IndicatorName"]])
            time.sleep(0.3)

        if candidatos:
            resultado = pd.concat(candidatos, ignore_index=True)
            saida = RAW_API_DIR / "who_gho_candidatos_indicadores.csv"
            resultado.to_csv(saida, index=False, encoding="utf-8")
            print(f"\n  Candidatos salvos em: {saida}")
            print("  ABRA esse arquivo, escolha o IndicatorCode certo para cada tema,")
            print("  cole em config.yaml -> who_gho.codigos_confirmados e rode este")
            print("  script de novo para baixar os dados de fato.")
        else:
            print("  [erro] nenhum candidato encontrado — confira sua internet ou as palavras-chave")
        return

    print("  codigos confirmados encontrados em config.yaml, baixando dados ...")
    todos = []
    for tema, codigo in confirmados.items():
        print(f"  baixando {tema} ({codigo}) ...")
        try:
            df = baixar_indicador_gho(codigo)
        except Exception as e:
            print(f"    [erro] {e}")
            continue
        if not df.empty:
            df["tema"] = tema
            todos.append(df)
        time.sleep(0.3)

    if todos:
        painel = pd.concat(todos, ignore_index=True)
        saida = RAW_API_DIR / "who_gho_indicadores.csv"
        painel.to_csv(saida, index=False, encoding="utf-8")
        print(f"  salvo em: {saida}  ({len(painel)} linhas)")


# ============================================================
# MAIN
# ============================================================
def main():
    RAW_API_DIR.mkdir(parents=True, exist_ok=True)
    cfg = carregar_config()

    rodar_world_bank(cfg)
    rodar_faostat(cfg)
    rodar_who_gho(cfg)

    print("\nConcluido. Confira os arquivos em data/raw/api/")


if __name__ == "__main__":
    main()
