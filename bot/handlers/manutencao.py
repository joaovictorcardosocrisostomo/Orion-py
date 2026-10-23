"""
bot/handlers/manutencao.py — Handlers para Controle de Manutenção e Calibração
"""
import uuid
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlmodel import Session, select

from database.db import engine
from database.models import Item, Usuario, NivelAcesso, TipoManutencao, StatusItem, CategoriaItem
from services.manutencao import verificar_status_calibracoes, registrar_manutencao, listar_historico_manutencoes

router = Router()


class FSMManutencao(StatesGroup):
    aguardando_tipo = State()
    aguardando_descricao = State()
    aguardando_tecnico = State()


@router.message(Command("manutencao"))
async def cmd_manutencao(message: Message):
    """Exibe o painel de status metrológico e manutenção dos equipamentos."""
    if message.from_user is None:
        return

    status = verificar_status_calibracoes(dias_alerta=15)
    total = status["total_equipamentos"]
    vencidas = status["vencidas"]
    proximas = status["proximas_vencer"]
    limite = status["limite_horas_atingido"]
    em_dia = status["em_dia"]

    linhas = [
        "🔧 <b>Gestão de Manutenção & Calibração Metrológica</b>",
        f"📊 Total de Equipamentos Monitorados: <b>{total}</b>\n"
    ]

    if vencidas:
        linhas.append("🚨 <b>CALIBRAÇÕES VENCIDAS:</b>")
        for eq in vencidas:
            linhas.append(f"• <b>{eq['nome']}</b> ({eq['laboratorio']}) — Venceu em: {eq['proxima_manutencao']}")
        linhas.append("")

    if proximas:
        linhas.append("⚠️ <b>Calibrações a vencer nos próximos 15 dias:</b>")
        for eq in proximas:
            linhas.append(f"• <b>{eq['nome']}</b> ({eq['laboratorio']}) — Vence em: {eq['proxima_manutencao']}")
        linhas.append("")

    if limite:
        linhas.append("⏳ <b>Horímetro no Limite Operacional:</b>")
        for eq in limite:
            linhas.append(f"• <b>{eq['nome']}</b>: {eq['horas_acumuladas']}h de uso (Limite: {eq['horas_limite']}h)")
        linhas.append("")

    linhas.append(f"✅ <b>Equipamentos Operacionais em Dia:</b> {len(em_dia)}")

    # Botões de ação rápida para admins
    botoes = []
    with Session(engine) as session:
        usuario = session.get(Usuario, message.from_user.id)
        if usuario and usuario.nivel_acesso == NivelAcesso.ADMIN:
            botoes.append([InlineKeyboardButton(text="🛠️ Registrar Nova Intervenção / Calibração", callback_data="manut_nova_intervencao")])

    botoes.append([InlineKeyboardButton(text="🔄 Atualizar Status", callback_data="manut_atualizar")])
    teclado = InlineKeyboardMarkup(inline_keyboard=botoes)

    await message.answer("\n".join(linhas), reply_markup=teclado, parse_mode="HTML")


@router.callback_query(F.data == "manut_atualizar")
async def callback_manut_atualizar(callback: CallbackQuery):
    if not isinstance(callback.message, Message):
        return

    status = verificar_status_calibracoes(dias_alerta=15)
    linhas = [
        "🔧 <b>Gestão de Manutenção & Calibração Metrológica</b>",
        f"📊 Total de Equipamentos Monitorados: <b>{status['total_equipamentos']}</b>\n",
        f"🚨 Vencidas: <b>{len(status['vencidas'])}</b>",
        f"⚠️ A vencer (15d): <b>{len(status['proximas_vencer'])}</b>",
        f"⏳ Horímetro no Limite: <b>{len(status['limite_horas_atingido'])}</b>",
        f"✅ Operacionais em dia: <b>{len(status['em_dia'])}</b>"
    ]
    teclado = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Atualizar Novamente", callback_data="manut_atualizar")]
    ])
    await callback.message.edit_text("\n".join(linhas), reply_markup=teclado, parse_mode="HTML")
    await callback.answer("Status atualizado!")
