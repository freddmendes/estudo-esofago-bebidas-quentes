# 00_install_packages.R
# -----------------------
# Roda UMA VEZ so, para instalar todos os pacotes R usados no projeto.
#
# Como rodar (dentro do RStudio): abra este arquivo e clique em "Source"
# Ou pelo cmd:
#   Rscript scripts\r\00_install_packages.R

pacotes <- c(
  "lme4", "lmerTest",       # modelos mistos (analise primaria)
  "glmmTMB",                 # GLMM binomial negativo
  "fixest",                  # efeitos fixos bidirecionais
  "geepack",                 # GEE (desfechos secundarios)
  "rms", "Hmisc",             # splines cubicos restritos (Harrell)
  "mice", "VIM",              # imputacao multipla
  "dagitty", "ggdag",         # DAG
  "FactoMineR", "psych",      # PCA / alfa de Cronbach (conferencia cruzada com Python)
  "EValue",                   # E-value (VanderWeele & Ding)
  "simr",                     # poder estatistico
  "spdep",                    # autocorrelacao espacial (I de Moran)
  "sf", "rnaturalearth",      # mapas (tmap opcional, pode falhar em alguns SOs)
  "broom", "broom.mixed",     # extracao organizada de coeficientes
  "ggplot2", "gt",            # tabelas e figuras
  "dplyr", "readr", "yaml"    # manipulacao de dados / leitura de config.yaml
)

instalados <- rownames(installed.packages())
faltando <- setdiff(pacotes, instalados)

if (length(faltando) > 0) {
  cat("Instalando pacotes faltantes:\n")
  print(faltando)
  install.packages(faltando, repos = "https://cloud.r-project.org")
} else {
  cat("Todos os pacotes ja estao instalados.\n")
}

cat("\nConcluido. Se algum pacote falhar (comum com 'sf' e 'rnaturalearth' em\n")
cat("alguns Windows por causa de dependencias do sistema — GDAL/GEOS), pule por\n")
cat("enquanto: eles so sao usados na Figura 1 (mapas), nao nos modelos estatisticos.\n")
