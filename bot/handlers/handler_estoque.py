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


@router.message(Command("adicionar_item"))
async def cmd_adicionar_item(message: Message):
    """
    Cadastra um novo item diretamente via comando no Telegram.
    Formato rápido usando barras verticais (|):
    /adicionar_item Nome | Categoria | Quantidade | Unidade | Lab | Bancada | Complemento | Marca | Lote
    
    Exemplo:
    /adicionar_item Cloreto de Sódio P.A. | reagente | 500 | g | LAT | Bancada 02 | do lado da pia | Synth | L-2024
    """
    import re
    from services.estoque import cadastrar_novo_item

    texto = message.text or ""
    partes_cmd = texto.split(maxsplit=1)

    if len(partes_cmd) < 2 or not partes_cmd[1].strip() or partes_cmd[1].strip().lower() in ("ajuda", "help"):
        await message.answer(
            "➕ <b>Como adicionar um novo item via Telegram:</b>\n\n"
            "Envie o comando separando os campos com barra vertical (<code>|</code>):\n"
            "<code>/adicionar_item Nome | Categoria | Quantidade | Unidade | Lab | Bancada | Complemento | Marca | Lote</code>\n\n"
            "🧪 <b>Exemplo prático:</b>\n"
            "<code>/adicionar_item Cloreto de Sódio | reagente | 500 | g | LAT | Bancada 02 | do lado da pia | Synth | L-2024</code>\n\n"
            "<i>Categorias aceitas:</i> <code>reagente</code>, <code>equipamento</code>, <code>vidraria</code>, <code>limpeza</code>.\n\n"
            "💡 <i>Você também pode simplesmente pedir em linguagem natural no chat:\n"
            "\"Cadastra 500g de sulfato de cobre no LAT bancada 1 do lado da pia marca Synth lote 9982\"</i>",
            parse_mode="HTML"
        )
        return

    conteudo = partes_cmd[1].strip()
    campos = [c.strip() for c in conteudo.split("|")]

    nome = campos[0] if len(campos) > 0 else ""
    if not nome:
        await message.answer("❌ O nome do item é obrigatório.")
        return

    categoria = campos[1] if len(campos) > 1 and campos[1] else "reagente"
    qtd_raw = campos[2] if len(campos) > 2 and campos[2] else "1"
    unidade = campos[3] if len(campos) > 3 and campos[3] else "un"
    lab = campos[4] if len(campos) > 4 and campos[4] else "LAT"
    bancada = campos[5] if len(campos) > 5 and campos[5] else None
    complemento = campos[6] if len(campos) > 6 and campos[6] else None
    marca = campos[7] if len(campos) > 7 and campos[7] else None
    lote = campos[8] if len(campos) > 8 and campos[8] else None

    # Tenta extrair unidade se estiver grudada no número (ex: 500g -> 500 e g)
    match_num = re.match(r"^([\d\.,]+)\s*([a-zA-Zµu]+)?$", qtd_raw)
    if match_num:
        qtd_str = match_num.group(1).replace(",", ".")
        unidade_extraida = match_num.group(2)
        if unidade_extraida and (unidade == "un" or len(campos) <= 3):
            unidade = unidade_extraida
    else:
        qtd_str = qtd_raw.replace(",", ".")

    try:
        qtd_num = float(qtd_str)
    except ValueError:
        await message.answer(f"❌ Quantidade inválida: '{qtd_raw}'. Envie um número válido.")
        return

    try:
        item = cadastrar_novo_item(
            nome=nome,
            categoria=categoria,
            quantidade_inicial=qtd_num,
            unidade_medida=unidade,
            laboratorio_sigla=lab,
            bancada=bancada,
            complemento=complemento,
            marca=marca,
            lote=lote,
            estado="Bom",
        )

        local_formatado = item.localizacao_exata if item.localizacao_exata else "Não especificada"
        lab_sigla = lab.upper() if lab else "LAT"

        resposta = (
            f"✅ <b>Item cadastrado com sucesso!</b>\n\n"
            f"📦 <b>Nome:</b> {item.nome}\n"
            f"🏷️ <b>Categoria:</b> {item.categoria.value if hasattr(item.categoria, 'value') else item.categoria}\n"
            f"⚖️ <b>Quantidade:</b> {item.quantidade_atual} {item.unidade_medida}\n"
            f"🏢 <b>Laboratório:</b> {lab_sigla}\n"
            f"📍 <b>Localização:</b> {local_formatado}\n"
        )
        if item.marca:
            resposta += f"🏭 <b>Marca:</b> {item.marca}\n"
        if item.lote:
            resposta += f"🔢 <b>Lote:</b> {item.lote}\n"

        await message.answer(resposta, parse_mode="HTML")
    except Exception as e:
        await message.answer(f"❌ Erro ao cadastrar item: {str(e)}")

