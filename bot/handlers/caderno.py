"""
bot/handlers/caderno.py — Handlers para o Caderno de Laboratório Eletrônico (ELN)
"""
import uuid
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlmodel import Session

from database.db import engine
from database.models import Reserva, Item, Usuario
from services.caderno import (
    criar_entrada_caderno,
    listar_entradas_caderno,
    obter_entrada_caderno,
    formatar_entrada_telegram,
)

router = Router()


class FSMCaderno(StatesGroup):
    aguardando_amostra = State()
    aguardando_objetivo = State()
    aguardando_observacoes = State()


# =========================================================================
# 1. COMANDO /caderno (Consulta e Registro Manual)
# =========================================================================

@router.message(Command("caderno"))
async def cmd_caderno(message: Message, state: FSMContext):
    """Lista os ensaios mais recentes registrados no Caderno de Laboratório."""
    if message.from_user is None:
        return

    entradas = listar_entradas_caderno(limite=5)
    if not entradas:
        teclado = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📝 Novo Registro Avulso", callback_data="caderno_novo_avulso")]
        ])
        await message.answer(
            "📖 <b>Caderno de Laboratório Eletrônico (ELN)</b>\n\n"
            "Ainda não há registros de ensaios salvos no laboratório.\n"
            "Você pode iniciar um registro avulso pelo botão abaixo ou "
            "ao finalizar um experimento agendado:",
            reply_markup=teclado,
            parse_mode="HTML"
        )
        return

    linhas = ["📖 <b>Caderno de Laboratório — Ensaios Recentes</b>\n"]
    botoes = []

    for e in entradas:
        data_str = e.data_registro.strftime("%d/%m %H:%M")
        linhas.append(f"• <b>{e.codigo_ensaio}</b>: {e.titulo} ({data_str}) — {e.tempo_bancada_minutos} min")
        botoes.append([
            InlineKeyboardButton(text=f"🔍 Ver {e.codigo_ensaio}", callback_data=f"caderno_ver_{e.id}")
        ])

    botoes.append([InlineKeyboardButton(text="📝 Novo Registro Avulso", callback_data="caderno_novo_avulso")])
    teclado = InlineKeyboardMarkup(inline_keyboard=botoes)

    await message.answer("\n".join(linhas), reply_markup=teclado, parse_mode="HTML")


# =========================================================================
# 2. FLUXO DE CRIAÇÃO DO CADERNO (Gatilhado pelo Fim do Experimento ou Avulso)
# =========================================================================

@router.callback_query(F.data.startswith("caderno_iniciar_"))
async def callback_iniciar_caderno_reserva(callback: CallbackQuery, state: FSMContext):
    """Inicia o preenchimento do caderno associado a uma reserva recém-concluída."""
    if callback.data is None or not isinstance(callback.message, Message):
        return

    reserva_id_str = callback.data.replace("caderno_iniciar_", "")
    reserva_uuid = None
    nome_padrao = "Ensaio Experimental"
    tempo_min = 0

    try:
        reserva_uuid = uuid.UUID(reserva_id_str)
        with Session(engine) as session:
            reserva = session.get(Reserva, reserva_uuid)
            if reserva:
                item = session.get(Item, reserva.item_id)
                nome_padrao = f"Uso de {item.nome if item else 'Equipamento'}"
                tempo_min = reserva.tempo_bancada_minutos or 0
    except Exception:
        pass

    await state.update_data(
        reserva_id=str(reserva_uuid) if reserva_uuid else None,
        titulo=nome_padrao,
        tempo_minutos=tempo_min,
    )

    teclado_pular = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Pular Identificação", callback_data="caderno_pular_amostra")]
    ])

    await callback.message.edit_text(
        f"📝 <b>Caderno de Laboratório — Novo Ensaio</b>\n\n"
        f"Atividade: <b>{nome_padrao}</b> ({tempo_min} min na bancada)\n\n"
        f"Qual a <b>identificação da amostra</b> testada? (Ex: <i>Efluente Tanque 2</i> ou <i>Padrão Fe 10ppm</i>):",
        reply_markup=teclado_pular,
        parse_mode="HTML"
    )
    await state.set_state(FSMCaderno.aguardando_amostra)


@router.callback_query(F.data == "caderno_novo_avulso")
async def callback_novo_avulso(callback: CallbackQuery, state: FSMContext):
    """Inicia um registro de caderno sem reserva prévia."""
    if not isinstance(callback.message, Message):
        return

    await state.update_data(
        reserva_id=None,
        titulo="Ensaio de Bancada Avulso",
        tempo_minutos=0,
    )

    teclado_pular = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Pular Identificação", callback_data="caderno_pular_amostra")]
    ])

    await callback.message.edit_text(
        "📝 <b>Caderno de Laboratório — Registro Avulso</b>\n\n"
        "Qual a <b>identificação da amostra</b>? (Ex: <i>Amostra Solo LAT-01</i>):",
        reply_markup=teclado_pular,
        parse_mode="HTML"
    )
    await state.set_state(FSMCaderno.aguardando_amostra)


