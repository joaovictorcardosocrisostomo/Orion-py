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
from database.models import Reserva, StatusReserva, StatusItem, Item, Usuario
from services.agendamento import cancelar_reserva, criar_reserva, criar_reservas_em_grupo
from services.estoque import listar_itens # Altere para service_estoque se for o seu nome de arquivo
from services.rag import formatar_contexto_rag
from services.llm import sintetizar_com_rag
from services.scheduler import agendar_alarme_fim, agendar_alarme_inicio

router = Router()

# --- ESTADOS DO AGENDAMENTO RELÂMPAGO ---
class FSMRelampago(StatesGroup):
    aguardando_item = State()

# --- ESTADOS DO EXPERIMENTO PLANEJADO (/experimento) ---
class FSMExperimento(StatesGroup):
    aguardando_descricao = State()     # 0. O que quer fazer (modo inteligente)
    aguardando_equipamento = State()   # 1. Nome do equipamento/recurso
    aguardando_duracao = State()       # 2. Duração em horas
    aguardando_inicio = State()        # 3. Quando começa ("agora" ou data/hora)
    aguardando_mais_recurso = State()  # 4. Loop: adicionar outro recurso?

def _alvos_do_callback(reserva_id_str: str) -> list[dict]:
    """Resolve um id de callback (avulso OU grupo de experimento) para a lista de reservas alvo.

    Retorna dicts com: reserva_id, item_id, nome_item, data_fim.
    """
    resultado: list[dict] = []
    try:
        alvo_id = uuid.UUID(reserva_id_str)
    except ValueError:
        return resultado

    with Session(engine) as session:
        reserva = session.get(Reserva, alvo_id)
        if reserva:
            # É o id de UMA reserva: se ela pertence a um grupo, pega o grupo inteiro
            if reserva.grupo_id is not None:
                alvos = session.exec(select(Reserva).where(Reserva.grupo_id == reserva.grupo_id)).all()
            else:
                alvos = [reserva]
        else:
            # Não é id de reserva: tenta interpretar como grupo_id de experimento
            alvos = session.exec(select(Reserva).where(Reserva.grupo_id == alvo_id)).all()

        for r in alvos:
            item = session.get(Item, r.item_id)
            resultado.append({
                "reserva_id": r.id,
                "item_id": r.item_id,
                "nome_item": item.nome if item else "Equipamento",
                "data_fim": r.data_fim,
            })
    return resultado


def _resolver_uma_reserva_do_alvo(reserva_id_str: str):
    """Dado um id (avulso) ou grupo_id, devolve o id de UMA reserva do alvo.

    Usado pelo botão cancelar, que delega o cancelamento do grupo inteiro ao service.
    """
    try:
        alvo_id = uuid.UUID(reserva_id_str)
    except ValueError:
        return None

    with Session(engine) as session:
        reserva = session.get(Reserva, alvo_id)
        if reserva:
            return reserva.id
        grupo = session.exec(select(Reserva).where(Reserva.grupo_id == alvo_id)).first()
        return grupo.id if grupo else None


