"""
criar_estrutura.py
-------------------
Cria toda a arvore de pastas do projeto. Pode rodar quantas vezes quiser
(nao apaga nada que ja existe, so cria o que estiver faltando).

Como rodar (cmd, dentro da pasta do projeto):
    python criar_estrutura.py
"""

from pathlib import Path

PASTAS = [
    "data/raw/api",
    "data/raw/manual/gbd",
    "data/raw/manual/globocan",
    "data/raw/manual/ci5",
    "data/raw/manual/vignat2022",
    "data/raw/manual/hbfei_x2_x3",
    "data/intermediate",
    "data/processed",
    "scripts/python",
    "scripts/r",
    "outputs/figures",
    "outputs/tables",
    "outputs/logs",
]

def main():
    base = Path(__file__).resolve().parent
    for pasta in PASTAS:
        caminho = base / pasta
        caminho.mkdir(parents=True, exist_ok=True)
        # arquivo .gitkeep so para a pasta nao ficar "vazia" no explorador
        marcador = caminho / ".gitkeep"
        if not marcador.exists():
            marcador.touch()
        print(f"OK  -> {caminho}")
    print("\nEstrutura criada/confirmada com sucesso.")

if __name__ == "__main__":
    main()
