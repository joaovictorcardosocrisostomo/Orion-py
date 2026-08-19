"""
services/parser_documento.py — Extração de texto de documentos

Suporta:
  - PDF  → pypdf
  - DOCX → python-docx
  - TXT  → decode UTF-8 direto
  - MD   → decode UTF-8 direto (Markdown é texto puro)
"""
import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Formatos suportados ───────────────────────────────────────────────
EXTENSOES_SUPORTADAS = {".pdf", ".docx", ".txt", ".md"}


def extrair_texto(conteudo_bytes: bytes, extensao: str) -> str:
    """
    Extrai texto de um documento com base na extensão do arquivo.

    Args:
        conteudo_bytes: Conteúdo do arquivo em bytes.
        extensao: Extensão do arquivo (ex: ".pdf", ".docx", ".txt", ".md").

    Returns:
        Texto extraído do documento.

    Raises:
        ValueError: Se a extensão não for suportada.
    """
    extensao = extensao.lower().strip()
    if not extensao.startswith("."):
        extensao = "." + extensao

    if extensao not in EXTENSOES_SUPORTADAS:
        raise ValueError(
            f"Formato '{extensao}' não suportado. "
            f"Use um dos: {', '.join(sorted(EXTENSOES_SUPORTADAS))}"
        )

    if extensao == ".pdf":
        texto = _extrair_texto_pdf(conteudo_bytes)
    elif extensao == ".docx":
        texto = _extrair_texto_docx(conteudo_bytes)
    else:  # .txt ou .md
        texto = _extrair_texto_txt(conteudo_bytes)

    # Sanitiza caracteres nulos — PostgreSQL não aceita \x00 em TEXT
    return texto.replace("\x00", "")


# ── Parsers específicos ───────────────────────────────────────────────

def _extrair_texto_pdf(conteudo_bytes: bytes) -> str:
    """Extrai texto de um PDF usando pypdf."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(conteudo_bytes))
    paginas = []

    for i, pagina in enumerate(reader.pages, start=1):
        texto = pagina.extract_text()
        if texto and texto.strip():
            paginas.append(texto.strip())

    if not paginas:
        logger.warning("Nenhum texto extraído do PDF — pode ser um PDF escaneado (imagem).")

    return "\n\n".join(paginas)


def _extrair_texto_docx(conteudo_bytes: bytes) -> str:
    """Extrai texto de um DOCX usando python-docx."""
    from docx import Document

    doc = Document(io.BytesIO(conteudo_bytes))
    paragrafos = []

    for paragrafo in doc.paragraphs:
        texto = paragrafo.text.strip()
        if texto:
            paragrafos.append(texto)

    if not paragrafos:
        logger.warning("Nenhum texto extraído do DOCX — documento pode estar vazio.")

    return "\n\n".join(paragrafos)


def _extrair_texto_txt(conteudo_bytes: bytes) -> str:
    """Decodifica bytes como UTF-8 (usado para .txt e .md)."""
    return conteudo_bytes.decode("utf-8")