@router.message(Command("hoje"))
async def painel_do_dia(message: Message):
    """Mostra os agendamentos do usuário para o dia atual e permite iniciar."""
    if message.from_user is None:
        return

    fuso = pytz.timezone("America/Fortaleza")
    hoje = datetime.now(fuso).date()
    
    with Session(engine) as session:
        # Busca todas as reservas que cruzam com a data de hoje
        # (filtros de data no SQL; usuário/status filtrados em Python, como no scheduler.py,
        # pois colunas com sa_column=Column(BigInteger) quebram a inferência do Pylance)
        statement = select(Reserva, Item).join(Item).where(
            (Reserva.data_inicio >= datetime.combine(hoje, datetime.min.time())) &
            (Reserva.data_fim <= datetime.combine(hoje, datetime.max.time()))
        )
        resultados = session.exec(statement).all()
        resultados = [
            r for r in resultados
            if r[0].usuario_id == message.from_user.id
            and r[0].status in (StatusReserva.AGENDADO, StatusReserva.EM_ANDAMENTO)
        ]
        resultados.sort(key=lambda r: r[0].data_inicio)
        
    if not resultados:
        await message.answer("☕ Você não tem nenhum experimento ou uso de equipamento agendado para hoje.")
        return
    else:
        await message.answer("📋 <b>Seus agendamentos para hoje:</b>", parse_mode="HTML")

        # Agrupa as reservas do MESMO experimento (mesmo grupo_id) em um ÚNICO card
        grupos: dict[str, list] = {}
        avulsas: list = []
        for reserva, item in resultados:
            if reserva.grupo_id is not None:
                grupos.setdefault(str(reserva.grupo_id), []).append((reserva, item))
            else:
                avulsas.append((reserva, item))

        # 1. Cards dos experimentos agrupados (1 card por experimento)
        for gid, membros in grupos.items():
            reserva_ref, _ = membros[0]
            nomes_itens = ", ".join(it.nome for _, it in membros)
            horario_str = f"{reserva_ref.data_inicio.strftime('%H:%M')} às {reserva_ref.data_fim.strftime('%H:%M')}"

            if reserva_ref.status == StatusReserva.AGENDADO:
                texto_status = "⏳ <i>Aguardando início</i>"
                teclado = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="▶️ Iniciar Experimento", callback_data=f"iniciar_{gid}")],
                    [InlineKeyboardButton(text="❌ Cancelar", callback_data=f"cancelar_{gid}")]
                ])
            else:
                texto_status = "🧪 <b>EM ANDAMENTO</b>"
                teclado = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Cancelar / Interromper", callback_data=f"cancelar_{gid}")]
                ])

            await message.answer(
                f"🧪 <b>Experimento</b>\n"
                f"📦 Recursos: {nomes_itens}\n"
                f"🕒 {horario_str}\n"
                f"Status: {texto_status}",
                reply_markup=teclado,
                parse_mode="HTML"
            )

        # 2. Reservas avulsas (uso relâmpago / NLP)
        for reserva, item in avulsas:
            horario_str = f"{reserva.data_inicio.strftime('%H:%M')} às {reserva.data_fim.strftime('%H:%M')}"

            if reserva.status == StatusReserva.AGENDADO:
                texto_status = "⏳ <i>Aguardando início</i>"
                teclado = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="▶️ Iniciar Experimento", callback_data=f"iniciar_{reserva.id}")],
                    [InlineKeyboardButton(text="❌ Cancelar", callback_data=f"cancelar_{reserva.id}")]
                ])
            else:
                texto_status = "🧪 <b>EM ANDAMENTO</b>"
                teclado = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="❌ Cancelar / Interromper", callback_data=f"cancelar_{reserva.id}")]
                ])

            await message.answer(
                f"⚙️ <b>{item.nome}</b>\n"
                f"🕒 {horario_str}\n"
                f"Status: {texto_status}",
                reply_markup=teclado,
                parse_mode="HTML"
            )
            
    # BOTÃO FIXO DE AGENDAMENTO RELÂMPAGO
    teclado_relampago = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Novo Uso Relâmpago", callback_data="relampago_inicio")]
    ])
    await message.answer("Precisa de algo que não estava planejado?", reply_markup=teclado_relampago)

@router.callback_query(F.data.startswith("iniciar_"))
async def botao_iniciar(callback: CallbackQuery):
    """Captura o clique no botão de iniciar."""
    if callback.data is None:
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Erro: mensagem indisponível.", show_alert=True)
        return

    reserva_id_str = callback.data.replace("iniciar_", "")

    alvos = _alvos_do_callback(reserva_id_str)
    if not alvos:
        await callback.answer("Reserva não encontrada!", show_alert=True)
        return

    with Session(engine) as session:
        # Barreira: todas as reservas do alvo precisam estar AGENDADO
        for alvo in alvos:
            reserva = session.get(Reserva, alvo["reserva_id"])
            if reserva is None or reserva.status != StatusReserva.AGENDADO:
                await callback.answer("Este experimento já foi iniciado ou alterado.", show_alert=True)
                return

        # MUDA O STATUS PARA EM ANDAMENTO (todas as reservas do experimento juntas)
        nomes: list[str] = []
        data_fim_referencia: datetime | None = None
        for alvo in alvos:
            reserva = session.get(Reserva, alvo["reserva_id"])
            if reserva is None:
                continue
            reserva.status = StatusReserva.EM_ANDAMENTO
            item = session.get(Item, reserva.item_id)
            if item:
                item.estado = StatusItem.EM_USO  # Muda o status no banco de dados
                nomes.append(item.nome)
            data_fim_referencia = reserva.data_fim
        session.commit()

    if not nomes or data_fim_referencia is None:
        await callback.answer("Não foi possível iniciar o experimento.", show_alert=True)
        return

    # --- LIGANDO O ALARME DE FIM (um único para o experimento inteiro) ---
    agendar_alarme_fim(
        data_fim_referencia,
        callback.from_user.id,
        ", ".join(nomes),
        reserva_id_str,  # pode ser grupo_id: o alarme cobre o grupo todo
    )

    await callback.message.edit_text(
        f"▶️ <b>Experimento Iniciado!</b>\n"
        f"Recursos: {', '.join(nomes)}\n\n"
        f"<i>Bom trabalho na bancada! O Orion irá te notificar às {data_fim_referencia.strftime('%H:%M')} para checar como foi.</i>",
        parse_mode="HTML"
    )

