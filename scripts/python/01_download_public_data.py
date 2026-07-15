"""
01_download_public_data.py
---------------------------
Baixa dados publicos do World Bank e WHO GHO e prepara o FAOSTAT.

Para o FAOSTAT, o pipeline usa uma estrategia reprodutivel de fallback:
    1. se data/raw/manual/faostat_manual.csv existir, usa o arquivo estatico;
    2. caso contrario, tenta a API publica do FAOSTAT.

Independentemente da origem, o artefato produzido tem o mesmo contrato:
    data/raw/api/faostat_consumo_cha_cafe_mate.csv

Colunas canonicas:
    iso3, pais, ano, item, consumo_kg_capita, unidade, flag, origem
"""

from __future__ import annotations

import time
from io import StringIO
from pathlib import Path

import pandas as pd
import pycountry
import requests
import yaml

BASE_DIR = Path(__file__).resolve().parents[2]
CONFIG_PATH = BASE_DIR / "config.yaml"
RAW_API_DIR = BASE_DIR / "data" / "raw" / "api"
RAW_MANUAL_DIR = BASE_DIR / "data" / "raw" / "manual"

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "pesquisa-academica-unip-sorocaba/1.0"})


def get_com_retentativa(url: str, tentativas: int = 3, espera_segundos: int = 8, **kwargs):
    """Faz GET com retentativas para fontes publicas instaveis."""
    ultimo_erro = None
    for tentativa in range(1, tentativas + 1):
        try:
            resp = SESSION.get(url, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as erro:
            ultimo_erro = erro
            print(f"    [tentativa {tentativa}/{tentativas} falhou: {erro}]")
            if tentativa < tentativas:
                print(f"    aguardando {espera_segundos}s antes de tentar de novo...")
                time.sleep(espera_segundos)
    raise ultimo_erro


def carregar_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as arquivo:
        return yaml.safe_load(arquivo)


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

    linhas = []
    for registro in payload[1]:
        linhas.append(
            {
                "iso3": registro.get("countryiso3code"),
                "pais": registro.get("country", {}).get("value"),
                "ano": int(registro["date"]) if registro.get("date") else None,
                "indicador": indicador_codigo,
                "valor": registro.get("value"),
            }
        )
    return pd.DataFrame(linhas)


def rodar_world_bank(cfg: dict) -> bool:
    print("\n=== World Bank (WDI) ===")
    ano_ini = cfg["periodo"]["ano_inicio"]
    ano_fim = cfg["periodo"]["ano_fim"]

    todos = []
    for nome, codigo in cfg["world_bank_indicadores"].items():
        print(f"  baixando {nome} ({codigo}) ...")
        try:
            df = baixar_world_bank(codigo, ano_ini, ano_fim)
        except Exception as erro:
            print(f"  [erro] falhou o indicador {nome}: {erro}")
            continue
        if not df.empty:
            df["nome_indicador"] = nome
            todos.append(df)
        time.sleep(0.5)

    if not todos:
        print("  [erro] nenhum dado do World Bank foi baixado")
        return False

    painel = pd.concat(todos, ignore_index=True)
    saida = RAW_API_DIR / "world_bank_indicadores.csv"
    painel.to_csv(saida, index=False, encoding="utf-8")
    print(f"  salvo em: {saida}  ({len(painel)} linhas)")
    return True


# ============================================================
# FAOSTAT
# ============================================================
FAOSTAT_BASE = "https://fenixservices.fao.org/faostat/api/v1/en"
ITENS_HBFEI = {
    "coffee and products": "Coffee and products",
    "tea (including mate)": "Tea (including mate)",
}


def _achar_coluna(df: pd.DataFrame, nomes_exatos: tuple[str, ...], contem: tuple[str, ...] = ()) -> str | None:
    mapa = {str(col).strip().lower(): col for col in df.columns}
    for nome in nomes_exatos:
        if nome.lower() in mapa:
            return mapa[nome.lower()]

    if contem:
        for col in df.columns:
            texto = str(col).strip().lower()
            if all(parte.lower() in texto for parte in contem):
                return col
    return None


def _m49_para_iso3(valor) -> str | None:
    if pd.isna(valor):
        return None
    texto = str(valor).strip()
    if texto.endswith(".0"):
        texto = texto[:-2]
    codigo = texto.zfill(3)
    pais = pycountry.countries.get(numeric=codigo)
    return pais.alpha_3 if pais else None


def _normalizar_item(valor) -> str | None:
    texto = " ".join(str(valor).strip().lower().split())
    return ITENS_HBFEI.get(texto)


def normalizar_faostat(df: pd.DataFrame, cfg: dict, origem: str) -> pd.DataFrame:
    """Converte exportacao manual ou resposta da API para contrato canonico."""
    col_pais = _achar_coluna(df, ("Area", "pais", "Country"))
    col_iso3 = _achar_coluna(df, ("iso3", "Area Code (ISO3)", "ISO3 Code"))
    col_m49 = _achar_coluna(df, ("Area Code (M49)", "M49 Code"))
    col_ano = _achar_coluna(df, ("Year", "ano"))
    col_item = _achar_coluna(df, ("Item", "item"))
    col_valor = _achar_coluna(df, ("Value", "valor", "consumo_kg_capita"))
    col_unidade = _achar_coluna(df, ("Unit", "unidade"))
    col_elemento = _achar_coluna(df, ("Element", "elemento"))
    col_flag = _achar_coluna(df, ("Flag", "flag"))

    obrigatorias = {
        "pais": col_pais,
        "ano": col_ano,
        "item": col_item,
        "valor": col_valor,
    }
    faltando = [nome for nome, coluna in obrigatorias.items() if coluna is None]
    if faltando:
        raise ValueError(
            f"FAOSTAT ({origem}): colunas obrigatorias ausentes: {faltando}. "
            f"Colunas encontradas: {list(df.columns)}"
        )
    if col_iso3 is None and col_m49 is None:
        raise ValueError(
            "FAOSTAT: nao encontrei codigo ISO3 nem Area Code (M49); "
            "nao e seguro harmonizar apenas pelo nome do pais."
        )

    trabalho = pd.DataFrame(
        {
            "pais": df[col_pais].astype("string").str.strip(),
            "ano": pd.to_numeric(df[col_ano], errors="coerce"),
            "item": df[col_item].map(_normalizar_item),
            "consumo_kg_capita": pd.to_numeric(df[col_valor], errors="coerce"),
            "unidade": df[col_unidade].astype("string").str.strip() if col_unidade else "kg/cap",
            "flag": df[col_flag].astype("string").str.strip() if col_flag else pd.NA,
        }
    )

    if col_iso3 is not None:
        iso_bruto = df[col_iso3].astype("string").str.strip().str.upper()
        trabalho["iso3"] = iso_bruto.where(iso_bruto.str.fullmatch(r"[A-Z]{3}", na=False))
    else:
        trabalho["iso3"] = df[col_m49].map(_m49_para_iso3)

    if col_elemento is not None:
        elemento_esperado = str(cfg["faostat"]["elemento_busca"]).strip().lower()
        mascara_elemento = df[col_elemento].astype(str).str.strip().str.lower().eq(elemento_esperado)
        trabalho = trabalho[mascara_elemento].copy()

    ano_ini = int(cfg["periodo"]["ano_inicio"])
    ano_fim = int(cfg["periodo"]["ano_fim"])
    trabalho = trabalho[
        trabalho["ano"].between(ano_ini, ano_fim, inclusive="both")
        & trabalho["item"].notna()
        & trabalho["consumo_kg_capita"].notna()
    ].copy()

    trabalho["ano"] = trabalho["ano"].astype(int)
    trabalho["origem"] = origem

    nao_mapeados = trabalho[trabalho["iso3"].isna()]["pais"].dropna().drop_duplicates().tolist()
    if nao_mapeados:
        print(
            "  [aviso] areas sem ISO3 foram excluidas (geralmente agregados regionais): "
            + ", ".join(nao_mapeados[:15])
        )
    trabalho = trabalho[trabalho["iso3"].notna()].copy()

    duplicadas = trabalho.duplicated(["iso3", "ano", "item"], keep=False)
    if duplicadas.any():
        exemplo = trabalho.loc[duplicadas, ["iso3", "pais", "ano", "item"]].head(10)
        raise ValueError(
            "FAOSTAT: existem duplicidades em iso3+ano+item; nao sera aplicada media "
            f"silenciosa. Exemplos:\n{exemplo.to_string(index=False)}"
        )

    trabalho = trabalho[
        ["iso3", "pais", "ano", "item", "consumo_kg_capita", "unidade", "flag", "origem"]
    ].sort_values(["iso3", "ano", "item"], kind="stable")

    if trabalho.empty:
        raise ValueError("FAOSTAT: nenhuma linha valida restou apos os filtros.")

    itens_presentes = set(trabalho["item"].dropna().unique())
    itens_ausentes = set(ITENS_HBFEI.values()) - itens_presentes
    if itens_ausentes:
        raise ValueError(f"FAOSTAT: itens obrigatorios ausentes: {sorted(itens_ausentes)}")

    return trabalho.reset_index(drop=True)


def salvar_faostat_canonico(df: pd.DataFrame) -> Path:
    RAW_API_DIR.mkdir(parents=True, exist_ok=True)
    saida = RAW_API_DIR / "faostat_consumo_cha_cafe_mate.csv"
    df.to_csv(saida, index=False, encoding="utf-8")
    print(f"  salvo em: {saida}  ({len(df)} linhas)")
    print(
        f"  cobertura: {df['iso3'].nunique()} ISO3, "
        f"{df['ano'].min()}-{df['ano'].max()}, itens={sorted(df['item'].unique())}"
    )
    return saida


def carregar_faostat_manual(cfg: dict) -> pd.DataFrame:
    caminho_cfg = cfg.get("faostat", {}).get("arquivo_manual", "data/raw/manual/faostat_manual.csv")
    caminho = BASE_DIR / caminho_cfg
    if not caminho.exists():
        return pd.DataFrame()

    print(f"  arquivo manual encontrado: {caminho}")
    bruto = pd.read_csv(
        caminho,
        low_memory=False,
        dtype={"Area Code (M49)": "string", "Year Code": "string"},
    )
    return normalizar_faostat(bruto, cfg, origem="manual_faostat_web")


def buscar_itens_faostat(dominio: str, palavra_chave: str) -> pd.DataFrame:
    url = f"{FAOSTAT_BASE}/definitions/types/item?datasource={dominio}"
    resp = get_com_retentativa(url, timeout=60)
    dados = resp.json().get("data", [])
    df = pd.DataFrame(dados)
    if df.empty:
        return df
    col_nome = "Item" if "Item" in df.columns else df.columns[df.columns.str.contains("Item", case=False)][0]
    return df[df[col_nome].astype(str).str.contains(palavra_chave, case=False, na=False)]


def buscar_elementos_faostat(dominio: str, palavra_chave: str) -> pd.DataFrame:
    url = f"{FAOSTAT_BASE}/definitions/types/element?datasource={dominio}"
    resp = get_com_retentativa(url, timeout=60)
    dados = resp.json().get("data", [])
    df = pd.DataFrame(dados)
    if df.empty:
        return df
    col_nome = "Element" if "Element" in df.columns else df.columns[df.columns.str.contains("Element", case=False)][0]
    return df[df[col_nome].astype(str).str.contains(palavra_chave, case=False, na=False)]


def baixar_faostat(
    dominio: str,
    item_codes: list,
    element_codes: list,
    ano_ini: int,
    ano_fim: int,
) -> pd.DataFrame:
    anos = ",".join(str(ano) for ano in range(ano_ini, ano_fim + 1))
    itens = ",".join(str(codigo) for codigo in sorted(set(item_codes)))
    elementos = ",".join(str(codigo) for codigo in sorted(set(element_codes)))
    url = (
        f"{FAOSTAT_BASE}/data/{dominio}"
        f"?area_cs=ISO3&item={itens}&item_cs=FAO&element={elementos}&element_cs=FAO"
        f"&year={anos}&show_codes=true&show_unit=true&show_flags=true"
        f"&null_values=false&output_type=csv"
    )
    resp = get_com_retentativa(url, timeout=120)
    return pd.read_csv(StringIO(resp.text), low_memory=False)


def rodar_faostat(cfg: dict) -> bool:
    print("\n=== FAOSTAT ===")

    # Prioridade deliberada ao snapshot manual: elimina dependencia do servidor
    # externo e torna a mesma versao dos dados reproduzivel em todas as rodadas.
    manual = carregar_faostat_manual(cfg)
    if not manual.empty:
        salvar_faostat_canonico(manual)
        print("  fonte usada: CSV manual; a API FAOSTAT nao foi consultada.")
        return True

    print("  nenhum CSV manual encontrado; tentando a API FAOSTAT...")
    dominio = cfg["faostat"]["dominio"]
    ano_ini = cfg["periodo"]["ano_inicio"]
    ano_fim = cfg["periodo"]["ano_fim"]

    elementos_df = buscar_elementos_faostat(dominio, "Food supply quantity")
    if elementos_df.empty:
        raise RuntimeError("nao encontrei o elemento Food supply quantity no FAOSTAT")
    col_cod_elem = [col for col in elementos_df.columns if "Code" in col][0]
    element_codes = elementos_df[col_cod_elem].tolist()

    item_codes = []
    itens_encontrados = []
    for palavra in cfg["faostat"]["itens_busca"]:
        print(f"  buscando item '{palavra}' ...")
        itens_df = buscar_itens_faostat(dominio, palavra)
        if itens_df.empty:
            continue
        col_cod_item = [col for col in itens_df.columns if "Code" in col][0]
        item_codes.extend(itens_df[col_cod_item].tolist())
        itens_encontrados.append(itens_df)

    if not item_codes:
        raise RuntimeError("nenhum item de cha/cafe/mate encontrado na API FAOSTAT")

    if itens_encontrados:
        pd.concat(itens_encontrados, ignore_index=True).drop_duplicates().to_csv(
            RAW_API_DIR / "faostat_itens_encontrados.csv", index=False, encoding="utf-8"
        )

    bruto = baixar_faostat(dominio, item_codes, element_codes, ano_ini, ano_fim)
    canonico = normalizar_faostat(bruto, cfg, origem="api_faostat")
    salvar_faostat_canonico(canonico)
    return True


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


def rodar_who_gho(cfg: dict) -> bool:
    print("\n=== WHO GHO ===")
    confirmados = cfg["who_gho"].get("codigos_confirmados") or {}

    if not confirmados:
        print("  Nenhum codigo confirmado em config.yaml ainda.")
        candidatos = []
        for tema, palavra in cfg["who_gho"]["palavras_chave_busca"].items():
            print(f"  buscando candidatos para '{tema}' ({palavra}) ...")
            try:
                df = buscar_indicadores_gho(palavra)
            except Exception as erro:
                print(f"    [erro] {erro}")
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
            return True
        print("  [erro] nenhum candidato encontrado")
        return False

    print("  codigos confirmados encontrados em config.yaml, baixando dados ...")
    todos = []
    for tema, codigo in confirmados.items():
        print(f"  baixando {tema} ({codigo}) ...")
        try:
            df = baixar_indicador_gho(codigo)
        except Exception as erro:
            print(f"    [erro] {erro}")
            continue
        if not df.empty:
            df["tema"] = tema
            todos.append(df)
        time.sleep(0.3)

    if not todos:
        return False

    painel = pd.concat(todos, ignore_index=True)
    saida = RAW_API_DIR / "who_gho_indicadores.csv"
    painel.to_csv(saida, index=False, encoding="utf-8")
    print(f"  salvo em: {saida}  ({len(painel)} linhas)")
    return True


# ============================================================
# MAIN
# ============================================================
def main():
    RAW_API_DIR.mkdir(parents=True, exist_ok=True)
    cfg = carregar_config()
    fontes_com_erro = []

    try:
        if not rodar_world_bank(cfg):
            fontes_com_erro.append("World Bank")
    except Exception as erro:
        print(f"\n[erro] World Bank falhou por completo: {erro}")
        fontes_com_erro.append("World Bank")

    try:
        if not rodar_faostat(cfg):
            fontes_com_erro.append("FAOSTAT")
    except Exception as erro:
        print(f"\n[erro] FAOSTAT falhou por completo: {erro}")
        fontes_com_erro.append("FAOSTAT")

    try:
        if not rodar_who_gho(cfg):
            fontes_com_erro.append("WHO GHO")
    except Exception as erro:
        print(f"\n[erro] WHO GHO falhou por completo: {erro}")
        fontes_com_erro.append("WHO GHO")

    print("\n" + "=" * 50)
    if fontes_com_erro:
        print(f"Concluido COM AVISOS. Fontes com falha/pendencia: {', '.join(fontes_com_erro)}")
    else:
        print("Concluido com sucesso em todas as fontes.")
    print("Confira os arquivos em data/raw/api/")


if __name__ == "__main__":
    main()
