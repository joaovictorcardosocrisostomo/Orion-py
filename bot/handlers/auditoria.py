import uuid
import logging
import pytz
from datetime import datetime, time
from typing import Union
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlmodel import Session

from database.db import engine
from database.models import Item, StatusItem, CategoriaItem, Reserva, StatusReserva
from services.estoque import listar_itens, atualizar_quantidade
from services.log_uso import registrar_log_uso

router = Router()

# ===================================================================
# ESTADOS DA FSM
# ===================================================================
class FSMAuditoria(StatesGroup):
    aguardando_item = State()        # 1. Usuário digita o nome do item
    confirmar_item = State()         # 2. Bot mostra e aguarda confirmação
    aguardando_qtd = State()         # 3. Pergunta "quanto foi consumido?"
    aguardando_estado = State()      # 4. Pergunta "estado após o uso?"
    aguardando_obs = State()         # 5. Pergunta "alguma observação?"
    aguardando_continuar = State()   # 6. Pergunta "mais algum item?" (loop)

# ===================================================================
# HELPERS
# ===================================================================
ICONE_CATEGORIA = {
    CategoriaItem.REAGENTE: "🧪",
    CategoriaItem.EQUIPAMENTO: "⚙️",
    CategoriaItem.VIDRARIA: "⚗️",
    CategoriaItem.LIMPEZA: "🧹",
}

NOME_CATEGORIA = {
    CategoriaItem.REAGENTE: "reagente",
    CategoriaItem.EQUIPAMENTO: "equipamento",
    CategoriaItem.VIDRARIA: "vidraria",
    CategoriaItem.LIMPEZA: "material de limpeza",
}


def _icone(categoria: CategoriaItem) -> str:
    return ICONE_CATEGORIA.get(categoria, "🔹")


def _teclado_confirmar() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Confirmar", callback_data="confirmar_item_sim")],
        [InlineKeyboardButton(text="🔍 Buscar outro", callback_data="confirmar_item_nao")],
    ])


def _teclado_estado() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Bom", callback_data="estado_bom")],
        [InlineKeyboardButton(text="⚠️ Avaria / Quebrado", callback_data="estado_avaria")],
    ])


def _teclado_obs() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Digitar", callback_data="obs_digitar")],
        [InlineKeyboardButton(text="⏭️ Pular", callback_data="pular_obs")],
    ])


def _teclado_continuar() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Sim", callback_data="mais_item_sim")],
        [InlineKeyboardButton(text="❌ Não, encerrar", callback_data="mais_item_nao")],
    ])


# Palavras-chave que indicam necessidade de reposição
PALAVRAS_REPOSICAO = ["repor", "reposição", "comprar", "acabou", "último", "comprando", "reabastecer", "precisa"]


def _detecta_reposicao(texto: str) -> bool:
    texto_lower = texto.lower()
    return any(p in texto_lower for p in PALAVRAS_REPOSICAO)