@router.callback_query(F.data.startswith("cancelar_"))
async def botao_cancelar(callback: CallbackQuery):
    if callback.data is None:
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Erro: mensagem indisponível.", show_alert=True)
        return

    reserva_id_str = callback.data.replace("cancelar_", "")

    # Se vier um grupo_id (experimento), resolve para uma reserva REAL do grupo:
    # o service cancelar_reserva cuida de cancelar o grupo inteiro via grupo_id
    reserva_alvo = _resolver_uma_reserva_do_alvo(reserva_id_str)
    if reserva_alvo is None:
        await callback.answer("Reserva não encontrada!", show_alert=True)
        return

    # Chama o nosso serviço seguro
    resultado = cancelar_reserva(reserva_alvo, callback.from_user.id)
    
    if not resultado["sucesso"]:
        await callback.answer(resultado["erro"], show_alert=True)
        return

    # Apaga os botões da mensagem original para o usuário não clicar de novo
    await callback.message.edit_text(
        f"🚫 <b>Agendamento Cancelado</b>\nEquipamento: {resultado['item_nome']}",
        parse_mode="HTML"
    )
    
    # 🔔 SISTEMA DE NOTIFICAÇÃO PUSH (Obrigatório pela regra do fluxo)
    if resultado["foi_admin_terceiro"] and callback.bot is not None:
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
    if not isinstance(callback.message, Message):
        await callback.answer("Erro: mensagem indisponível.", show_alert=True)
        return
    await callback.message.edit_text("⚡ <b>Agendamento Relâmpago</b>\nDigite o nome do equipamento que você vai começar a usar AGORA:", parse_mode="HTML")
    await state.set_state(FSMRelampago.aguardando_item)

@router.message(FSMRelampago.aguardando_item)
async def relampago_step2(message: Message, state: FSMContext):
    if message.text is None:
        return
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
    if callback.data is None:
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Erro: mensagem indisponível.", show_alert=True)
        return

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
            if reserva is None:
                await callback.answer("Erro ao localizar a reserva.", show_alert=True)
                return
            reserva.status = StatusReserva.EM_ANDAMENTO
            item = session.get(Item, reserva.item_id)
            if item:
                item.estado = StatusItem.EM_USO # Muda o status no banco de dados
            session.commit()
        
        # --- LIGANDO O ALARME DE FIM (RELÂMPAGO) ---
        agendar_alarme_fim(fim, callback.from_user.id, resposta["item_nome"], str(resposta["reserva"].id))
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
    if callback.data is None:
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Erro: mensagem indisponível.", show_alert=True)
        return

    reserva_id_str = callback.data.replace("finalizar_", "")

    alvos = _alvos_do_callback(reserva_id_str)
    if not alvos:
        await callback.answer("Reserva não encontrada!", show_alert=True)
        return

    with Session(engine) as session:
        for alvo in alvos:
            reserva = session.get(Reserva, alvo["reserva_id"])
            if reserva is None:
                continue
            reserva.status = StatusReserva.CONCLUIDO
        session.commit()

    # Fluxo de relatório: começa pelo primeiro recurso e mantém os demais na fila
    primeiro = alvos[0]
    await state.update_data(
        item_id=str(primeiro["item_id"]),
        nome_item=primeiro["nome_item"],
        grupo_itens_pendentes=[
            {"item_id": str(a["item_id"]), "nome_item": a["nome_item"]} for a in alvos[1:]
        ],
    )

    teclado = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tudo perfeito", callback_data="estado_bom")],
        [InlineKeyboardButton(text="⚠️ Apresentou avaria/quebrou", callback_data="estado_avaria")]
    ])

    texto_final = f"✅ <b>Experimento Concluído!</b>\nComo você deixou o <b>{primeiro['nome_item']}</b> após o uso?"
    if len(alvos) > 1:
        texto_final += f"\n<i>({len(alvos) - 1} outro(s) recurso(s) aguardando confirmação)</i>"

    await callback.message.edit_text(texto_final, reply_markup=teclado, parse_mode="HTML")

    # Engatilha o usuário no relatório de avarias!
    await state.set_state(FSMRelatorio.aguardando_estado_avaria)

