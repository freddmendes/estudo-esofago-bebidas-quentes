# 07_primary_models.R
# ---------------------
# Analise confirmatoria primaria, seguindo a Secao 14 do protocolo:
#   14.2 modelo misto de 3 niveis (pais dentro de super-regiao GBD)
#   14.3 efeitos fixos bidirecionais (verificacao de robustez)
#   14.4 splines cubicos restritos (forma dose-resposta)
#   14.5 GEE (desfechos secundarios)
#   + E-value (VanderWeele & Ding, 2017)
#
# Como rodar:
#   Rscript scripts\r\07_primary_models.R
#
# IMPORTANTE: os nomes de variaveis abaixo (ex: super_regiao_gbd,
# tabagismo, alcool ...) precisam bater com as colunas reais do seu
# painel final. Ajuste os nomes na secao "MAPEAMENTO DE COLUNAS" logo
# abaixo — o resto do script nao precisa mudar.

library(dplyr)
library(mice)
library(lme4)
library(lmerTest)
library(fixest)
library(rms)
library(geepack)
library(EValue)
library(broom.mixed)
library(yaml)

cfg <- yaml::read_yaml("config.yaml")
dir.create(cfg$caminhos$outputs, showWarnings = FALSE)
dir.create(file.path(cfg$caminhos$outputs, "tables"), showWarnings = FALSE)

# =========================================================
# MAPEAMENTO DE COLUNAS — ajuste aqui se os nomes do seu painel
# final forem diferentes
# =========================================================
COL_DESFECHO_PRIMARIO   <- "asr_incidence"          # ASR incidencia (esofago total)
COL_DESFECHO_CONTROLE   <- "asr_incidence_eac"      # ASR EAC (controle negativo, Nivel 2)
COL_EXPOSICAO           <- "hbfei"
COL_PAIS                <- "iso3"
COL_SUPERREGIAO         <- "super_regiao_gbd"
COL_ANO                 <- "ano"
COVARIAVEIS_NUCLEO <- c(
  "tabagismo", "alcool", "frutas", "vegetais",
  "sdi", "urbanizacao", "who_cobertura_saude", "imc_medio",
  "h_pylori", "expectativa_vida"
)

# =========================================================
# Carrega o objeto de imputacao multipla (script 06)
# =========================================================
caminho_mice <- file.path(cfg$caminhos$processed, "imputacao_mice.rds")
if (!file.exists(caminho_mice)) {
  stop("Rode antes o script 06_imputation.R")
}
imputado <- readRDS(caminho_mice)

formula_covariaveis <- paste(COVARIAVEIS_NUCLEO, collapse = " + ")

# =========================================================
# 14.2 — Modelo misto de 3 niveis (pais dentro de super-regiao)
# NOTA: lme4 nativamente faz 2 niveis de intercepto aleatorio de forma
# simples; para 3 niveis aninhados, a sintaxe e (1 | superregiao/pais)
# =========================================================
formula_misto <- as.formula(
  paste0("log(", COL_DESFECHO_PRIMARIO, ") ~ ", COL_EXPOSICAO, " + ", formula_covariaveis,
         " + (1 | ", COL_SUPERREGIAO, "/", COL_PAIS, ")")
)

cat("=== Modelo misto de 3 niveis (analise primaria, H1) ===\n")
modelos_mistos <- with(imputado, lmer(formula_misto))
resumo_misto <- summary(mice::pool(modelos_mistos))
print(resumo_misto)
write.csv(resumo_misto, file.path(cfg$caminhos$outputs, "tables", "modelo_misto_primario.csv"))

# =========================================================
# 14.3 — Efeitos fixos bidirecionais (verificacao de robustez)
# fixest trabalha melhor com dado completo; usamos o 1o conjunto
# imputado para esta verificacao (pratica aceita quando o objetivo e
# so testar robustez, nao o efeito pontual final)
# =========================================================
completo_1 <- mice::complete(imputado, 1)