async def _persistir_e_perguntar_continuar(
    target: Union[Message, CallbackQuery],
    state: FSMContext,
    usuario_id: int,
    bot: Bot,
):
    """Salva LogUso + atualiza estoque + pergunta se há mais itens."""
    dados = await state.get_data()

    # Extrai dados do state
    item_id = uuid.UUID(dados["item_id"])
    nome_item = dados["nome_item"]
    categoria = dados["categoria"]
    quantidade = dados.get("quantidade", 0.0)
    estado: StatusItem = dados.get("estado", StatusItem.BOM)
    observacao = dados.get("observacao", "")
    unidade = dados.get("unidade", "unidades")

    # Detecta se a observação menciona reposição
    precisa_repor = bool(observacao) and _detecta_reposicao(observacao)

    # 1. Persiste LogUso
    log, _ = registrar_log_uso(
        usuario_id=usuario_id,
        item_id=item_id,
        quantidade=quantidade,
        estado=estado,
        observacoes=observacao if observacao else None,
        reposicao_necessaria=precisa_repor,
    )

    # 2. Atualiza estoque se houve consumo
    if quantidade > 0:
        atualizar_quantidade(item_id, quantidade)
        qtd_str = f"{quantidade} {unidade}"
    else:
        qtd_str = "— (sem consumo)"

    # 3. Acumula no resumo
    itens_reportados: list = dados.get("itens_reportados", [])
    resumo_linha = f"{_icone(categoria)} <b>{nome_item}</b> — {qtd_str}"
    itens_reportados.append(resumo_linha)
    await state.update_data(itens_reportados=itens_reportados)

    # 4. Limpa dados do item atual (mantém apenas itens_reportados)
    await state.update_data(
        item_id=None, nome_item=None, categoria=None, unidade=None,
        lab_sigla=None, localizacao=None, quantidade=None, estado=None,
        observacao=None,
    )

    logging.info(
        f"Auditoria: LogUso criado — usuario={usuario_id}, "
        f"item={nome_item}, qtd={quantidade}, estado={estado.value}"
    )

    # 5. Descobre o chat_id
    if isinstance(target, Message):
        chat_id = target.chat.id
        await target.answer(
            f"✅ <b>Registrado!</b>\n{resumo_linha}",
            parse_mode="HTML"
        )
    else:
        chat_id = target.message.chat.id
        await target.message.edit_text(
            f"✅ <b>Registrado!</b>\n{resumo_linha}",
            parse_mode="HTML"
        )

    # 6. Pergunta se quer continuar
    await bot.send_message(
        chat_id=chat_id,
        text="Usou mais algum item hoje?",
        reply_markup=_teclado_continuar(),
        parse_mode="HTML"
    )
    await state.set_state(FSMAuditoria.aguardando_continuar)


async def _montar_resumo_e_encerrar(
    callback: CallbackQuery,
    state: FSMContext,
):
    """Exibe resumo final com todos os itens reportados e encerra a FSM."""
    dados = await state.get_data()
    itens = dados.get("itens_reportados", [])

    if itens:
        resumo = "\n".join(itens)
        texto = (
            "✅ <b>Auditoria concluída!</b>\n\n"
            "📋 <b>Itens reportados hoje:</b>\n"
            f"{resumo}\n\n"
            "🌟 Obrigado! Os registros foram salvos e o estoque atualizado.\n"
            "Tenha um bom descanso!"
        )
    else:
        texto = (
            "✅ <b>Auditoria concluída!</b>\n\n"
            "Nenhum item foi reportado hoje.\n"
            "Tenha um bom descanso! 🌙"
        )

    await callback.message.edit_text(texto, parse_mode="HTML")
    await state.clear()

# ===================================================================
# HANDLER 1 — "Sim, usei algo"
# ===================================================================
@router.callback_query(F.data == "uso_sim")
async def auditoria_inicio(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✍️ <b>Auditoria de Itens</b>\n\n"
        "Qual item (equipamento, reagente, vidraria ou material de limpeza) "
        "você utilizou hoje?\n\n"
        "Digite o nome ou parte do nome do item:",
        parse_mode="HTML"
    )
    await state.update_data(itens_reportados=[])
    await state.set_state(FSMAuditoria.aguardando_item)

# ===================================================================
# HANDLER 2 — "Não usei nada"
# ===================================================================
@router.callback_query(F.data == "uso_nao")
async def auditoria_nao_usou(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✅ <b>Auditoria concluída!</b>\n\n"
        "Nenhum item foi registrado para hoje.\n"
        "Tenha um bom descanso! 🌙",
        parse_mode="HTML"
    )
    await state.clear()

# ===================================================================
# HANDLER 3 — Usuário digitou o nome do item
# ===================================================================
@router.message(FSMAuditoria.aguardando_item)
async def auditoria_buscar_item(message: Message, state: FSMContext):
    termo = message.text.strip()
    if not termo:
        await message.answer("Por favor, digite o nome do item que você usou.")
        return

    resultados = listar_itens(termo_busca=termo)
    if not resultados:
        await message.answer(
            f"🔍 Nenhum item encontrado para '<b>{termo}</b>'.\n"
            "Tente novamente com outro nome:",
            parse_mode="HTML"
        )
        return

    item, lab = resultados[0]
    sigla_lab = lab.sigla if lab else "N/A"
    local_msg = f" — 📍 {item.localizacao_exata}" if item.localizacao_exata else ""

    await state.update_data(
        item_id=str(item.id),
        nome_item=item.nome,
        categoria=item.categoria,
        unidade=item.unidade_medida,
        lab_sigla=sigla_lab,
        localizacao=item.localizacao_exata or "",
    )

    await message.answer(
        f"{_icone(item.categoria)} <b>{item.nome}</b>\n"
        f"Lab: {sigla_lab}{local_msg}\n"
        f"<i>É este o item que você usou?</i>",
        reply_markup=_teclado_confirmar(),
        parse_mode="HTML"
    )
    await state.set_state(FSMAuditoria.confirmar_item)