@router.callback_query(F.data.startswith("estender_"))
async def botao_estender(callback: CallbackQuery):
    if callback.data is None:
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Erro: mensagem indisponível.", show_alert=True)
        return

    reserva_id_str = callback.data.replace("estender_", "")

    alvos = _alvos_do_callback(reserva_id_str)
    if not alvos:
        await callback.answer("Reserva não encontrada!", show_alert=True)
        return

    try:
        nomes: list[str] = []
        nova_data: datetime | None = None
        with Session(engine) as session:
            for alvo in alvos:
                reserva = session.get(Reserva, alvo["reserva_id"])
                if reserva is None:
                    continue
                # Dá mais 30 minutos na data final de TODOS os recursos do experimento
                reserva.data_fim = reserva.data_fim + timedelta(minutes=30)
                nova_data = reserva.data_fim
                item = session.get(Item, reserva.item_id)
                if item:
                    nomes.append(item.nome)
            session.commit()

        if nova_data is None:
            await callback.answer("Nenhuma reserva encontrada para estender.", show_alert=True)
            return

        # 🛡️ CORREÇÃO DEFINITIVA: Usamos a variável de texto reserva_id_str que já tínhamos!
        agendar_alarme_fim(nova_data, callback.from_user.id, ", ".join(nomes), reserva_id_str)

        await callback.message.edit_text(
            f"⏳ <b>Tempo Estendido!</b>\nO Orion retornará às {nova_data.strftime('%H:%M')} para checar novamente.",
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.answer(f"Ocorreu um erro ao estender: {e}", show_alert=True)


# ════════════════════════════════════════════════════════════════════
# /experimento — PLANEJAMENTO EXPERIMENTAL (Modo Inteligente + Manual)
# ════════════════════════════════════════════════════════════════════

@router.message(Command("experimento"))
async def experimento_inicio(message: Message, state: FSMContext):
    """Modo inteligente: se o RAG tiver documento relevante, sugere o protocolo."""
    if message.text is None or message.from_user is None:
        return
    descricao = message.text.replace("/experimento", "", 1).strip()

    if message.bot is not None:
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # ── Modo inteligente: sem descrição, pergunta o que o usuário quer fazer ──
    if not descricao:
        await message.answer(
            "🧪 <b>Planejamento Experimental</b>\n\n"
            "Me diga <b>o que você quer fazer</b> — ex: "
            "<i>'análise de ferro'</i>, <i>'titulação'</i>, <i>'preparo de solução'</i>.\n\n"
            "Se eu tiver um procedimento no banco de conhecimento, eu sugiro o protocolo! "
            "Ou planejamos manualmente: equipamento → duração → horário.",
            parse_mode="HTML"
        )
        await state.set_state(FSMExperimento.aguardando_descricao)
        return

    # ── Tentativa de recuperar o procedimento no RAG ──
    contexto = formatar_contexto_rag(descricao, limite=3)

    if contexto:
        # RAG encontrou → LLM sintetiza o procedimento completo
        resposta = await sintetizar_com_rag(
            pergunta_usuario=f"O usuário quer fazer: {descricao}. Explique o procedimento e liste os recursos.",
            contexto_rag=contexto,
            telegram_id=message.from_user.id,
        )

        teclado = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Planejar com esse protocolo", callback_data="exp_plano_rag")],
            [InlineKeyboardButton(text="✏️ Planejar manualmente", callback_data="exp_manual")],
        ])

        await message.answer(
            f"📚 <b>Encontrei um procedimento no banco de conhecimento!</b>\n\n{resposta}",
            reply_markup=teclado,
            parse_mode="HTML"
        )
        await state.update_data(descricao_experimento=descricao)
        await state.set_state(FSMExperimento.aguardando_equipamento)
    else:
        # RAG não encontrou → fluxo manual
        await message.answer(
            f"🔍 Não encontrei um procedimento pronto para '<b>{descricao}</b>'.\n"
            "Vamos planejar manualmente. Qual o <b>primeiro equipamento</b> que você vai usar?\n\n"
            "<i>(Digite o nome, ex: espectrofotômetro)</i>",
            parse_mode="HTML"
        )
        await state.update_data(descricao_experimento=descricao)
        await state.set_state(FSMExperimento.aguardando_equipamento)


