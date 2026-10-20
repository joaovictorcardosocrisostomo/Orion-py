"""
bot/handlers/dashboard.py — Comando /dashboard e /painel para abrir o Orion LIMS no Telegram
"""
import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.filters import Command
from sqlmodel import Session, select, func

from core.config import settings
from database.db import engine
from database.models import Item, Reserva, LogUso, StatusItem, StatusReserva
from services.usuario import buscar_usuario
from bot.apresentacao import MENSAGEM_APRESENTACAO

router = Router()


def _is_url_valida_para_botao(url: str) -> bool:
    """O Telegram rejeita botões de URL apontando para localhost ou 127.0.0.1 (BUTTON_URL_INVALID)."""
    if not url:
        return False
    url_lower = url.lower()
    if "localhost" in url_lower or "127.0.0.1" in url_lower:
        return False
    return url_lower.startswith("http://") or url_lower.startswith("https://")


def _gerar_teclado_dashboard() -> InlineKeyboardMarkup:
    """Gera teclado com suporte a Telegram MiniApp e navegador convencional, seguro contra erros da API."""
    url = settings.DASHBOARD_URL
    botoes = []

    # Telegram MiniApp exige HTTPS no cliente móvel. Se for HTTPS e válido, oferece o MiniApp nativo!
    if url.startswith("https://") and _is_url_valida_para_botao(url):
        botoes.append([
            InlineKeyboardButton(text="📱 Abrir MiniApp no Telegram", web_app=WebAppInfo(url=url))
        ])

    # Botão de acesso via navegador externo (apenas para domínios públicos válidos no Telegram)
    if _is_url_valida_para_botao(url):
        botoes.append([
            InlineKeyboardButton(text="🌐 Abrir no Navegador", url=url)
        ])

    # Botão de atualização rápida dos KPIs no chat
    botoes.append([
        InlineKeyboardButton(text="🔄 Atualizar Indicadores", callback_data="atualizar_kpis_dashboard")
    ])

    # Botão de ajuda e comandos
    botoes.append([
        InlineKeyboardButton(text="📋 Ver Comandos do Bot", callback_data="ajuda_dashboard")
    ])

    return InlineKeyboardMarkup(inline_keyboard=botoes)


def _obter_resumo_kpis() -> dict:
    """Busca métricas essenciais do banco para a mensagem do Telegram com tolerância a falhas."""
    try:
        with Session(engine) as session:
            total_itens = session.exec(select(func.count(Item.id))).one() or 0
            em_uso = session.exec(
                select(func.count(Item.id)).where(Item.estado == StatusItem.EM_USO)
            ).one() or 0
            esgotados = session.exec(
                select(func.count(Item.id)).where(
                    (Item.estado == StatusItem.ESGOTADO) | (Item.quantidade_atual <= 0)
                )
            ).one() or 0
            agendamentos_ativos = session.exec(
                select(func.count(Reserva.id)).where(
                    Reserva.status.in_([StatusReserva.AGENDADO, StatusReserva.EM_ANDAMENTO])
                )
            ).one() or 0

            # Reposições sinalizadas
            logs_repor = session.exec(
                select(func.count(LogUso.id)).where(LogUso.reposicao_necessaria == True)
            ).one() or 0

        return {
            "total_itens": total_itens,
            "em_uso": em_uso,
            "esgotados": esgotados,
            "agendamentos": agendamentos_ativos,
            "reposicoes": esgotados + logs_repor,
        }
    except Exception as e:
        logging.error(f"Erro ao obter KPIs para dashboard: {e}", exc_info=True)
        return {
            "total_itens": 0,
            "em_uso": 0,
            "esgotados": 0,
            "agendamentos": 0,
            "reposicoes": 0,
        }


def _formatar_mensagem_painel(nome_usuario: str, kpis: dict) -> str:
    url = settings.DASHBOARD_URL
    is_local = "localhost" in url.lower() or "127.0.0.1" in url.lower()

    if is_local:
        acesso_info = (
            f"🔗 <b>Link Direto:</b> <a href=\"{url}\">{url}</a>\n"
            f"💡 <i>(Servidor rodando localmente. Clique no link acima para abrir no seu navegador)</i>\n\n"
        )
    else:
        acesso_info = (
            f"🔗 <b>Link Web:</b> <a href=\"{url}\">{url}</a>\n\n"
        )

    return (
        f"🌌 <b>Orion LIMS — Painel de Gestão</b>\n\n"
        f"Olá, <b>{nome_usuario}</b>! O painel completo do laboratório está pronto para acesso.\n\n"
        f"{acesso_info}"
        f"📊 <b>Panorama Atual:</b>\n"
        f"  📦 <b>Total de itens:</b> {kpis['total_itens']}\n"
        f"  ⚡ <b>Bancada em uso:</b> {kpis['em_uso']} equipamento(s)\n"
        f"  📅 <b>Agendamentos ativos:</b> {kpis['agendamentos']}\n"
        f"  🚨 <b>Reposições / Estoque crítico:</b> {kpis['reposicoes']}\n\n"
        f"Acesse o link acima para consultar reagentes, inventário, relatórios e auditorias."
    )


@router.message(Command("dashboard", "painel"))
async def cmd_dashboard(message: Message):
    if message.from_user is None:
        return

    try:
        usuario = buscar_usuario(message.from_user.id)
        nome = usuario.nome if usuario else message.from_user.first_name

        kpis = _obter_resumo_kpis()
        texto = _formatar_mensagem_painel(nome, kpis)
        teclado = _gerar_teclado_dashboard()

        await message.answer(texto, reply_markup=teclado, parse_mode="HTML")
    except Exception as e:
        logging.error(f"Erro ao responder comando /dashboard: {e}", exc_info=True)
        # Fallback seguro caso o Telegram rejeite formatação ou teclado
        url = settings.DASHBOARD_URL
        await message.answer(
            f"🌌 <b>Orion LIMS — Dashboard</b>\n\n"
            f"Acesse o painel do laboratório no seu navegador:\n"
            f"<a href=\"{url}\">{url}</a>",
            parse_mode="HTML"
        )


@router.callback_query(F.data == "atualizar_kpis_dashboard")
async def callback_atualizar_kpis(callback: CallbackQuery):
    if not isinstance(callback.message, Message) or callback.from_user is None:
        await callback.answer("Mensagem indisponível.", show_alert=True)
        return

    try:
        usuario = buscar_usuario(callback.from_user.id)
        nome = usuario.nome if usuario else callback.from_user.first_name

        kpis = _obter_resumo_kpis()
        texto = _formatar_mensagem_painel(nome, kpis)
        teclado = _gerar_teclado_dashboard()

        await callback.message.edit_text(texto, reply_markup=teclado, parse_mode="HTML")
        await callback.answer("✅ Indicadores atualizados!")
    except Exception as e:
        logging.error(f"Erro ao atualizar KPIs: {e}")
        await callback.answer("Os dados já estão atualizados.")


@router.callback_query(F.data == "ajuda_dashboard")
async def callback_ajuda_dashboard(callback: CallbackQuery):
    if not isinstance(callback.message, Message):
        await callback.answer("Mensagem indisponível.", show_alert=True)
        return

    await callback.message.answer(MENSAGEM_APRESENTACAO, parse_mode="HTML")
    await callback.answer()
