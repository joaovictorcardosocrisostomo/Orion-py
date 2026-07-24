from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from sqlmodel import Session

from database.db import engine
from database.models import Item
from services.estoque import listar_itens # Lembre-se do nome do seu arquivo aqui (pode ser service_estoque)

router = Router()

class FSMRelatorio(StatesGroup):
    aguardando_nome_item = State()
    aguardando_estado_avaria = State()
    aguardando_detalhes_avaria = State() # A pergunta extra do que quebrou!

# ==========================================
# 1. COMANDO MANUAL (/relatorio)
# ==========================================
@router.message(Command("relatorio"))
async def iniciar_relatorio_manual(message: Message, state: FSMContext):
    await message.answer("✍️ <b>Relatório de Uso</b>\nQual equipamento, reagente ou vidraria você quer relatar agora?", parse_mode="HTML")
    await state.set_state(FSMRelatorio.aguardando_nome_item)

@router.message(FSMRelatorio.aguardando_nome_item)
async def buscar_item_relatorio(message: Message, state: FSMContext):
    resultados = listar_itens(termo_busca=message.text)
    if not resultados:
        await message.answer(f"Não encontrei '{message.text}'. Tente novamente:")
        return

    item = resultados[0][0]
    await state.update_data(item_id=str(item.id), nome_item=item.nome)

    teclado = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tudo perfeito", callback_data="estado_bom")],
        [InlineKeyboardButton(text="⚠️ Apresentou avaria/quebrou", callback_data="estado_avaria")]
    ])
    
    await message.answer(f"Como você deixou o <b>{item.nome}</b> após o uso?", reply_markup=teclado, parse_mode="HTML")
    await state.set_state(FSMRelatorio.aguardando_estado_avaria)


# ==========================================
# 2. FLUXO DE AVARIA (Conectado aos Botões)
# ==========================================
@router.callback_query(FSMRelatorio.aguardando_estado_avaria)
async def processar_estado(callback: CallbackQuery, state: FSMContext):
    dados = await state.get_data()
    item_id = dados.get("item_id")
    nome_item = dados.get("nome_item")

    if callback.data == "estado_bom":
        with Session(engine) as session:
            item = session.get(Item, item_id)
            if item:
                item.estado = "Bom"
            session.commit()
            
        await callback.message.edit_text(f"✅ Relatório salvo! Obrigado por cuidar do <b>{nome_item}</b>.", parse_mode="HTML")
        await state.clear()
        
    elif callback.data == "estado_avaria":
        # Em vez de fechar, avança a FSM para perguntar o que aconteceu!
        await callback.message.edit_text(
            f"⚠️ <b>Avaria no {nome_item}</b>\nPor favor, digite uma breve descrição do que aconteceu ou o que está quebrado:", 
            parse_mode="HTML"
        )
        await state.set_state(FSMRelatorio.aguardando_detalhes_avaria)

@router.message(FSMRelatorio.aguardando_detalhes_avaria)
async def processar_detalhes(message: Message, state: FSMContext):
    detalhes = message.text
    dados = await state.get_data()
    
    with Session(engine) as session:
        item = session.get(Item, dados.get("item_id"))
        if item:
            item.estado = "Quebrado"
            # Aqui, no futuro, você pode salvar o texto "detalhes" na tabela de LogUso!
        session.commit()

    await message.answer(
        f"🚨 Relatório de avaria registrado!\n"
        f"<i>Nota gravada: '{detalhes}'</i>\n"
        f"O equipamento foi bloqueado para uso até a manutenção.",
        parse_mode="HTML"
    )
    await state.clear()