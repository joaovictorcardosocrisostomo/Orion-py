"""
bot/handlers/adicionar_pop.py — Comando para adicionar POPs via Telegram.

Fluxo:
  1. Usuário envia /adicionar_pop
  2. Bot verifica se é ADMIN (se não, acesso negado)
  3. Bot pede o arquivo do procedimento
  4. Usuário envia PDF, DOCX, TXT ou MD
  5. Bot extrai título do nome do arquivo, conteúdo via parser
  6. Gera embedding, salva no banco e confirma

Restrição: apenas administradores podem adicionar POPs.
"""
import logging
from pathlib import Path
from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from services.rag import inserir_documento
from services.parser_documento import extrair_texto, EXTENSOES_SUPORTADAS
from services.usuario import buscar_usuario
from database.models import NivelAcesso

router = Router()

# ── Estados da FSM ───────────────────────────────────────────────────

class FSMAdicionarPOP(StatesGroup):
    aguardando_arquivo = State()

# ── Comando /adicionar_pop ───────────────────────────────────────────

@router.message(Command("adicionar_pop"))
async def cmd_adicionar_pop(message: Message, state: FSMContext):
    """Inicia o fluxo de cadastro — apenas para administradores."""
    if message.from_user is None:
        return

    # ── Verificação de administrador ──────────────────────────────
    usuario = buscar_usuario(message.from_user.id)
    if not usuario or usuario.nivel_acesso != NivelAcesso.ADMIN:
        await message.answer(
            "🚫 <b>Acesso negado.</b>\n\n"
            "Apenas <b>administradores</b> podem adicionar novos procedimentos "
            "ao banco de conhecimento do laboratório.\n\n"
            "Se você precisa registrar um POP, peça a um administrador do laboratório "
            "para fazê-lo.",
            parse_mode="HTML"
        )
        return

    # ── Início do fluxo ───────────────────────────────────────────
    extensoes = ", ".join(sorted(EXTENSOES_SUPORTADAS))
    await message.answer(
        f"📄 <b>Adicionar novo Procedimento</b>\n\n"
        f"Envie o <b>arquivo</b> do procedimento ({extensoes}).\n\n"
        f"📌 O <b>título</b> será extraído do nome do arquivo.\n"
        f"📌 O <b>conteúdo</b> será extraído automaticamente.\n\n"
        f"<i>Limite: 20 MB por arquivo.</i>",
        parse_mode="HTML"
    )
    await state.set_state(FSMAdicionarPOP.aguardando_arquivo)


@router.message(FSMAdicionarPOP.aguardando_arquivo, F.document)
async def processar_arquivo(message: Message, state: FSMContext):
    """Recebe o arquivo, extrai texto, gera embedding e salva."""
    if message.from_user is None:
        return
    doc = message.document
    if doc is None:
        return
    nome_arquivo = doc.file_name or "documento_sem_titulo"
    extensao = Path(nome_arquivo).suffix.lower()

    # ── 1. Valida extensão ────────────────────────────────────────
    if extensao not in EXTENSOES_SUPORTADAS:
        extensoes = ", ".join(sorted(EXTENSOES_SUPORTADAS))
        await message.answer(
            f"❌ Formato <b>'{extensao}'</b> não suportado.\n\n"
            f"Envie um arquivo nos formatos: {extensoes}",
            parse_mode="HTML"
        )
        return

    # ── 2. Valida tamanho (máx 20 MB) ─────────────────────────────
    MAX_SIZE = 20 * 1024 * 1024  # 20 MB
    if doc.file_size and doc.file_size > MAX_SIZE:
        await message.answer(
            "❌ O arquivo é muito grande (máx. 20 MB).\n"
            "Reduza o tamanho ou divida em partes.",
            parse_mode="HTML"
        )
        return

    # ── 3. Download do arquivo ────────────────────────────────────
    await message.answer(
        "📥 Baixando e processando o arquivo...",
        parse_mode="HTML"
    )

    try:
        if message.bot is None:
            return
        telegram_file = await message.bot.download(doc)
        if telegram_file is None:
            await message.answer("❌ Não consegui baixar o arquivo. Tente novamente.", parse_mode="HTML")
            return
        conteudo_bytes = telegram_file.read()

        # ── 4. Extração de texto ──────────────────────────────────
        conteudo_texto = extrair_texto(conteudo_bytes, extensao)

        if not conteudo_texto or not conteudo_texto.strip():
            await message.answer(
                "❌ Não consegui extrair texto deste arquivo. "
                "Ele pode estar vazio ou ser um PDF escaneado (imagem).",
                parse_mode="HTML"
            )
            return

    except Exception as e:
        logging.error(f"Erro ao processar arquivo: {e}")
        await message.answer(
            "❌ Ocorreu um erro ao ler o arquivo. "
            "Verifique se o formato é válido e tente novamente.",
            parse_mode="HTML"
        )
        return

    # ── 5. Define título a partir do nome do arquivo ──────────────
    titulo = Path(nome_arquivo).stem  # "POP-042 - Análise de Ferro.md" → "POP-042 - Análise de Ferro"

    # ── 6. Feedback visual de processamento ───────────────────────
    await message.answer(
        f"🧠 Gerando embedding e salvando no banco vetorial...\n"
        f"📄 <b>{titulo}</b> ({len(conteudo_texto)} caracteres extraídos)",
        parse_mode="HTML"
    )

    # ── 7. Gera embedding e persiste ──────────────────────────────
    try:
        doc_salvo = inserir_documento(titulo, conteudo_texto)

        preview = conteudo_texto[:120].strip()
        if len(conteudo_texto) > 120:
            preview += "..."

        await message.answer(
            f"✅ <b>Procedimento salvo com sucesso!</b>\n\n"
            f"📄 <b>Título:</b> {doc_salvo.titulo_documento}\n"
            f"🔢 <b>Dimensões do embedding:</b> {len(doc_salvo.embedding)}\n"
            f"📝 <b>Preview:</b> {preview}",
            parse_mode="HTML"
        )

    except ValueError as e:
        if "já existe" in str(e):
            await message.answer(
                f"⚠️ Já existe um procedimento com o título '<b>{titulo}</b>' no banco.\n"
                f"Use um arquivo com nome diferente ou edite o existente.",
                parse_mode="HTML"
            )
        else:
            await message.answer(f"❌ Erro: {e}", parse_mode="HTML")
    except Exception as e:
        logging.error(f"Erro ao adicionar POP via Telegram: {e}")
        await message.answer(
            "❌ Ocorreu um erro ao salvar o procedimento. "
            "Verifique se a chave da API Gemini está configurada.",
            parse_mode="HTML"
        )
    finally:
        await state.clear()


# ── Fallback: usuário envia texto em vez de arquivo ───────────────────

@router.message(FSMAdicionarPOP.aguardando_arquivo)
async def fallback_arquivo_nao_recebido(message: Message, state: FSMContext):
    """Avisa que o bot espera um arquivo, não texto."""
    extensoes = ", ".join(sorted(EXTENSOES_SUPORTADAS))
    await message.answer(
        f"📤 Por favor, <b>envie um arquivo</b> ({extensoes}).\n\n"
        f"Use o botão de anexo (📎) do Telegram para enviar o documento.\n"
        f"Digite /cancelar para sair.",
        parse_mode="HTML"
    )
