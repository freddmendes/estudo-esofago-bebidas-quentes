# GBD Results Tool — arquivo manual

1. Acesse: https://vizhub.healthdata.org/gbd-results/
2. Crie uma conta gratuita (obrigatorio) e faca login.
3. Filtros a selecionar:
   - Cause: "Esophageal cancer"
   - Measure: Incidence, Deaths, DALYs, YLLs, YLDs (marque todas)
   - Metric: Rate (para pegar o ASR)
   - Location: marque "Select all" nos paises/territorios
   - Year: do ano inicial ao ano final do seu periodo de estudo
   - Sex: Both
   - Age: Age-standardized
4. Clique em "Download" -> escolha formato CSV.
5. Salve o(s) arquivo(s) CSV baixado(s) NESTA PASTA, sem renomear.

O script 02_import_manual_data.py vai procurar automaticamente por
qualquer arquivo .csv dentro desta pasta.