@router.message(FSMExperimento.aguardando_descricao)
async def experimento_descricao(message: Message, state: FSMContext):
    """Recebe a descrição digitada e tenta o RAG (mesma lógica do comando direto)."""
    if message.text is None or message.from_user is None:
        return
    descricao = message.text.strip()
    if not descricao:
        await message.answer("Me diga o que você quer fazer:")
        return

    if message.bot is not None:
        await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    contexto = formatar_contexto_rag(descricao, limite=3)

    if contexto:
        resposta = await sintetizar_com_rag(
            pergunta_usuario=f"O usuário quer fazer: {descricao}. Explique o procedimento e liste os recursos.",
            contexto_rag=contexto,
            telegram_id=message.from_user.id,
        )

        teclado = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Planejar com esse protocolo", callback_data="exp_plano_rag")],
            [InlineKeyboardButton(text="✏️ Planejar manualmente", callback_data="exp_manual")],
        ])

        await message.answer(
            f"📚 <b>Encontrei um procedimento no banco de conhecimento!</b>\n\n{resposta}",
            reply_markup=teclado,
            parse_mode="HTML"
        )
        await state.update_data(descricao_experimento=descricao)
        await state.set_state(FSMExperimento.aguardando_equipamento)
    else:
        await message.answer(
            f"🔍 Não encontrei um procedimento pronto para '<b>{descricao}</b>'.\n"
            "Vamos planejar manualmente. Qual o <b>primeiro equipamento</b> que você vai usar?\n\n"
            "<i>(Digite o nome, ex: espectrofotômetro)</i>",
            parse_mode="HTML"
        )
        await state.update_data(descricao_experimento=descricao)
        await state.set_state(FSMExperimento.aguardando_equipamento)


