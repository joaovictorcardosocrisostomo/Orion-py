import logging
from datetime import datetime, timedelta, time, date
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlmodel import Session, select

from database.db import engine
from database.models import Usuario, Reserva, StatusReserva, Item

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
    """Auditoria segmentada: só contacta quem tinha agendamento no dia."""
    logging.info("Iniciando disparo automático da Auditoria Diária (17h)...")
    if not bot_instance:
        return

    fuso = pytz.timezone("America/Fortaleza")
    hoje = datetime.now(fuso).date()
    inicio_hoje = datetime.combine(hoje, time.min)
    fim_hoje = datetime.combine(hoje, time.max)

    # --- GRUPO A: usuários que INICIARAM (EM_ANDAMENTO ou CONCLUIDO) ---
    # --- GRUPO B: usuários que PLANEJARAM mas NÃO INICIARAM (AGENDADO) ---
    usuarios_iniciaram = set()
    usuarios_nao_iniciaram = {}

    with Session(engine) as session:
        reservas_statement = select(Reserva, Usuario).join(Usuario).where(
            (Reserva.data_inicio >= inicio_hoje) &
            (Reserva.data_fim <= fim_hoje)
        )
        reservas_do_dia = session.exec(reservas_statement).all()

        for reserva, usuario in reservas_do_dia:
            if reserva.status in (StatusReserva.EM_ANDAMENTO, StatusReserva.CONCLUIDO):
                usuarios_iniciaram.add(usuario.telegram_id)
            elif reserva.status == StatusReserva.AGENDADO:
                item = session.get(Item, reserva.item_id)
                nome_item = item.nome if item else "Item"
                if usuario.telegram_id not in usuarios_nao_iniciaram:
                    usuarios_nao_iniciaram[usuario.telegram_id] = {
                        "nome": usuario.nome,
                        "pendentes": [],
                    }
                usuarios_nao_iniciaram[usuario.telegram_id]["pendentes"].append(
                    (nome_item, str(reserva.id))
                )

    # --- GRUPO A: Iniciaram → questionário normal de auditoria ---
    teclado_uso = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Sim, usei algo", callback_data="uso_sim")],
        [InlineKeyboardButton(text="❌ Não usei nada", callback_data="uso_nao")]
    ])
    for user_id in usuarios_iniciaram:
        try:
            await bot_instance.send_message(
                chat_id=user_id,
                text="🔔 <b>Auditoria Diária (17h00)</b>\nOlá! Você utilizou algum equipamento, reagente ou material de limpeza no laboratório hoje?",
                reply_markup=teclado_uso,
                parse_mode="HTML"
            )
        except Exception as e:
            logging.warning(f"Não foi possível enviar auditoria para {user_id}: {e}")

    # --- GRUPO B: Planejaram mas não iniciaram → pergunta específica ---
    teclado_experimento = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Sim, fiz", callback_data="experimento_sim")],
        [InlineKeyboardButton(text="❌ Não fiz", callback_data="experimento_nao")]
    ])
    for user_id, info in usuarios_nao_iniciaram.items():
        itens_str = ", ".join([item[0] for item in info["pendentes"]])
        try:
            await bot_instance.send_message(
                chat_id=user_id,
                text=(
                    f"🔔 <b>Auditoria Diária (17h00)</b>\n"
                    f"Olá, <b>{info['nome']}</b>! Você tinha agendado <b>{itens_str}</b> para hoje.\n\n"
                    f"Conseguiu realizar o experimento?"
                ),
                reply_markup=teclado_experimento,
                parse_mode="HTML"
            )
        except Exception as e:
            logging.warning(f"Não foi possível enviar auditoria para {user_id}: {e}")

    logging.info(
        f"Auditoria: {len(usuarios_iniciaram)} usuários iniciaram experimento, "
        f"{len(usuarios_nao_iniciaram)} não iniciaram."
    )


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