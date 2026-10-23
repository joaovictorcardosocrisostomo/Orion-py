import logging
from datetime import datetime, timedelta, time, date
import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiogram import Bot
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from sqlmodel import Session, select

from database.db import engine
from database.models import Usuario, Reserva, StatusReserva, Item, CategoriaNotificacao, NivelAcesso
from services.notificacoes import configurar_bot_notificacoes, enviar_notificacao, notificar_administradores
from services.manutencao import verificar_status_calibracoes

# Instância global do relógio para podermos importar em outros arquivos
scheduler = AsyncIOScheduler(timezone="America/Fortaleza")
bot_instance = None

# ==========================================
# 1. ALARMES DINÂMICOS (Play / Stop)
# ==========================================

async def notificar_inicio(telegram_id: int, item_nome: str, reserva_id: str):
    """Grita na hora que o agendamento está marcado para começar."""
    teclado = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ Iniciar Experimento", callback_data=f"iniciar_{reserva_id}")]
    ])
    await enviar_notificacao(
        usuario_id=telegram_id,
        categoria=CategoriaNotificacao.LEMBRETE_AGENDA,
        titulo="⏰ Hora de começar!",
        mensagem=(
            f"O seu agendamento para o <b>{item_nome}</b> começou agora.\n\n"
            "Clique no botão abaixo assim que estiver na bancada para iniciarmos a sessão e o cronômetro:"
        ),
        teclado=teclado
    )

async def notificar_fim(telegram_id: int, item_nome: str, reserva_id: str):
    """Grita na hora que o agendamento está marcado para acabar."""
    teclado = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Sim, terminei", callback_data=f"finalizar_{reserva_id}")],
        [InlineKeyboardButton(text="⏳ Preciso de +30 min", callback_data=f"estender_{reserva_id}")]
    ])
    await enviar_notificacao(
        usuario_id=telegram_id,
        categoria=CategoriaNotificacao.LEMBRETE_AGENDA,
        titulo="🔔 Fim do tempo planejado!",
        mensagem=f"Você conseguiu concluir o uso do <b>{item_nome}</b>?",
        teclado=teclado
    )

def agendar_alarme_inicio(data_inicio: datetime, telegram_id: int, item_nome: str, reserva_id: str):
    logging.info(f"⏳ Armando alarme INÍCIO para: {data_inicio}")
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

    teclado_uso = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Sim, usei algo", callback_data="uso_sim")],
        [InlineKeyboardButton(text="❌ Não usei nada", callback_data="uso_nao")]
    ])
    for user_id in usuarios_iniciaram:
        try:
            await enviar_notificacao(
                usuario_id=user_id,
                categoria=CategoriaNotificacao.AUDITORIA_17H,
                titulo="🔔 Auditoria Diária (17h00)",
                mensagem="Olá! Você utilizou algum equipamento, reagente ou material de limpeza no laboratório hoje?",
                teclado=teclado_uso
            )
        except Exception as e:
            logging.warning(f"Não foi possível enviar auditoria para {user_id}: {e}")

    teclado_experimento = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Sim, fiz", callback_data="experimento_sim")],
        [InlineKeyboardButton(text="❌ Não fiz", callback_data="experimento_nao")]
    ])
    for user_id, info in usuarios_nao_iniciaram.items():
        itens_str = ", ".join([item[0] for item in info["pendentes"]])
        try:
            await enviar_notificacao(
                usuario_id=user_id,
                categoria=CategoriaNotificacao.AUDITORIA_17H,
                titulo="🔔 Auditoria Diária (17h00)",
                mensagem=(
                    f"Olá, <b>{info['nome']}</b>! Você tinha agendado <b>{itens_str}</b> para hoje.\n\n"
                    f"Conseguiu realizar o experimento?"
                ),
                teclado=teclado_experimento
            )
        except Exception as e:
            logging.warning(f"Não foi possível enviar auditoria para {user_id}: {e}")


# =========================================================================
# 3. BRIEFING DE PLANEJAMENTO NOTURNO (17h30) — Feature 5 solicitada
# =========================================================================

