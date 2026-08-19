"""
utils/importar_pops.py — Script para importar POPs em lote para o banco vetorial.

Uso:
    python utils/importar_pops.py                                   # Importa todos
    python utils/importar_pops.py --pasta pops                      # Pasta customizada
    python utils/importar_pops.py --arquivo "pops/meu_pop.md"       # Apenas um arquivo

Comportamento:
    - Lê arquivos .txt e .md da pasta especificada.
    - Cada arquivo = um documento: título = nome do arquivo, conteúdo = texto do arquivo.
    - Pula arquivos cujo título já exista no banco (evita duplicatas).
    - Se o embedding falhar, pula o arquivo e continua com os próximos.
"""
import os
import sys
import argparse
import logging
from pathlib import Path

# Garante que o projeto está no path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.rag import inserir_documento
from database.db import init_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

EXTENSOES_VALIDAS = {".txt", ".md", ".rst"}


def importar_arquivo(caminho: Path) -> bool:
    """Importa um único arquivo. Retorna True se sucesso, False se falhou."""
    titulo = caminho.stem  # nome do arquivo sem extensão
    try:
        conteudo = caminho.read_text(encoding="utf-8")
        doc = inserir_documento(titulo, conteudo)
        print(f"  ✅ {titulo} ({len(doc.embedding)} dims)")
        return True
    except ValueError as e:
        if "já existe" in str(e).lower():
            print(f"  ⏭️  {titulo} — já existe no banco (pulando)")
        else:
            print(f"  ⚠️  {titulo} — erro: {e}")
        return False
    except Exception as e:
        print(f"  ❌ {titulo} — falha: {e}")
        return False


def importar_pasta(pasta: str = "pops"):
    """Importa todos os arquivos .txt/.md de uma pasta."""
    caminho_pasta = Path(pasta)

    if not caminho_pasta.exists():
        print(f"❌ Pasta '{pasta}' não encontrada.")
        return

    arquivos = sorted(
        [f for f in caminho_pasta.iterdir() if f.suffix.lower() in EXTENSOES_VALIDAS]
    )

    if not arquivos:
        print(f"📂 Nenhum arquivo .txt/.md encontrado em '{pasta}'.")
        return

    print(f"📂 Importando {len(arquivos)} documento(s) de '{pasta}':\n")

    sucessos = 0
    falhas = 0
    for arquivo in arquivos:
        if importar_arquivo(arquivo):
            sucessos += 1
        else:
            falhas += 1

    print(
        f"\n🎯 Resultado: {sucessos} importado(s), {falhas} falha(s), "
        f"{len(arquivos) - sucessos - falhas} pulado(s)."
    )


def main():
    parser = argparse.ArgumentParser(
        description="Importa POPs para o banco vetorial do Orion."
    )
    parser.add_argument(
        "--pasta",
        default="pops",
        help="Pasta com os arquivos .txt/.md (default: pops)",
    )
    parser.add_argument(
        "--arquivo",
        help="Importa apenas um arquivo específico (caminho completo)",
    )

    args = parser.parse_args()

    # Garante que as tabelas existem
    init_db()

    if args.arquivo:
        caminho = Path(args.arquivo)
        if not caminho.exists():
            print(f"❌ Arquivo '{args.arquivo}' não encontrado.")
            sys.exit(1)
        print("📄 Importando arquivo único:\n")
        importar_arquivo(caminho)
    else:
        importar_pasta(args.pasta)


if __name__ == "__main__":
    main()
