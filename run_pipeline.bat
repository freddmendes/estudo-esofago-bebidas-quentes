@echo off
REM =====================================================
REM run_pipeline.bat
REM Roda o pipeline inteiro em sequencia, do jeito certo.
REM Rode este arquivo SOMENTE depois de:
REM   1) instalar Python, R e os pacotes (ver guia)
REM   2) ter colocado os 4 arquivos manuais nas pastas certas
REM   3) ter preenchido pelo menos parte da planilha X2/X3
REM =====================================================

setlocal

echo [1/9] Baixando dados publicos via API (World Bank, FAOSTAT, WHO GHO)...
python scripts\python\01_download_public_data.py
if errorlevel 1 goto :erro

echo [2/9] Importando arquivos manuais (GBD, GLOBOCAN, CI5, Vignat)...
python scripts\python\02_import_manual_data.py
if errorlevel 1 goto :erro

echo [3/9] Harmonizando codigos de pais (ISO3)...
python scripts\python\03_harmonize_countries.py
if errorlevel 1 goto :erro

echo [4/9] Construindo o painel pais-ano...
python scripts\python\04_build_panel.py
if errorlevel 1 goto :erro

echo [5/9] Construindo o HBFEI (PCA)...
python scripts\python\05_build_hbfei.py
if errorlevel 1 goto :erro

echo [6/9] Imputacao multipla (R / MICE)...
Rscript scripts\r\06_imputation.R
if errorlevel 1 goto :erro

echo [7/9] Modelos estatisticos primarios (R)...
Rscript scripts\r\07_primary_models.R
if errorlevel 1 goto :erro

echo [8/9] Analises de sensibilidade (R)...
Rscript scripts\r\08_sensitivity_models.R
if errorlevel 1 goto :erro

echo [9/9] Gerando tabelas e figuras finais...
python scripts\python\09_generate_outputs.py
if errorlevel 1 goto :erro

echo.
echo ==========================================
echo PIPELINE CONCLUIDO COM SUCESSO
echo Veja os resultados em outputs\tables e outputs\figures
echo ==========================================
goto :fim

:erro
echo.
echo ==========================================
echo ERRO em uma das etapas acima. Leia a mensagem
echo de erro impressa e corrija antes de rodar de novo.
echo ==========================================
exit /b 1

:fim
endlocal