@router.callback_query(F.data == "exp_plano_rag")
async def experimento_plano_rag(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        await callback.answer("Erro: mensagem indisponível.", show_alert=True)
        return
    await callback.message.edit_text(
        "✅ <b>Protocolo selecionado!</b>\n\n"
        "Qual o <b>primeiro equipamento</b> do protocolo que você vai usar?\n"
        "Digite o nome:",
        parse_mode="HTML"
    )
    await state.set_state(FSMExperimento.aguardando_equipamento)


@router.callback_query(F.data == "exp_manual")
async def experimento_manual(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        await callback.answer("Erro: mensagem indisponível.", show_alert=True)
        return
    await callback.message.edit_text(
        "✏️ <b>Planejamento manual</b>\n\n"
        "Qual o <b>primeiro equipamento</b> que você vai usar?\n"
        "Digite o nome:",
        parse_mode="HTML"
    )
    await state.set_state(FSMExperimento.aguardando_equipamento)


@router.message(FSMExperimento.aguardando_equipamento)
async def experimento_equipamento(message: Message, state: FSMContext):
    if message.text is None:
        return
    termo = message.text.strip()
    if not termo:
        await message.answer("Digite o nome do equipamento:")
        return

    resultados = listar_itens(termo_busca=termo)
    if not resultados:
        await message.answer(
            f"🔍 Não encontrei '<b>{termo}</b>' no sistema.\n"
            "Tente outro nome:",
            parse_mode="HTML"
        )
        return

    item, lab = resultados[0]
    sigla_lab = lab.sigla if lab else "N/A"

    # Verifica conflito ativo (alguém já em uso?)
    with Session(engine) as session:
        statement = select(Reserva, Usuario).join(Usuario).where(
            (Reserva.item_id == item.id) &
            (Reserva.status == StatusReserva.EM_ANDAMENTO)
        )
        uso_ativo = session.exec(statement).first()

    if uso_ativo:
        reserva_ativa, usuario_dono = uso_ativo
        await message.answer(
            f"⚠️ <b>{item.nome}</b> está em uso agora por {usuario_dono.nome}.\n"
            "Você quer agendar mesmo assim ou escolher outro equipamento?",
            parse_mode="HTML"
        )

    # Salva o equipamento na lista de recursos
    dados = await state.get_data()
    recursos = dados.get("recursos", [])
    if not any(r["id"] == str(item.id) for r in recursos):
        recursos.append({
            "id": str(item.id),
            "nome": item.nome,
            "lab": sigla_lab,
        })
    await state.update_data(recursos=recursos)

    # Pergunta a duração
    teclado_duracao = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="1 Hora", callback_data="exp_duracao_1"),
         InlineKeyboardButton(text="2 Horas", callback_data="exp_duracao_2")],
        [InlineKeyboardButton(text="3 Horas", callback_data="exp_duracao_3"),
         InlineKeyboardButton(text="4+ Horas", callback_data="exp_duracao_4")],
    ])
    await message.answer(
        f"⚙️ <b>{item.nome}</b> selecionado ({sigla_lab}).\n"
        "Por quanto tempo vai usar?",
        reply_markup=teclado_duracao,
        parse_mode="HTML"
    )
    await state.set_state(FSMExperimento.aguardando_duracao)


@router.callback_query(FSMExperimento.aguardando_duracao, F.data.startswith("exp_duracao_"))
async def experimento_duracao(callback: CallbackQuery, state: FSMContext):
    if callback.data is None:
        return
    if not isinstance(callback.message, Message):
        await callback.answer("Erro: mensagem indisponível.", show_alert=True)
        return

    horas = callback.data.replace("exp_duracao_", "")

    if horas == "4":
        await callback.message.edit_text(
            "⏱️ Por quantas horas no total? (digite o número)",
            parse_mode="HTML"
        )
        # Guarda marcador de espera
        await state.update_data(duracao_personalizada=True)
        return

    duration = int(horas)
    await state.update_data(duracao=float(duration))
    if isinstance(callback.message, Message):
        await _perguntar_mais_recurso(callback.message, state)
    else:
        await callback.answer("Clique novamente no horário de início.", show_alert=True)
        await state.set_state(FSMExperimento.aguardando_mais_recurso)


@router.message(FSMExperimento.aguardando_duracao)
async def experimento_duracao_custom(message: Message, state: FSMContext):
    dados = await state.get_data()
    if not dados.get("duracao_personalizada"):
        # Não esperávamos texto aqui — ignora se vier de outro estado
        return
    if message.text is None:
        return

    try:
        duration = float(message.text.replace(",", ".").strip())
    except ValueError:
        await message.answer("Digite um número válido de horas (ex: 2.5):")
        return

    if duration <= 0 or duration > 24:
        await message.answer("A duração deve estar entre 0.5 e 24 horas.")
        return

    await state.update_data(duracao=float(duration), duracao_personalizada=False)
    await _perguntar_mais_recurso(message, state)


async def _perguntar_mais_recurso(target: Message, state: FSMContext):
    """Helper: pergunta se o usuário quer adicionar mais recursos (vidraria, reagente, material)."""
    dados = await state.get_data()
    recursos = dados.get("recursos", [])
    nomes = ", ".join(r["nome"] for r in recursos)

    teclado = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Adicionar material", callback_data="exp_recurso_sim")],
        [InlineKeyboardButton(text="⏭️ Não, seguir", callback_data="exp_recurso_nao")],
    ])
    await target.answer(
        f"🧪 <b>Seu plano até agora:</b>\n"
        f"  ⚙️ Recursos: {nomes}\n\n"
        f"Vai usar alguma <b>vidraria</b>, <b>reagente</b> ou <b>material de apoio</b>?\n"
        f"<i>(Ex: balão 60mL, 1-10 Fenantrolina, álcool 70%)</i>",
        reply_markup=teclado,
        parse_mode="HTML"
    )
    await state.set_state(FSMExperimento.aguardando_mais_recurso)

