# bot/handlers/handler_estoque.py - gerencia os comandos e edição do estoque
import uuid
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from sqlmodel import Session

from database.db import engine
from database.models import Item, CategoriaItem
from services.estoque import listar_itens, formatar_mensagem_estoque, editar_item
from bot.keyboards import keyboard_opcoes_edicao
from bot.states import EstoqueEditStates

router = Router()

FILTROS_CATEGORIA = {
    "reagente": CategoriaItem.REAGENTE,
    "reagentes": CategoriaItem.REAGENTE,
    "equipamento": CategoriaItem.EQUIPAMENTO,
    "equipamentos": CategoriaItem.EQUIPAMENTO,
    "vidraria": CategoriaItem.VIDRARIA,
    "vidrarias": CategoriaItem.VIDRARIA,
    "limpeza": CategoriaItem.LIMPEZA,
}

@router.message(Command("estoque"))
async def cmd_estoque(message: Message):
    argumentos = message.text.split(maxsplit=1)
    termo_busca = argumentos[1] if len(argumentos) > 1 else None

    if termo_busca and termo_busca.strip().lower() in FILTROS_CATEGORIA:
        categoria = FILTROS_CATEGORIA[termo_busca.strip().lower()]
        resultados = listar_itens(categoria=categoria.value)
        texto_final = formatar_mensagem_estoque(resultados, termo_busca)
    else:
        resultados = listar_itens(termo_busca=termo_busca)
        texto_final = formatar_mensagem_estoque(resultados, termo_busca)

    await message.answer(texto_final, parse_mode="HTML")

@router.message(Command("editar_item"))
async def cmd_editar_item(message: Message):
    """Comando /editar_item <nome_do_item> para iniciar a edição."""
    argumentos = message.text.split(maxsplit=1)
    if len(argumentos) < 2:
        await message.answer("⚠️ Uso incorreto. Digite: <code>/editar_item &lt;nome do item&gt;</code>", parse_mode="HTML")
        return

    termo = argumentos[1]
    resultados = listar_itens(termo_busca=termo)
    if not resultados:
        await message.answer(f"🔍 Nenhum item encontrado com o termo: <b>{termo}</b>", parse_mode="HTML")
        return

    # Se encontrar múltiplos itens ou apenas um
    botoes = []
    for item, lab in resultados[:5]:
        botoes.append([InlineKeyboardButton(text=f"{item.nome} ({item.categoria.value})", callback_data=f"sel_item:{item.id}")])

    await message.answer(
        "Selecione o item que deseja editar:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=botoes)
    )

@router.callback_query(F.data.startswith("sel_item:"))
async def callback_selecionar_item(callback: CallbackQuery):
    item_id_str = callback.data.split(":")[1]
    item_id = uuid.UUID(item_id_str)

    with Session(engine) as session:
        item = session.get(Item, item_id)
        if not item:
            await callback.message.edit_text("❌ Item não encontrado.")
            return

        texto = (
            f"<b>Editando:</b> {item.nome}\n"
            f"<b>Categoria:</b> {item.categoria.value}\n"
            f"<b>Quantidade atual:</b> {item.quantidade_atual} {item.unidade_medida}\n\n"
            "Escolha o campo que deseja alterar:"
        )
        markup = keyboard_opcoes_edicao(item.id, item.categoria)
        await callback.message.edit_text(texto, reply_markup=markup, parse_mode="HTML")

@router.callback_query(F.data.startswith("edit:"))
async def callback_campo_edicao(callback: CallbackQuery, state: FSMContext):
    _, item_id_str, campo = callback.data.split(":")
    await state.update_data(item_id=item_id_str, campo=campo)
    await state.set_state(EstoqueEditStates.aguardando_novo_valor)
    
    nomes_campos = {
        "nome": "o novo nome",
        "quantidade_atual": "a nova quantidade (apenas números)",
        "localizacao_exata": "a nova localização exata",
        "unidade_medida": "a nova unidade de medida (ex: g, ml, un)",
        "lote": "o novo lote",
        "marca": "a nova marca"
    }
    
    campo_humano = nomes_campos.get(campo, campo)
    await callback.message.answer(f"✏️ Por favor, envie {campo_humano}:")
    await callback.answer()

@router.message(EstoqueEditStates.aguardando_novo_valor)
async def processar_novo_valor(message: Message, state: FSMContext):
    data = await state.get_data()
    item_id = uuid.UUID(data["item_id"])
    campo = data["campo"]
    valor_bruto = message.text.strip()

    # Conversões necessárias de tipo
    valor_final = valor_bruto
    if campo == "quantidade_atual":
        try:
            valor_final = float(valor_bruto.replace(",", "."))
        except ValueError:
            await message.answer("❌ Valor inválido. Envie um número válido para a quantidade:")
            return

    # Executa a edição no banco de dados
    sucesso = editar_item(item_id, {campo: valor_final})
    if sucesso:
        await message.answer("✅ Item atualizado com sucesso!")
    else:
        await message.answer("❌ Não foi possível atualizar o item. Verifique os dados e tente novamente.")

    await state.clear()

@router.callback_query(F.data == "edit_cancelar")
async def callback_cancelar_edicao(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Edição cancelada.")
