# 08_sensitivity_models.R
# --------------------------
# Analises de sensibilidade pre-especificadas (Secao 15 do protocolo):
#   - leave-one-country-out (jackknife)
#   - estratificacao por super-regiao GBD e por nivel de renda
#   - definicoes alternativas do HBFEI (equal-weight vs PCA)
#   - autocorrelacao espacial (I de Moran)
#
# Como rodar:
#   Rscript scripts\r\08_sensitivity_models.R

library(dplyr)
library(readr)
library(lme4)
library(spdep)
library(yaml)

cfg <- yaml::read_yaml("config.yaml")

COL_DESFECHO_PRIMARIO <- "asr_incidence"
COL_EXPOSICAO <- "hbfei"
COL_PAIS <- "iso3"
COL_SUPERREGIAO <- "super_regiao_gbd"
COVARIAVEIS_NUCLEO <- c(
  "tabagismo", "alcool", "frutas", "vegetais",
  "sdi", "urbanizacao", "who_cobertura_saude", "imc_medio",
  "h_pylori", "expectativa_vida"
)

caminho_painel <- file.path(cfg$caminhos$processed, "painel_pais_ano_com_hbfei.csv")
painel <- readr::read_csv(caminho_painel, show_col_types = FALSE)

formula_covariaveis <- paste(COVARIAVEIS_NUCLEO, collapse = " + ")
formula_base <- as.formula(
  paste0("log(", COL_DESFECHO_PRIMARIO, ") ~ ", COL_EXPOSICAO, " + ", formula_covariaveis,
         " + (1 | ", COL_PAIS, ")")
)

# =========================================================
# Leave-one-country-out (jackknife)
# =========================================================
cat("=== Leave-one-country-out ===\n")
paises <- unique(painel[[COL_PAIS]])
resultados_jackknife <- list()

for (pais_excluido in paises) {
  subset_dados <- painel %>% filter(.data[[COL_PAIS]] != pais_excluido)
  modelo <- tryCatch(
    lmer(formula_base, data = subset_dados),
    error = function(e) NULL
  )
  if (!is.null(modelo)) {
    coef_exp <- fixef(modelo)[COL_EXPOSICAO]
    resultados_jackknife[[pais_excluido]] <- coef_exp
  }
}

jackknife_df <- data.frame(
  pais_excluido = names(resultados_jackknife),
  coeficiente_hbfei = unlist(resultados_jackknife)
)
write.csv(jackknife_df, file.path(cfg$caminhos$outputs, "tables", "jackknife_leave_one_out.csv"),
          row.names = FALSE)
cat("Resultado salvo. Verifique se algum pais isolado muda drasticamente o coeficiente.\n")

# =========================================================
# Estratificacao por super-regiao GBD
# =========================================================
if (COL_SUPERREGIAO %in% names(painel)) {
  cat("\n=== Estratificacao por super-regiao GBD ===\n")
  superregioes <- unique(painel[[COL_SUPERREGIAO]])
  resultados_regiao <- list()

  for (regiao in superregioes) {
    subset_dados <- painel %>% filter(.data[[COL_SUPERREGIAO]] == regiao)
    modelo <- tryCatch(
      lm(as.formula(paste0("log(", COL_DESFECHO_PRIMARIO, ") ~ ", COL_EXPOSICAO)), data = subset_dados),
      error = function(e) NULL
    )
    if (!is.null(modelo)) {
      resultados_regiao[[regiao]] <- coef(modelo)[COL_EXPOSICAO]
    }
  }
  regiao_df <- data.frame(
    superregiao = names(resultados_regiao),
    coeficiente_hbfei = unlist(resultados_regiao)
  )
  write.csv(regiao_df, file.path(cfg$caminhos$outputs, "tables", "estratificacao_superregiao.csv"),
            row.names = FALSE)
} else {
  cat("\n[aviso] coluna de super-regiao GBD nao encontrada — adicione essa",
      "informacao ao painel (voce pode derivar da classificacao GBD por pais).\n")
}

# =========================================================
# HBFEI alternativo: ponderacao igual (equal-weight) vs PCA
# =========================================================
cat("\n=== HBFEI alternativo (equal-weight) ===\n")
colunas_x <- intersect(c("x1_consumo_total", "x2_proporcao_muito_quente", "x3_classificacao_0_2"),
                        names(painel))
if (length(colunas_x) >= 2) {
  z_scores <- scale(painel[, colunas_x])
  painel$hbfei_equalweight <- rowMeans(z_scores, na.rm = TRUE)

  modelo_equalweight <- tryCatch(
    lmer(as.formula(
      paste0("log(", COL_DESFECHO_PRIMARIO, ") ~ hbfei_equalweight + ", formula_covariaveis,
             " + (1 | ", COL_PAIS, ")")
    ), data = painel),
    error = function(e) NULL
  )
  if (!is.null(modelo_equalweight)) {
    cat("Coeficiente HBFEI (equal-weight):", fixef(modelo_equalweight)["hbfei_equalweight"], "\n")
    cat("Compare com o coeficiente do HBFEI por PCA (script 07) —",
        "direcao e significancia devem se manter.\n")
  }
} else {
  cat("[aviso] componentes insuficientes para recalcular o HBFEI alternativo.\n")
}

# =========================================================
# Autocorrelacao espacial (I de Moran) sobre residuos do modelo nulo
# =========================================================
cat("\n=== Teste de autocorrelacao espacial (I de Moran) ===\n")
cat("NOTA: este teste exige um objeto de vizinhanca espacial entre paises\n")
cat("(ex: shapefile de fronteiras via rnaturalearth + poly2nb do spdep).\n")
cat("Deixe para rodar depois que os mapas (Figura 1) estiverem prontos,\n")
cat("reaproveitando o mesmo shapefile. Esqueleto:\n\n")
cat('  # paises_sf <- rnaturalearth::ne_countries(returnclass = "sf")\n')
cat('  # vizinhos <- spdep::poly2nb(paises_sf)\n')
cat('  # pesos <- spdep::nb2listw(vizinhos, zero.policy = TRUE)\n')
cat('  # spdep::moran.test(residuos_modelo_nulo, pesos, zero.policy = TRUE)\n')

cat("\nConcluido. Resultados em outputs/tables/\n")