@router.callback_query(F.data == "exp_recurso_sim")
async def experimento_recurso_sim(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        await callback.answer("Erro: mensagem indisponível.", show_alert=True)
        return
    await callback.message.edit_text(
        "🔎 Digite o nome da <b>vidraria</b>, <b>reagente</b> ou <b>material</b> que você vai usar:\n\n"
        "<i>(Ex: balão 60mL, 1-10 Fenantrolina, álcool 70%)</i>",
        parse_mode="HTML"
    )
    await state.set_state(FSMExperimento.aguardando_mais_recurso)

@router.callback_query(F.data == "exp_recurso_nao")
async def experimento_recurso_nao(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        await callback.answer("Erro: mensagem indisponível.", show_alert=True)
        return
    await callback.message.edit_text("👍 <b>Perfeito!</b> Recursos finalizados.")
    await _perguntar_inicio(callback.message, state)

@router.message(FSMExperimento.aguardando_mais_recurso)
async def experimento_mais_recurso(message: Message, state: FSMContext):
    if message.text is None:
        return
    termo = message.text.strip()
    if not termo:
        await message.answer("Digite o nome do material/equipamento:")
        return

    resultados = listar_itens(termo_busca=termo)
    if not resultados:
        await message.answer(
            f"⚠️ <b>'{termo}' não encontrado no estoque.</b>\n"
            "Pode digitar o nome correto, ou toque em <b>⏭️ Não, seguir</b>.",
            parse_mode="HTML"
        )
        return

    item, lab = resultados[0]
    sigla_lab = lab.sigla if lab else "N/A"

    dados = await state.get_data()
    recursos = dados.get("recursos", [])
    if not any(r["id"] == str(item.id) for r in recursos):
        recursos.append({
            "id": str(item.id),
            "nome": item.nome,
            "lab": sigla_lab,
        })
    await state.update_data(recursos=recursos)

    # Pergunta se quer adicionar mais
    teclado = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Adicionar outro", callback_data="exp_recurso_sim")],
        [InlineKeyboardButton(text="⏭️ Não, seguir", callback_data="exp_recurso_nao")],
    ])
    await message.answer(
        f"✅ <b>{item.nome}</b> adicionado ao plano ({sigla_lab}).\n\n",
        reply_markup=teclado,
        parse_mode="HTML"
    )

async def _perguntar_inicio(target: Message, state: FSMContext):
    """Helper: envia a pergunta de horário de início."""
    dados = await state.get_data()
    duracao = dados.get("duracao", 1.0)

    recursos = dados.get("recursos", [])
    nomes = ", ".join(r["nome"] for r in recursos)
    fuso = pytz.timezone("America/Fortaleza")
    agora = datetime.now(fuso).replace(tzinfo=None)

    teclado = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⚡ Agora (início imediato)", callback_data="exp_inicio_agora")],
        [InlineKeyboardButton(text="📅 Escolher data/hora", callback_data="exp_inicio_escolher")],
    ])
    await target.answer(
        f"📋 <b>Seu plano:</b>\n"
        f"  🧪 Recursos: {nomes}\n"
        f"  ⏱️ Duração: {duracao:.1f} h\n\n"
        f"Quando começa?",
        reply_markup=teclado,
        parse_mode="HTML"
    )
    await state.set_state(FSMExperimento.aguardando_inicio)


@router.callback_query(FSMExperimento.aguardando_inicio, F.data == "exp_inicio_agora")
async def experimento_inicio_agora(callback: CallbackQuery, state: FSMContext):
    fuso = pytz.timezone("America/Fortaleza")
    agora = datetime.now(fuso).replace(tzinfo=None)

    await state.update_data(inicio=agora)
    if isinstance(callback.message, Message):
        await _agendar_recursos(callback.message, callback.from_user.id, state, agora)
    else:
        await callback.answer("Erro: mensagem indisponível.", show_alert=True)


