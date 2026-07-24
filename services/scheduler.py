import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlmodel import Session, select

from database.db import engine
from database.models import Usuario

# Instância global do relógio para podermos importar em outros arquivos
scheduler = AsyncIOScheduler(timezone="America/Fortaleza")
bot_instance = None

# ==========================================
# 1. ALARMES DINÂMICOS (Play / Stop)
# ==========================================

async def notificar_inicio(telegram_id: int, item_nome: str, reserva_id: str):
    """Grita na hora que o agendamento está marcado para começar."""
    if bot_instance:
        teclado = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="▶️ Iniciar Experimento", callback_data=f"iniciar_{reserva_id}")]
        ])
        await bot_instance.send_message(
            chat_id=telegram_id,
            text=f"⏰ <b>Hora de começar!</b>\nO seu agendamento para o <b>{item_nome}</b> começou agora.\n\nClique no botão abaixo assim que estiver na bancada para iniciarmos a sessão:",
            reply_markup=teclado,
            parse_mode="HTML"
        )

async def notificar_fim(telegram_id: int, item_nome: str, reserva_id: str):
    """Grita na hora que o agendamento está marcado para acabar."""
    if bot_instance:
        teclado = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Sim, terminei", callback_data=f"finalizar_{reserva_id}")],
            [InlineKeyboardButton(text="⏳ Preciso de +30 min", callback_data=f"estender_{reserva_id}")]
        ])
        await bot_instance.send_message(
            chat_id=telegram_id,
            text=f"🔔 <b>Fim do tempo planejado!</b>\nVocê conseguiu concluir o uso do <b>{item_nome}</b>?",
            reply_markup=teclado,
            parse_mode="HTML"
        )

# Funções auxiliares para armar os alarmes facilmente em outros arquivos
def agendar_alarme_inicio(data_inicio: datetime, telegram_id: int, item_nome: str, reserva_id: str):
    logging.info(f"⏳ Armando alarme INÍCIO para: {data_inicio}")
    # misfire_grace_time=None garante que o alarme toque mesmo se o processamento da IA atrasar uns segundos
    scheduler.add_job(notificar_inicio, 'date', run_date=data_inicio, args=[telegram_id, item_nome, str(reserva_id)], misfire_grace_time=None)

def agendar_alarme_fim(data_fim: datetime, telegram_id: int, item_nome: str, reserva_id: str):
    logging.info(f"⏳ Armando alarme FIM para: {data_fim}")
    scheduler.add_job(notificar_fim, 'date', run_date=data_fim, args=[telegram_id, item_nome, str(reserva_id)], misfire_grace_time=None)

# ==========================================
# 2. A VASSOURA DIÁRIA (17h00)
# ==========================================

async def disparar_auditoria_diaria():
    """Chama todos os usuários do banco de dados às 17h para o questionário de baixa."""
    logging.info("Iniciando disparo automático da Auditoria Diária (17h)...")
    if not bot_instance:
        return
        
    with Session(engine) as session:
        usuarios = session.exec(select(Usuario)).all()

    teclado = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Sim, usei algo", callback_data="uso_sim")],
        [InlineKeyboardButton(text="❌ Não usei nada", callback_data="uso_nao")]
    ])

    for usuario in usuarios:
        try:
            await bot_instance.send_message(
                chat_id=usuario.telegram_id,
                text="🔔 <b>Auditoria Diária (17h00)</b>\nOlá! Você utilizou algum equipamento, reagente ou material de limpeza no laboratório hoje?",
                reply_markup=teclado,
                parse_mode="HTML"
            )
        except Exception as e:
            logging.warning(f"Não foi possível enviar auditoria para {usuario.nome}: {e}")


# ==========================================
# 3. INICIALIZAÇÃO NO MAIN
# ==========================================

def iniciar_scheduler(bot: Bot):
    global bot_instance
    bot_instance = bot
    
    # Configura a Vassoura para rodar de segunda a sexta, às 17h00 exatas.
    scheduler.add_job(disparar_auditoria_diaria, 'cron', day_of_week='mon-fri', hour=17, minute=0)
    
    scheduler.start()
    logging.info("⏰ Scheduler iniciado! Relógio biológico online.")