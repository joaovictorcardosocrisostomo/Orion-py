"""
services/rag.py — Motor de Busca Semântica (RAG)

Implementa o pipeline de Retrieval-Augmented Generation usando:
- Embeddings: Gemini API (gemini-embedding-2) — 768 dimensões (configurado)
- Armazenamento: pgvector no PostgreSQL
- Busca: cosine_distance (<=>) para similaridade semântica
"""
import uuid
import logging
from typing import Optional
from sqlmodel import Session, select, text as sql_text
from google import genai
from google.genai.types import EmbedContentConfig

from core.config import settings
from database.db import engine
from database.models import ProcedimentoRAG

# ── Cliente Gemini ───────────────────────────────────────────────────
_client: Optional[genai.Client] = None

def _get_client() -> genai.Client:
    """Retorna o cliente Gemini (singleton por performance)."""
    global _client
    if _client is None:
        api_key = settings.gemini_api_key_resolved
        if not api_key:
            raise ValueError(
                "GOOGLE_API_KEY ou GEMINI_API_KEY não configurada no .env. "
                "O RAG não pode gerar embeddings sem uma chave de API."
            )
        _client = genai.Client(api_key=api_key)
    return _client


# ── 1. Geração de Embeddings ─────────────────────────────────────────

def gerar_embedding(texto: str) -> list[float]:
    """
    Gera um embedding vetorial para o texto usando Gemini embedding-2.

    Args:
        texto: O conteúdo (pode ser o POP inteiro ou a consulta do usuário).

    Returns:
        Lista de 768 floats representando o vetor semântico.

    Raises:
        ValueError: Se a chave de API não estiver configurada.
        Exception: Se a API Gemini falhar.
    """
    if not texto or not texto.strip():
        raise ValueError("Texto vazio — não é possível gerar embedding.")

    # Limita tamanho para ~2K tokens
    texto_limpo = texto.strip()[:8_000]

    try:
        result = _get_client().models.embed_content(
            model="gemini-embedding-2",
            contents=texto_limpo,
            config=EmbedContentConfig(output_dimensionality=768),
        )
        embedding = result.embeddings[0].values
        logging.debug(f"Embedding gerado: {len(embedding)} dimensões")
        return embedding

    except Exception as e:
        logging.error(f"Falha ao gerar embedding no Gemini: {e}")
        raise


# ── 2. Inserção de Documentos ────────────────────────────────────────

def inserir_documento(titulo: str, conteudo: str) -> ProcedimentoRAG:
    """
    Gera o embedding e persiste um novo documento (POP) no banco vetorial.

    Args:
        titulo: Nome do procedimento (ex: "POP-042 - Análise de Ferro").
        conteudo: Texto completo do procedimento.

    Returns:
        O objeto ProcedimentoRAG salvo (com id e embedding).

    Raises:
        ValueError: Se o título já existir no banco.
    """
    if not titulo or not titulo.strip():
        raise ValueError("Título não pode ser vazio.")
    if not conteudo or not conteudo.strip():
        raise ValueError("Conteúdo não pode ser vazio.")

    # Sanitiza caracteres nulos — PostgreSQL não aceita \x00 em TEXT
    conteudo = conteudo.replace("\x00", "")

    with Session(engine) as session:
        # Verifica duplicata
        existente = session.exec(
            select(ProcedimentoRAG).where(ProcedimentoRAG.titulo_documento == titulo.strip())
        ).first()
        if existente:
            raise ValueError(f"Já existe um documento com o título '{titulo}' no banco.")

        # Gera embedding
        embedding = gerar_embedding(conteudo)

        # Persiste
        doc = ProcedimentoRAG(
            titulo_documento=titulo.strip(),
            conteudo_texto=conteudo.strip(),
            embedding=embedding,  # pgvector aceita list[float] diretamente
        )
        session.add(doc)
        session.commit()
        session.refresh(doc)

        logging.info(f"📄 Documento inserido: '{titulo}' ({len(embedding)} dims)")
        return doc


# ── 3. Busca Vetorial por Similaridade ───────────────────────────────

