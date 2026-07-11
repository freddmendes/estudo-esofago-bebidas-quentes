#!/bin/bash
# =====================================================
# run_pipeline.sh - versao para Mac/Linux
# =====================================================
set -e

echo "[1/9] Baixando dados publicos via API..."
python3 scripts/python/01_download_public_data.py

echo "[2/9] Importando arquivos manuais..."
python3 scripts/python/02_import_manual_data.py

echo "[3/9] Harmonizando codigos de pais (ISO3)..."
python3 scripts/python/03_harmonize_countries.py

echo "[4/9] Construindo o painel pais-ano..."
python3 scripts/python/04_build_panel.py

echo "[5/9] Construindo o HBFEI (PCA)..."
python3 scripts/python/05_build_hbfei.py

echo "[6/9] Imputacao multipla (R)..."
Rscript scripts/r/06_imputation.R

echo "[7/9] Modelos estatisticos primarios (R)..."
Rscript scripts/r/07_primary_models.R

echo "[8/9] Analises de sensibilidade (R)..."
Rscript scripts/r/08_sensitivity_models.R

echo "[9/9] Gerando tabelas e figuras finais..."
python3 scripts/python/09_generate_outputs.py

echo ""
echo "PIPELINE CONCLUIDO COM SUCESSO"