cat("\n=== Efeitos fixos bidirecionais (verificacao de robustez) ===\n")
formula_fe <- as.formula(
  paste0(COL_DESFECHO_PRIMARIO, " ~ ", COL_EXPOSICAO, " + ", formula_covariaveis,
         " | ", COL_PAIS, " + ", COL_ANO)
)
modelo_fe <- fixest::feols(formula_fe, data = completo_1, cluster = COL_PAIS)
print(summary(modelo_fe))
fixest::etable(modelo_fe, file = file.path(cfg$caminhos$outputs, "tables", "modelo_efeitos_fixos.csv"))

# =========================================================
# 14.4 — Splines cubicos restritos (forma dose-resposta)
# 4 nos nos percentis 5, 35, 65, 95 (Secao 14.4 / recomendacao Harrell)
# =========================================================
cat("\n=== Splines cubicos restritos (dose-resposta) ===\n")
dd <- rms::datadist(completo_1)
options(datadist = "dd")

formula_rcs <- as.formula(
  paste0("log(", COL_DESFECHO_PRIMARIO, ") ~ rcs(", COL_EXPOSICAO, ", 4) + ", formula_covariaveis)
)
modelo_rcs <- rms::ols(formula_rcs, data = completo_1)
print(modelo_rcs)

# teste de nao-linearidade (likelihood-ratio contra o modelo linear)
formula_linear <- as.formula(
  paste0("log(", COL_DESFECHO_PRIMARIO, ") ~ ", COL_EXPOSICAO, " + ", formula_covariaveis)
)
modelo_linear <- rms::ols(formula_linear, data = completo_1)
teste_nao_linear <- anova(modelo_rcs)
print(teste_nao_linear)

# =========================================================
# Controle negativo — H2 (EAC), mesmo modelo misto
# =========================================================
if (COL_DESFECHO_CONTROLE %in% names(completo_1)) {
  cat("\n=== Controle negativo (H2) — EAC ===\n")
  formula_controle <- as.formula(
    paste0("log(", COL_DESFECHO_CONTROLE, ") ~ ", COL_EXPOSICAO, " + ", formula_covariaveis,
           " + (1 | ", COL_SUPERREGIAO, "/", COL_PAIS, ")")
  )
  modelo_controle <- lmer(formula_controle, data = completo_1)
  print(summary(modelo_controle))
  write.csv(broom.mixed::tidy(modelo_controle),
            file.path(cfg$caminhos$outputs, "tables", "modelo_controle_negativo_eac.csv"))
} else {
  cat("\n[aviso] coluna de EAC nao encontrada ainda — rode a analise Nivel 2",
      "(CI5 + Vignat et al.) antes de testar H2.\n")
}

# =========================================================
# 14.5 — GEE (desfechos secundarios: mortalidade, DALY, YLL, YLD)
# =========================================================
desfechos_secundarios <- c("asr_deaths", "asr_dalys", "asr_ylls", "asr_ylds")
desfechos_disponiveis <- intersect(desfechos_secundarios, names(completo_1))

for (desfecho in desfechos_disponiveis) {
  cat(paste0("\n=== GEE — ", desfecho, " ===\n"))
  formula_gee <- as.formula(
    paste0("log(", desfecho, ") ~ ", COL_EXPOSICAO, " + ", formula_covariaveis)
  )
  modelo_gee <- geepack::geeglm(
    formula_gee, id = as.factor(completo_1[[COL_PAIS]]),
    data = completo_1, corstr = "ar1"
  )
  print(summary(modelo_gee))
}

# =========================================================
# E-value (quantifica confundimento residual necessario para anular o achado)
# =========================================================
cat("\n=== E-value ===\n")
coef_principal <- resumo_misto[COL_EXPOSICAO, "estimate"]
erro_padrao <- resumo_misto[COL_EXPOSICAO, "std.error"]

evalue_resultado <- EValue::evalues.OLS(
  est = coef_principal, se = erro_padrao, sd = sd(completo_1[[COL_EXPOSICAO]], na.rm = TRUE)
)
print(evalue_resultado)
write.csv(as.data.frame(evalue_resultado),
          file.path(cfg$caminhos$outputs, "tables", "evalue.csv"))

cat("\nConcluido. Resultados salvos em outputs/tables/\n")