@router.message(FSMCaderno.aguardando_amostra)
async def processar_amostra(message: Message, state: FSMContext):
    amostra = message.text.strip() if message.text else "Não especificada"
    await state.update_data(amostra=amostra)

    teclado_pular = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Pular Objetivo", callback_data="caderno_pular_objetivo")]
    ])

    await message.answer(
        f"Amostra gravada: <b>{amostra}</b>\n\n"
        f"Qual o <b>objetivo do ensaio</b>? (Ex: <i>Quantificação de ferro por espectrofotometria</i>):",
        reply_markup=teclado_pular,
        parse_mode="HTML"
    )
    await state.set_state(FSMCaderno.aguardando_objetivo)


@router.callback_query(FSMCaderno.aguardando_amostra, F.data == "caderno_pular_amostra")
async def pular_amostra(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    await state.update_data(amostra="Não especificada")

    teclado_pular = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭️ Pular Objetivo", callback_data="caderno_pular_objetivo")]
    ])
    await callback.message.edit_text(
        "Qual o <b>objetivo do ensaio</b>? (Ex: <i>Quantificação de ferro por espectrofotometria</i>):",
        reply_markup=teclado_pular,
        parse_mode="HTML"
    )
    await state.set_state(FSMCaderno.aguardando_objetivo)


@router.message(FSMCaderno.aguardando_objetivo)
async def processar_objetivo(message: Message, state: FSMContext):
    objetivo = message.text.strip() if message.text else "Rotina de ensaio"
    await state.update_data(objetivo=objetivo)

    await message.answer(
        "Agora digite as <b>observações de bancada</b>, leituras obtidas (ex: <i>Abs = 0.542, pH = 7.2</i>) "
        "ou ocorrências do ensaio:",
        parse_mode="HTML"
    )
    await state.set_state(FSMCaderno.aguardando_observacoes)


@router.callback_query(FSMCaderno.aguardando_objetivo, F.data == "caderno_pular_objetivo")
async def pular_objetivo(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        return
    await state.update_data(objetivo="Rotina de ensaio")

    await callback.message.edit_text(
        "Digite as <b>observações de bancada</b>, leituras obtidas (ex: <i>Abs = 0.542, pH = 7.2</i>) "
        "ou ocorrências do ensaio:",
        parse_mode="HTML"
    )
    await state.set_state(FSMCaderno.aguardando_observacoes)


@router.message(FSMCaderno.aguardando_observacoes)
async def processar_observacoes_e_salvar(message: Message, state: FSMContext):
    if message.from_user is None:
        return

    observacoes = message.text.strip() if message.text else "Sem observações adicionais."
    dados = await state.get_data()

    reserva_uuid = uuid.UUID(dados["reserva_id"]) if dados.get("reserva_id") else None
    titulo = dados.get("titulo", "Ensaio Experimental")
    amostra = dados.get("amostra", "Não especificada")
    objetivo = dados.get("objetivo", "Rotina de ensaio")
    tempo_min = dados.get("tempo_minutos", 0)

    entrada = criar_entrada_caderno(
        usuario_id=message.from_user.id,
        titulo=titulo,
        amostra_identificacao=amostra,
        objetivo=objetivo,
        reserva_id=reserva_uuid,
        dados_brutos_observacoes=observacoes,
        tempo_bancada_minutos=tempo_min,
    )

    texto_final = formatar_entrada_telegram(entrada)
    await message.answer(
        f"✅ <b>Entrada gravada com sucesso no Caderno de Laboratório!</b>\n\n{texto_final}",
        parse_mode="HTML"
    )
    await state.clear()


# =========================================================================
# 3. VISUALIZAÇÃO DE ENTRADA ESPECÍFICA
# =========================================================================

@router.callback_query(F.data.startswith("caderno_ver_"))
async def callback_ver_entrada(callback: CallbackQuery):
    if callback.data is None or not isinstance(callback.message, Message):
        return

    entrada_id_str = callback.data.replace("caderno_ver_", "")
    try:
        entrada_uuid = uuid.UUID(entrada_id_str)
        entrada = obter_entrada_caderno(entrada_uuid)
        if entrada:
            texto = formatar_entrada_telegram(entrada)
            await callback.message.answer(texto, parse_mode="HTML")
            await callback.answer()
        else:
            await callback.answer("Entrada não encontrada.", show_alert=True)
    except Exception as e:
        await callback.answer(f"Erro: {e}", show_alert=True)
