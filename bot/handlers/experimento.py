import uuid
from datetime import datetime, timedelta
import pytz
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from bot.handlers.relatorio import FSMRelatorio
from aiogram.fsm.state import State, StatesGroup
from sqlmodel import Session, select

from database.db import engine
from database.models import Reserva, StatusReserva, Item, Usuario
from services.agendamento import cancelar_reserva, criar_reserva
from services.estoque import listar_itens # Altere para service_estoque se for o seu nome de arquivo
from services.scheduler import agendar_alarme_fim

router = Router()

# --- ESTADOS DO AGENDAMENTO RELÂMPAGO ---
class FSMRelampago(StatesGroup):
    aguardando_item = State()

@router.message(Command("hoje"))
async def painel_do_dia(message: Message):
    """Mostra os agendamentos do usuário para o dia atual e permite iniciar."""
    fuso = pytz.timezone("America/Fortaleza")
    hoje = datetime.now(fuso).date()
    
    with Session(engine) as session:
        # Busca todas as reservas do usuário que cruzam com a data de hoje
        statement = select(Reserva, Item).join(Item).where(
            (Reserva.usuario_id == message.from_user.id) &
            # Compara apenas a data (ignorando a hora) para trazer tudo do dia
            (Reserva.data_inicio >= datetime.combine(hoje, datetime.min.time())) &
            (Reserva.data_fim <= datetime.combine(hoje, datetime.max.time())) &
            (Reserva.status.in_([StatusReserva.AGENDADO, StatusReserva.EM_ANDAMENTO]))
        ).order_by(Reserva.data_inicio)
        
        resultados = session.exec(statement).all()
        
    if not resultados:
        await message.answer("☕ Você não tem nenhum experimento ou uso de equipamento agendado para hoje.")
        return
    else:
        await message.answer("📋 <b>Seus agendamentos para hoje:</b>", parse_mode="HTML")

        # Cria uma mensagem com botões para cada agendamento
        for reserva, item in resultados:
            horario_str = f"{reserva.data_inicio.strftime('%H:%M')} às {reserva.data_fim.strftime('%H:%M')}"

            if reserva.status == StatusReserva.AGENDADO:
                texto_status = "⏳ <i>Aguardando início</i>"
                teclado = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="▶️ Iniciar Experimento", callback_data=f"iniciar_{reserva.id}")],
                    [InlineKeyboardButton(text="❌ Cancelar", callback_data=f"cancelar_{reserva.id}")] # NOVO BOTÃO
                ])
            else:
                texto_status = "🧪 <b>EM ANDAMENTO</b>"
                teclado = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Cancelar / Interromper", callback_data=f"cancelar_{reserva.id}")]
                ])

            msg_texto = (
                f"⚙️ <b>{item.nome}</b>\n"
                f"🕒 {horario_str}\n"
                f"Status: {texto_status}"
            )

            await message.answer(msg_texto, reply_markup=teclado, parse_mode="HTML")
            
    # BOTÃO FIXO DE AGENDAMENTO RELÂMPAGO
    teclado_relampago = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Novo Uso Relâmpago", callback_data="relampago_inicio")]
    ])
    await message.answer("Precisa de algo que não estava planejado?", reply_markup=teclado_relampago)

@router.callback_query(F.data.startswith("iniciar_"))
async def botao_iniciar(callback: CallbackQuery):
    """Captura o clique no botão de iniciar."""
    reserva_id_str = callback.data.replace("iniciar_", "")
    
    with Session(engine) as session:
        reserva = session.get(Reserva, uuid.UUID(reserva_id_str))
        
        if not reserva:
            await callback.answer("Reserva não encontrada!", show_alert=True)
            return
            
        if reserva.status != StatusReserva.AGENDADO:
            await callback.answer("Este experimento já foi iniciado ou alterado.", show_alert=True)
            return

        # MUDA O STATUS PARA EM ANDAMENTO
        reserva.status = StatusReserva.EM_ANDAMENTO
        item = session.get(Item, reserva.item_id)
        if item:
            item.estado = "Em uso" # Muda o status no banco de dados
        session.commit()
        
        # --- LIGANDO O ALARME DE FIM ---
        agendar_alarme_fim(reserva.data_fim, callback.from_user.id, item.nome, reserva.id)
        # -------------------------------
        
        # Pega o nome do item para a mensagem
        item = session.get(Item, reserva.item_id)
        
        # AQUI É ONDE O DESPERTADOR (SCHEDULER) VAI ENTRAR NO PRÓXIMO PASSO!
        
        await callback.message.edit_text(
            f"▶️ <b>Experimento Iniciado!</b>\n"
            f"Equipamento: {item.nome}\n\n"
            f"<i>Bom trabalho na bancada! O Orion irá te notificar às {reserva.data_fim.strftime('%H:%M')} para checar como foi.</i>",
            parse_mode="HTML"
        )