# ===================================================================
# HANDLER 4 — Confirmou o item
# ===================================================================
@router.callback_query(FSMAuditoria.confirmar_item, F.data == "confirmar_item_sim")
async def auditoria_confirmar_item(callback: CallbackQuery, state: FSMContext):
    dados = await state.get_data()
    categoria = dados["categoria"]
    nome_item = dados["nome_item"]

    if categoria == CategoriaItem.EQUIPAMENTO:
        # Equipamento → sem consumo, vai direto para estado
        await state.update_data(quantidade=0.0)
        await callback.message.edit_text(
            f"⚙️ <b>{nome_item}</b>\n\n"
            "Qual o estado do equipamento após o uso?",
            reply_markup=_teclado_estado(),
            parse_mode="HTML"
        )
        await state.set_state(FSMAuditoria.aguardando_estado)
    else:
        # Reagente / Limpeza / Vidraria → pergunta quantidade
        unidade = dados.get("unidade", "unidades")
        await callback.message.edit_text(
            f"{_icone(categoria)} <b>{nome_item}</b>\n\n"
            f"Quanto foi consumido (em <b>{unidade}</b>)?\n"
            "Digite apenas o número (ex: 50, 2.5, 0):",
            parse_mode="HTML"
        )
        await state.set_state(FSMAuditoria.aguardando_qtd)

# ===================================================================
# HANDLER 5 — "Buscar outro item"
# ===================================================================
@router.callback_query(FSMAuditoria.confirmar_item, F.data == "confirmar_item_nao")
async def auditoria_buscar_outro(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✍️ Digite o nome do item novamente:",
        parse_mode="HTML"
    )
    await state.set_state(FSMAuditoria.aguardando_item)

# ===================================================================
# HANDLER 6 — Usuário digitou a quantidade consumida
# ===================================================================
@router.message(FSMAuditoria.aguardando_qtd)
async def auditoria_quantidade(message: Message, state: FSMContext):
    try:
        quantidade = float(message.text.strip().replace(",", "."))
    except ValueError:
        await message.answer("❌ Digite apenas um número (ex: 50, 2.5, 0):")
        return

    if quantidade < 0:
        await message.answer("❌ A quantidade não pode ser negativa. Digite novamente:")
        return

    await state.update_data(quantidade=quantidade)

    dados = await state.get_data()
    await message.answer(
        f"{_icone(dados['categoria'])} <b>{dados['nome_item']}</b>\n"
        f"Consumo: {quantidade} {dados.get('unidade', 'unidades')}\n\n"
        "Qual o estado do item após o uso?",
        reply_markup=_teclado_estado(),
        parse_mode="HTML"
    )
    await state.set_state(FSMAuditoria.aguardando_estado)

# ===================================================================
# HANDLER 7 — Usuário escolheu estado (Bom / Avaria)
# ===================================================================
@router.callback_query(FSMAuditoria.aguardando_estado, F.data.in_(["estado_bom", "estado_avaria"]))
async def auditoria_estado(callback: CallbackQuery, state: FSMContext):
    dados = await state.get_data()
    nome_item = dados["nome_item"]
    categoria = dados["categoria"]

    estado = StatusItem.BOM if callback.data == "estado_bom" else StatusItem.QUEBRADO
    await state.update_data(estado=estado)

    await callback.message.edit_text(
        f"{_icone(categoria)} <b>{nome_item}</b>\n"
        f"Estado: {'✅ Bom' if estado == StatusItem.BOM else '🚨 Avaria/Quebrado'}\n\n"
        "Alguma observação? (ex: precisa de reposição, vidraria quebrou, etc.)\n"
        "Clique em Digitar para escrever ou Pular para seguir:",
        reply_markup=_teclado_obs(),
        parse_mode="HTML"
    )
    await state.set_state(FSMAuditoria.aguardando_obs)

