"""
bot/handlers/briefing.py — Handlers para o Briefing de Planejamento Noturno
"""
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

router = Router()


@router.callback_query(F.data == "briefing_confirmar")
async def callback_briefing_confirmar(callback: CallbackQuery):
    """Confirmação de presença no experimento do próximo expediente."""
    if not isinstance(callback.message, Message):
        return

    await callback.message.edit_text(
        f"{callback.message.text}\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "✅ <b>Presença Confirmada!</b>\n"
        "O laboratório estará preparado para recebê-lo. Tenha um excelente descanso!",
        parse_mode="HTML"
    )
    await callback.answer("Presença confirmada com sucesso!", show_alert=False)


@router.callback_query(F.data == "briefing_ajustar")
async def callback_briefing_ajustar(callback: CallbackQuery):
    """Auxilia o analista a ajustar ou cancelar o agendamento do dia seguinte."""
    if not isinstance(callback.message, Message):
        return

    teclado = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📋 Ver Agendamentos (/hoje)", callback_data="abrir_hoje_rapido")],
        [InlineKeyboardButton(text="🌐 Painel Web Completo", callback_data="abrir_web_briefing")]
    ])

    await callback.message.answer(
        "🔄 <b>Ajuste de Planejamento</b>\n\n"
        "Para cancelar ou reagendar seu experimento de amanhã e liberar o equipamento para outros colegas:\n"
        "• Digite <code>/hoje</code> para visualizar e gerenciar suas reservas ativas.\n"
        "• Ou acesse o <b>Painel Web</b> pelo botão abaixo:",
        reply_markup=teclado,
        parse_mode="HTML"
    )
    await callback.answer()