@router.callback_query(FSMExperimento.aguardando_inicio, F.data == "exp_inicio_escolher")
async def experimento_inicio_escolher(callback: CallbackQuery, state: FSMContext):
    if not isinstance(callback.message, Message):
        await callback.answer("Erro: mensagem indisponível.", show_alert=True)
        return
    await callback.message.edit_text(
        "📅 Digite a data e hora de início no formato:\n"
        "<b>DD/MM/AAAA HH:MM</b>\n\n"
        "<i>Ex: 20/08/2025 14:00</i>",
        parse_mode="HTML"
    )
    # Mantém o estado, mas texto livre virá no próximo message handler
    await state.update_data(aguardando_data_texto=True)


@router.message(FSMExperimento.aguardando_inicio)
async def experimento_inicio_texto(message: Message, state: FSMContext):
    dados = await state.get_data()
    if not dados.get("aguardando_data_texto"):
        return
    if message.text is None or message.from_user is None:
        return

    texto = message.text.strip()
    try:
        dt_inicio = datetime.strptime(texto, "%d/%m/%Y %H:%M")
    except ValueError:
        await message.answer(
            "Formato inválido. Use <b>DD/MM/AAAA HH:MM</b> — ex: 20/08/2025 14:00",
            parse_mode="HTML"
        )
        return

    if dt_inicio < datetime.now().replace(tzinfo=None) - timedelta(minutes=1):
        await message.answer("A data de início não pode estar no passado.")
        return

    await state.update_data(inicio=dt_inicio, aguardando_data_texto=False)
    await _agendar_recursos(message, message.from_user.id, state, dt_inicio)


async def _agendar_recursos(target: Message, telegram_id: int, state: FSMContext, dt_inicio: datetime):
    """Executa as reservas de TODOS os recursos do plano sob um MESMO grupo_id."""
    dados = await state.get_data()
    duracao = dados.get("duracao", 1.0)
    recursos = dados.get("recursos", [])
    descricao = dados.get("descricao_experimento")

    dt_fim = dt_inicio + timedelta(hours=duracao)

    if not recursos:
        await target.answer("⚠️ Nenhum recurso foi adicionado ao plano. Refaça o /experimento.")
        await state.clear()
        return

    # Cria TODAS as reservas do experimento em um único agendamento lógico (grupo_id comum)
    resultado = criar_reservas_em_grupo(
        telegram_id=telegram_id,
        itens=[uuid.UUID(r["id"]) for r in recursos],
        data_inicio=dt_inicio,
        data_fim=dt_fim,
    )

    sucessos = resultado["sucessos"]
    falhas = resultado["falhas"]

    # Um único alarme de início para o experimento inteiro (usa o grupo_id nos botões)
    if resultado["sucesso"]:
        grupo_id_str = str(resultado["grupo_id"])
        agendar_alarme_inicio(dt_inicio, telegram_id, ", ".join(sucessos), grupo_id_str)
        agendar_alarme_fim(dt_fim, telegram_id, ", ".join(sucessos), grupo_id_str)

    # Monta resumo
    msg = "✅ <b>Experimento Planejado!</b>\n\n"
    msg += f"📋 <b>Objetivo:</b> {descricao or '—'}\n"
    msg += f"📅 <b>Início:</b> {dt_inicio.strftime('%d/%m/%Y às %H:%M')}\n"
    msg += f"⏱️ <b>Duração:</b> {duracao:.1f} h\n"
    msg += f"⏰ <b>Término previsto:</b> {dt_fim.strftime('%d/%m/%Y às %H:%M')}\n\n"

    if sucessos:
        msg += "✅ <b>Reservados (1 agendamento):</b>\n" + "\n".join(f"  • {n}" for n in sucessos) + "\n"
    if falhas:
        msg += "\n⚠️ <b>Conflitos:</b>\n" + "\n".join(f"  • {f}" for f in falhas) + "\n\n"
        msg += "<i>Alinhe os conflitos e refaça o agendamento se necessário.</i>"

    if isinstance(target, Message):
        await target.answer(msg, parse_mode="HTML")
    else:
        await target.edit_text(msg, parse_mode="HTML")
    await state.clear()