# ===================================================================
# HANDLER 8a — Observação: usuário vai digitar
# ===================================================================
@router.callback_query(FSMAuditoria.aguardando_obs, F.data == "obs_digitar")
async def auditoria_obs_digitar(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✍️ Digite sua observação abaixo:",
        parse_mode="HTML"
    )

# ===================================================================
# HANDLER 8b — Observação: pular
# ===================================================================
@router.callback_query(FSMAuditoria.aguardando_obs, F.data == "pular_obs")
async def auditoria_obs_pular(callback: CallbackQuery, state: FSMContext):
    await _persistir_e_perguntar_continuar(
        target=callback,
        state=state,
        usuario_id=callback.from_user.id,
        bot=callback.bot,
    )

# ===================================================================
# HANDLER 8c — Observação: texto digitado
# ===================================================================
@router.message(FSMAuditoria.aguardando_obs)
async def auditoria_obs_texto(message: Message, state: FSMContext):
    texto_obs = message.text.strip()
    await state.update_data(observacao=texto_obs)
    await _persistir_e_perguntar_continuar(
        target=message,
        state=state,
        usuario_id=message.from_user.id,
        bot=message.bot,
    )

# ===================================================================
# HANDLER 9 — Loop: "Sim, mais um item"
# ===================================================================
@router.callback_query(FSMAuditoria.aguardando_continuar, F.data == "mais_item_sim")
async def auditoria_mais_item(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "✍️ Digite o nome do próximo item que você usou:",
        parse_mode="HTML"
    )
    await state.set_state(FSMAuditoria.aguardando_item)

# ===================================================================
# HANDLER 10 — Loop: "Não, encerrar"
# ===================================================================
@router.callback_query(FSMAuditoria.aguardando_continuar, F.data == "mais_item_nao")
async def auditoria_encerrar(callback: CallbackQuery, state: FSMContext):
    await _montar_resumo_e_encerrar(callback, state)

# ===================================================================
# HANDLER 11 — Grupo B: "Sim, consegui fazer o experimento"
# ===================================================================
@router.callback_query(F.data == "experimento_sim")
async def experimento_sim(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text(
        "🧪 Que bom que conseguiu fazer o experimento! "
        "Vamos registrar os itens utilizados.\n\n"
        "✍️ Digite o nome do primeiro item que você usou:",
        parse_mode="HTML"
    )
    await state.set_state(FSMAuditoria.aguardando_item)


# ===================================================================
# HANDLER 12 — Grupo B: "Não consegui fazer o experimento"
# ===================================================================
@router.callback_query(F.data == "experimento_nao")
async def experimento_nao(callback: CallbackQuery, state: FSMContext):
    usuario_id = callback.from_user.id
    tz = pytz.timezone("America/Fortaleza")
    hoje_inicio = datetime.now(tz).replace(hour=0, minute=0, second=0, microsecond=0)
    hoje_fim = hoje_inicio.replace(hour=23, minute=59, second=59, microsecond=999999)

    with Session(engine) as session:
        reservas = session.query(Reserva).filter(
            Reserva.usuario_id == usuario_id,
            Reserva.data_inicio >= hoje_inicio,
            Reserva.data_fim <= hoje_fim,
            Reserva.status == StatusReserva.AGENDADO,
        ).all()

        if not reservas:
            await callback.message.edit_text(
                "📭 Nenhuma reserva pendente encontrada para hoje.",
                parse_mode="HTML"
            )
            return

        count = 0
        for r in reservas:
            r.status = StatusReserva.NAO_REALIZADO
            count += 1
        session.commit()

    await callback.message.edit_text(
        f"✅ {count} reserva(s) foi/foram marcada(s) como <b>Não Realizada(s)</b>.\n\n"
        "Se precisar de algo, estou à disposição!",
        parse_mode="HTML"
    )
    await state.clear()