@router.callback_query(F.data.startswith("cancelar_"))
async def botao_cancelar(callback: CallbackQuery):
    reserva_id_str = callback.data.replace("cancelar_", "")
    
    # Chama o nosso serviço seguro
    resultado = cancelar_reserva(uuid.UUID(reserva_id_str), callback.from_user.id)
    
    if not resultado["sucesso"]:
        await callback.answer(resultado["erro"], show_alert=True)
        return

    # Apaga os botões da mensagem original para o usuário não clicar de novo
    await callback.message.edit_text(
        f"🚫 <b>Agendamento Cancelado</b>\nEquipamento: {resultado['item_nome']}",
        parse_mode="HTML"
    )
    
    # 🔔 SISTEMA DE NOTIFICAÇÃO PUSH (Obrigatório pela regra do fluxo)
    if resultado["foi_admin_terceiro"]:
        try:
            await callback.bot.send_message(
                chat_id=resultado["dono_id"],
                text=f"⚠️ <b>Aviso de Cancelamento</b>\nSeu agendamento para o <b>{resultado['item_nome']}</b> foi cancelado pelo Administrador(a) <b>{resultado['solicitante_nome']}</b>.\nPor favor, procure-o(a) para alinhar os motivos.",
                parse_mode="HTML"
            )
        except Exception as e:
            print(f"Não foi possível notificar o usuário: {e}")
            
            
# --- FLUXO DO EXPERIMENTO RELÂMPAGO ---

@router.callback_query(F.data == "relampago_inicio")
async def relampago_step1(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("⚡ <b>Agendamento Relâmpago</b>\nDigite o nome do equipamento que você vai começar a usar AGORA:", parse_mode="HTML")
    await state.set_state(FSMRelampago.aguardando_item)

@router.message(FSMRelampago.aguardando_item)
async def relampago_step2(message: Message, state: FSMContext):
    termo = message.text
    resultados = listar_itens(termo_busca=termo)
    
    if not resultados:
        await message.answer(f"Não encontrei '{termo}'. Tente digitar novamente:")
        return
        
    item = resultados[0][0] 
    
    # 🛡️ NOVA VERIFICAÇÃO: Checa se alguém já deu o "Play" nesse equipamento
    with Session(engine) as session:
        statement = select(Reserva, Usuario).join(Usuario).where(
            (Reserva.item_id == item.id) &
            (Reserva.status == StatusReserva.EM_ANDAMENTO)
        )
        uso_ativo = session.exec(statement).first()

        if uso_ativo:
            reserva_ativa, usuario_dono = uso_ativo
            await message.answer(
                f"⚠️ <b>O equipamento {item.nome} está em uso agora por {usuario_dono.nome}.</b>\n"
                f"Aguarde a liberação ou alinhe diretamente com ele(a).",
                parse_mode="HTML"
            )
            await state.clear()
            return
    
    # Se estiver livre, mostra os botões de horas
    teclado_horas = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 Hora", callback_data=f"tempo_{item.id}_1"),
         InlineKeyboardButton(text="2 Horas", callback_data=f"tempo_{item.id}_2")],
        [InlineKeyboardButton(text="3 Horas", callback_data=f"tempo_{item.id}_3"),
         InlineKeyboardButton(text="4 Horas", callback_data=f"tempo_{item.id}_4")]
    ])
    
    await message.answer(f"Você selecionou: <b>{item.nome}</b>\nPor quanto tempo vai utilizar?", reply_markup=teclado_horas, parse_mode="HTML")
    await state.clear()