async def disparar_briefing_planejamento_noturno():
    """
    Notifica ao final do expediente pesquisadores que possuem planejamento registrado
    para o próximo dia de trabalho, permitindo preparo prévio e confirmação/ajustes.
    """
    logging.info("🌙 Iniciando verificação de Planejamento Registrado para o próximo dia útil (17h30)...")
    if not bot_instance:
        return

    fuso = pytz.timezone("America/Fortaleza")
    hoje = datetime.now(fuso).date()

    # Se for sexta-feira (weekday 4), o próximo dia de operação planejado é sábado/segunda
    dia_semana = hoje.weekday()
    if dia_semana == 4:  # Sexta
        dias_a_frente = 3  # Próxima Segunda
    elif dia_semana == 5:  # Sábado
        dias_a_frente = 2
    else:
        dias_a_frente = 1

    proximo_dia = hoje + timedelta(days=dias_a_frente)
    inicio_janela = datetime.combine(proximo_dia, time.min)
    fim_janela = datetime.combine(proximo_dia, time.max)

    data_formatada = proximo_dia.strftime("%d/%m/%Y")

    with Session(engine) as session:
        statement = (
            select(Reserva, Usuario, Item)
            .join(Usuario, Reserva.usuario_id == Usuario.telegram_id)
            .join(Item, Reserva.item_id == Item.id)
            .where(
                (Reserva.data_inicio >= inicio_janela) &
                (Reserva.data_inicio <= fim_janela) &
                (Reserva.status == StatusReserva.AGENDADO)
            )
            .order_by(Reserva.data_inicio)
        )
        reservas_planejadas = session.exec(statement).all()

        # Agrupa por usuário
        planejamentos_por_usuario = {}
        for reserva, usuario, item in reservas_planejadas:
            uid = usuario.telegram_id
            if uid not in planejamentos_por_usuario:
                planejamentos_por_usuario[uid] = {
                    "nome": usuario.nome,
                    "itens": []
                }
            planejamentos_por_usuario[uid]["itens"].append({
                "reserva_id": str(reserva.id),
                "item_nome": item.nome,
                "categoria": item.categoria.value,
                "laboratorio": item.laboratorio.sigla if item.laboratorio else "Geral",
                "localizacao": item.localizacao_exata or "Bancada",
                "inicio": reserva.data_inicio.strftime("%H:%M"),
                "fim": reserva.data_fim.strftime("%H:%M"),
            })

    # Dispara mensagens personalizadas para cada usuário com agendamento
    for user_id, dados in planejamentos_por_usuario.items():
        linhas_itens = []
        for i, info in enumerate(dados["itens"], 1):
            linhas_itens.append(
                f"{i}. 🔬 <b>{info['item_nome']}</b>\n"
                f"   ⏰ {info['inicio']} às {info['fim']} | 📍 {info['laboratorio']} ({info['localizacao']})"
            )
        corpo_itens = "\n\n".join(linhas_itens)

        teclado = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Confirmado, estarei lá!", callback_data="briefing_confirmar")],
            [InlineKeyboardButton(text="🔄 Reagendar / Cancelar", callback_data="briefing_ajustar")]
        ])

        mensagem = (
            f"Olá, <b>{dados['nome']}</b>! Você possui <b>{len(dados['itens'])} atividade(s) planejada(s)</b> "
            f"para o próximo expediente (<b>{data_formatada}</b>):\n\n"
            f"{corpo_itens}\n\n"
            f"💡 <i>Dica de bancada: Deixe reagentes, padrões e vidrarias separadas com antecedência para agilizar seu ensaio!</i>"
        )

        try:
            await enviar_notificacao(
                usuario_id=user_id,
                categoria=CategoriaNotificacao.BRIEFING_NOTURNO,
                titulo="🌙 Briefing de Planejamento de Bancada",
                mensagem=mensagem,
                teclado=teclado
            )
        except Exception as e:
            logging.warning(f"Erro ao enviar briefing noturno para {user_id}: {e}")

    logging.info(f"🌙 Briefing Noturno concluído: {len(planejamentos_por_usuario)} usuário(s) notificado(s).")


# =========================================================================
# 4. MONITORAMENTO MATINAL DE CALIBRAÇÕES E MANUTENÇÕES (08h00) — Feature 3
# =========================================================================

async def verificar_alertas_manutencao_matinal():
    """Varre calibrações vencendo ou horímetro esgotado e avisa os Administradores."""
    logging.info("🔧 Verificando calibrações e preventivas de equipamentos (08h00)...")
    resumo = verificar_status_calibracoes(dias_alerta=15)

    vencidas = resumo["vencidas"]
    proximas = resumo["proximas_vencer"]
    limite = resumo["limite_horas_atingido"]

    if not vencidas and not proximas and not limite:
        logging.info("🔧 Todos os equipamentos estão com a manutenção e calibração em dia.")
        return

    linhas = ["🔧 <b>Alerta Matinal de Manutenção & Calibração</b>\n"]
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
        linhas.append("⏳ <b>Limite de Horas de Operação Atingido:</b>")
        for eq in limite:
            linhas.append(f"• <b>{eq['nome']}</b>: {eq['horas_acumuladas']}h de uso (Limite: {eq['horas_limite']}h)")

    mensagem = "\n".join(linhas)
    await notificar_administradores(
        titulo="🔧 Alerta de Manutenção e Calibração de Equipamentos",
        mensagem=mensagem,
        categoria=CategoriaNotificacao.MANUTENCAO_ALERTA
    )

    # Processa alertas preditivos de vencimento de garantia de manutenções
    try:
        from services.manutencao import processar_e_notificar_garantias_vencendo
        await processar_e_notificar_garantias_vencendo()
    except Exception as e:
        logging.warning(f"Erro ao processar notificações de garantia de manutenção: {e}")


# ==========================================
# 5. INICIALIZAÇÃO NO MAIN
# ==========================================

def iniciar_scheduler(bot: Bot):
    global bot_instance
    bot_instance = bot
    configurar_bot_notificacoes(bot)
    
    # 1. Vassoura Diária (Prestação de contas do dia): 17h00 seg-sex
    scheduler.add_job(disparar_auditoria_diaria, 'cron', day_of_week='mon-fri', hour=17, minute=0)

    # 2. Briefing Noturno (Planejamento do dia seguinte): 17h30 seg-sex
    scheduler.add_job(disparar_briefing_planejamento_noturno, 'cron', day_of_week='mon-fri', hour=17, minute=30)

    # 3. Monitoramento de Calibração/Manutenção: 08h00 seg-sex
    scheduler.add_job(verificar_alertas_manutencao_matinal, 'cron', day_of_week='mon-fri', hour=8, minute=0)
    
    scheduler.start()
    logging.info("⏰ Scheduler iniciado com Auditoria (17h), Briefing Noturno (17h30) e Manutenção (08h)!")