def busca_vetorial(consulta: str, limite: int = 5) -> list[tuple[ProcedimentoRAG, float]]:
    """
    Busca os documentos mais similares à consulta usando cosine_distance.

    Args:
        consulta: Texto livre do usuário (ex: "análise de ferro com fenantrolina").
        limite: Máximo de resultados (padrão 5).

    Returns:
        Lista de tuplas (ProcedimentoRAG, distancia_cosseno).
        Quanto menor a distância, maior a similaridade (0 = idêntico, 2 = oposto).
    """
    if not consulta or not consulta.strip():
        return []

    # Gera embedding da consulta
    emb_consulta = gerar_embedding(consulta)

    with Session(engine) as session:
        # Usa cosine_distance (<=>) do pgvector
        # A cláusula ORDER BY com <=> ordena do mais similar ao menos similar
        stmt = sql_text(
            """
            SELECT id, titulo_documento, conteudo_texto,
                   embedding <=> :emb_consulta AS distancia
            FROM procedimentorag
            ORDER BY distancia
            LIMIT :limite
            """
        )

        resultados = session.exec(
            stmt,
            params={
                "emb_consulta": str(emb_consulta),  # pgvector aceita string repr de lista
                "limite": limite,
            },
        ).fetchall()

        # Converte para tuplas (objeto, distancia)
        documentos = []
        for row in resultados:
            doc = ProcedimentoRAG(
                id=row[0],
                titulo_documento=row[1],
                conteudo_texto=row[2],
                embedding=emb_consulta,  # placeholder, não usado
            )
            documentos.append((doc, float(row[3])))

        logging.info(
            f"🔍 Busca vetorial por '{consulta[:50]}...' → "
            f"{len(documentos)} resultados"
        )
        return documentos


# ── 4. Funções para o LLM (Function Calling) ─────────────────────────

def formatar_contexto_rag(termo_busca: str, limite: int = 3) -> str:
    """
    Busca documentos similares e retorna o conteúdo em texto puro
    para ser injetado como contexto no LLM (síntese).

    Args:
        termo_busca: O que o usuário quer saber.
        limite: Máximo de documentos (padrão 3).

    Returns:
        Texto puro com título e conteúdo dos documentos encontrados,
        ou string vazia se nada encontrado.
    """
    try:
        resultados = busca_vetorial(termo_busca, limite=limite)
    except Exception as e:
        logging.error(f"Erro no formatar_contexto_rag: {e}")
        return ""

    if not resultados:
        return ""

    blocos = []
    for i, (doc, dist) in enumerate(resultados, 1):
        # Trunca o conteúdo para evitar estourar o limite de tokens do LLM (erro 413)
        conteudo_limitado = doc.conteudo_texto.strip()[:4_000]
        if len(doc.conteudo_texto) > 4_000:
            conteudo_limitado += "\n...[trecho truncado para evitar excesso de tokens]..."

        blocos.append(
            f"--- DOCUMENTO {i} ---\n"
            f"Título: {doc.titulo_documento}\n"
            f"Similaridade: {1 - dist:.1%}\n"
            f"Conteúdo:\n{conteudo_limitado}\n"
        )

    return "\n\n".join(blocos)


def consultar_rag(termo_busca: str) -> str:
    """
    Função chamada pelo LLM via function calling.
    Busca documentos similares e retorna um resumo formatado.

    Args:
        termo_busca: O que o usuário quer saber (ex: "análise de ferro").

    Returns:
        String formatada com os documentos encontrados (título + trecho).
        Se nada for encontrado, retorna mensagem informativa.
    """
    try:
        resultados = busca_vetorial(termo_busca, limite=5)
    except ValueError as e:
        return f"⚠️ Configuração de IA pendente: {e}"
    except Exception as e:
        logging.error(f"Erro no consultar_rag: {e}")
        return "❌ Ocorreu um erro ao buscar os procedimentos. Tente novamente."

    if not resultados:
        return (
            f"🔍 Não encontrei nenhum procedimento relacionado a "
            f"'{termo_busca}' no banco de conhecimento do laboratório."
        )

    linhas = [f"📚 <b>Resultados para: {termo_busca}</b>\n"]
    for i, (doc, dist) in enumerate(resultados, 1):
        # Pega os primeiros ~300 caracteres do conteúdo como preview
        preview = doc.conteudo_texto[:300].strip()
        if len(doc.conteudo_texto) > 300:
            preview += "..."

        linhas.append(
            f"{i}. <b>{doc.titulo_documento}</b> "
            f"(similaridade: {1 - dist:.1%})\n"
            f"   <i>{preview}</i>\n"
        )

    return "\n".join(linhas)