@router.callback_query(F.data.startswith("tempo_"))
async def relampago_step3(callback: CallbackQuery):
    _, item_id_str, horas = callback.data.split("_")
    
    # Prepara as datas (Removendo o tzinfo para evitar conflitos com o DB)
    fuso = pytz.timezone("America/Fortaleza")
    agora = datetime.now(fuso).replace(tzinfo=None)
    fim = agora + timedelta(hours=int(horas))
    
    # Cria a reserva usando o nosso serviço padrão
    resposta = criar_reserva(
        telegram_id=callback.from_user.id,
        item_id=uuid.UUID(item_id_str),
        data_inicio=agora,
        data_fim=fim
    )
    
    if resposta["sucesso"]:
        # Pulo do Gato: Força o status para "Em Andamento" já que é um início imediato
        with Session(engine) as session:
            reserva = session.get(Reserva, resposta["reserva"].id)
            reserva.status = StatusReserva.EM_ANDAMENTO
            item = session.get(Item, reserva.item_id)
            if item:
                item.estado = "Em uso" # Muda o status no banco de dados
            session.commit()
        
        # --- LIGANDO O ALARME DE FIM (RELÂMPAGO) ---
        agendar_alarme_fim(fim, callback.from_user.id, resposta["item_nome"], resposta["reserva"].id)
        # -------------------------------------------    
            
        await callback.message.edit_text(
            f"⚡ <b>Experimento Iniciado!</b>\n"
            f"Item: {resposta['item_nome']}\n"
            f"Término previsto: {fim.strftime('%H:%M')}\n\n"
            f"<i>Bom trabalho na bancada!</i>", 
            parse_mode="HTML"
        )
    else:
        await callback.message.edit_text(f"❌ <b>Conflito detectado:</b>\n{resposta['erro']}\n<i>Alguém já reservou o equipamento para este horário.</i>", parse_mode="HTML")
        

@router.callback_query(F.data.startswith("finalizar_"))
async def botao_finalizar(callback: CallbackQuery, state: FSMContext):
    reserva_id_str = callback.data.replace("finalizar_", "")
    
    with Session(engine) as session:
        reserva = session.get(Reserva, uuid.UUID(reserva_id_str))
        reserva.status = StatusReserva.CONCLUIDO
        item = session.get(Item, reserva.item_id)
        session.commit()
        
        await state.update_data(item_id=str(item.id), nome_item=item.nome)
        
    teclado = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tudo perfeito", callback_data="estado_bom")],
        [InlineKeyboardButton(text="⚠️ Apresentou avaria/quebrou", callback_data="estado_avaria")]
    ])
    
    await callback.message.edit_text(f"✅ <b>Experimento Concluído!</b>\nComo você deixou o <b>{item.nome}</b> após o uso?", reply_markup=teclado, parse_mode="HTML")
    
    # Engatilha o usuário no relatório de avarias!
    await state.set_state(FSMRelatorio.aguardando_estado_avaria)

@router.callback_query(F.data.startswith("estender_"))
async def botao_estender(callback: CallbackQuery):
    reserva_id_str = callback.data.replace("estender_", "")
    
    try:
        with Session(engine) as session:
            reserva = session.get(Reserva, uuid.UUID(reserva_id_str))
            
            # Dá mais 30 minutos na data final da reserva
            reserva.data_fim = reserva.data_fim + timedelta(minutes=30)
            nova_data = reserva.data_fim
            
            item = session.get(Item, reserva.item_id)
            nome_do_item = item.nome
            
            session.commit()
            
        # 🛡️ CORREÇÃO DEFINITIVA: Usamos a variável de texto reserva_id_str que já tínhamos!
        agendar_alarme_fim(nova_data, callback.from_user.id, nome_do_item, reserva_id_str)
        
        await callback.message.edit_text(
            f"⏳ <b>Tempo Estendido!</b>\nO Orion retornará às {nova_data.strftime('%H:%M')} para checar novamente.", 
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"Ocorreu um erro ao estender: {e}", show_alert=True)