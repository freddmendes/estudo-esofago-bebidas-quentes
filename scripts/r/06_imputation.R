# 06_imputation.R
# -----------------
# Trata dados faltantes por Imputacao Multipla por Equacoes Encadeadas
# (MICE, m=40), conforme Secao 19 do protocolo.
#
# Como rodar:
#   Rscript scripts\r\06_imputation.R

library(dplyr)
library(readr)
library(mice)
library(yaml)

cfg <- yaml::read_yaml("config.yaml")

caminho_painel <- file.path(cfg$caminhos$processed, "painel_pais_ano_com_hbfei.csv")
if (!file.exists(caminho_painel)) {
  stop(paste("Nao encontrei", caminho_painel, "- rode antes o script Python 05_build_hbfei.py"))
}

painel <- readr::read_csv(caminho_painel, show_col_types = FALSE)

cat("Dimensoes do painel:", nrow(painel), "linhas x", ncol(painel), "colunas\n")

# Teste de Little (MCAR) - diagnostico preliminar (Secao 19)
# obs: mcar_test do pacote naniar tambem funciona, mas mice::mice ja
# reporta padroes de missingness com md.pattern()
cat("\nPadrao de dados faltantes (resumo):\n")
print(colSums(is.na(painel)))

# variaveis auxiliares que ajudam a predizer o missingness, se existirem
vars_aux <- intersect(c("who_cobertura_saude", "expectativa_vida"), names(painel))

# seleciona variaveis numericas para o modelo de imputacao
# (ajuste esta lista conforme as colunas reais do seu painel final)
vars_modelo <- painel %>%
  select(where(is.numeric)) %>%
  names()

cat("\nVariaveis incluidas no modelo de imputacao:\n")
print(vars_modelo)

m_imputacoes <- 40  # Secao 19: m=40 por fracao de informacao faltante esperada > 20%

imputado <- mice::mice(
  painel[, vars_modelo],
  m = m_imputacoes,
  method = "pmm",
  seed = 20260710,
  printFlag = TRUE
)

saveRDS(imputado, file.path(cfg$caminhos$processed, "imputacao_mice.rds"))

# tambem salva uma versao "completa" media (so para inspecao rapida,
# os modelos finais devem usar o objeto 'imputado' inteiro + regras de Rubin,
# nao esta media simples)
completo_1 <- mice::complete(imputado, 1)
readr::write_csv(completo_1, file.path(cfg$caminhos$processed, "painel_imputado_conjunto1_preview.csv"))

cat("\nImputacao concluida. Objeto salvo em data/processed/imputacao_mice.rds\n")
cat("Use esse objeto (nao um CSV unico) nos scripts 07 e 08, combinando as\n")
cat("estimativas dos m=40 conjuntos pelas Regras de Rubin (mice cuida disso\n")
cat("automaticamente via with() e pool()).\n")
