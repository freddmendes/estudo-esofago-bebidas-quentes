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

Este script isola falhas por fonte: se o FAOSTAT ou o WHO GHO estiverem
temporariamente fora do ar, isso NAO impede as outras fontes de rodar —
cada uma roda dentro do seu proprio bloco de protecao, e o script sempre
chega ao fim, avisando no final quais fontes falharam.
"""

import time
from pathlib import Path

import requests
import pandas as pd
import yaml

BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "config.yaml"
RAW_API_DIR = BASE_DIR / "data" / "raw" / "api"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "pesquisa-academica-unip-sorocaba/1.0"})


def get_com_retentativa(url: str, tentativas: int = 3, espera_segundos: int = 8, **kwargs):
    """
    Faz um GET com retentativas automaticas. Servidores publicos (FAOSTAT,
    WHO GHO) as vezes ficam temporariamente fora do ar (erro 5xx) — isso
    nao e um bug do nosso codigo, e uma instabilidade do lado deles.
    """
    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            resp = SESSION.get(url, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            ultimo_erro = e
            print(f"    [tentativa {tentativa}/{tentativas} falhou: {e}]")
            if tentativa < tentativas:
                print(f"    aguardando {espera_segundos}s antes de tentar de novo...")
                time.sleep(espera_segundos)
    raise ultimo_erro


def carregar_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ============================================================
# WORLD BANK
# ============================================================
def baixar_world_bank(indicador_codigo: str, ano_ini: int, ano_fim: int) -> pd.DataFrame:
    url = (
        f"https://api.worldbank.org/v2/country/all/indicator/{indicador_codigo}"
        f"?format=json&date={ano_ini}:{ano_fim}&per_page=20000"
    )
    resp = get_com_retentativa(url, timeout=60)
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
        try:
            df = baixar_world_bank(codigo, ano_ini, ano_fim)
        except Exception as e:
            print(f"  [erro] falhou o indicador {nome}: {e}")
            continue
        if not df.empty:
            df["nome_indicador"] = nome
            todos.append(df)
        time.sleep(0.5)

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
    url = f"{FAOSTAT_BASE}/definitions/types/item?datasource={dominio}"
    resp = get_com_retentativa(url, timeout=60)
    dados = resp.json().get("data", [])
    df = pd.DataFrame(dados)
    if df.empty:
        return df
    col_nome = "Item" if "Item" in df.columns else df.columns[df.columns.str.contains("Item", case=False)][0]
    filtro = df[col_nome].astype(str).str.contains(palavra_chave, case=False, na=False)
    return df[filtro]


def buscar_elementos_faostat(dominio: str, palavra_chave: str) -> pd.DataFrame:
    url = f"{FAOSTAT_BASE}/definitions/types/element?datasource={dominio}"
    resp = get_com_retentativa(url, timeout=60)
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
    resp = get_com_retentativa(url, timeout=120)
    from io import StringIO
    return pd.read_csv(StringIO(resp.text))


def rodar_faostat(cfg: dict):
    print("\n=== FAOSTAT ===")
    dominio = cfg["faostat"]["dominio"]
    ano_ini = cfg["periodo"]["ano_inicio"]
    ano_fim = cfg["periodo"]["ano_fim"]

    print(f"  buscando elemento '{cfg['faostat']['elemento_busca']}' ...")
    try:
        elementos_df = buscar_elementos_faostat(dominio, "Food supply quantity")
    except Exception as e:
        print(f"  [erro] FAOSTAT indisponivel no momento ({e}) — pulando esta fonte.")
        print(f"  Rode o pipeline de novo mais tarde para tentar so o FAOSTAT.")
        return
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
        try:
            itens_df = buscar_itens_faostat(dominio, palavra)
        except Exception as e:
            print(f"    [erro] falhou a busca de '{palavra}': {e}")
            continue
        if itens_df.empty:
            print(f"    [aviso] nenhum item encontrado para '{palavra}'")
            continue
        col_cod_item = [c for c in itens_df.columns if "Code" in c][0]
        item_codes.extend(itens_df[col_cod_item].tolist())
        itens_encontrados.append(itens_df)

    if not item_codes:
        print("  [erro] nenhum item encontrado — abortando FAOSTAT")
        return

    if itens_encontrados:
        pd.concat(itens_encontrados, ignore_index=True).to_csv(
            RAW_API_DIR / "faostat_itens_encontrados.csv", index=False
        )

    print(f"  baixando dados ({len(item_codes)} itens, {len(element_codes)} elementos) ...")
    try:
        df = baixar_faostat(dominio, item_codes, element_codes, ano_ini, ano_fim)
    except Exception as e:
        print(f"  [erro] falha ao baixar FAOSTAT: {e}")
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
    resp = get_com_retentativa(url, timeout=60)
    return pd.DataFrame(resp.json().get("value", []))


def baixar_indicador_gho(codigo: str) -> pd.DataFrame:
    url = f"{GHO_BASE}/{codigo}"
    resp = get_com_retentativa(url, timeout=120)
    return pd.DataFrame(resp.json().get("value", []))


def rodar_who_gho(cfg: dict):
    print("\n=== WHO GHO ===")
    confirmados = cfg["who_gho"].get("codigos_confirmados") or {}

    if not confirmados:
        print("  Nenhum codigo confirmado em config.yaml ainda.")
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
        else:
            print("  [erro] nenhum candidato encontrado")
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

    fontes_com_erro = []

    try:
        rodar_world_bank(cfg)
    except Exception as e:
        print(f"\n[erro] World Bank falhou por completo: {e}")
        fontes_com_erro.append("World Bank")

    try:
        rodar_faostat(cfg)
    except Exception as e:
        print(f"\n[erro] FAOSTAT falhou por completo: {e}")
        fontes_com_erro.append("FAOSTAT")

    try:
        rodar_who_gho(cfg)
    except Exception as e:
        print(f"\n[erro] WHO GHO falhou por completo: {e}")
        fontes_com_erro.append("WHO GHO")

    print("\n" + "=" * 50)
    if fontes_com_erro:
        print(f"Concluido COM AVISOS. Fontes que falharam: {', '.join(fontes_com_erro)}")
        print("Rode o script de novo mais tarde para tentar essas fontes de novo.")
    else:
        print("Concluido com sucesso em todas as fontes.")
    print("Confira os arquivos em data/raw/api/")


if __name__ == "__main__":
    main()
