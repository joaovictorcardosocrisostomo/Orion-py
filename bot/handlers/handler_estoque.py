# bot/handlers/estoque.py - gerencia os comandos relacionados ao estoque
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

# Importando os services
from services.estoque import listar_itens, formatar_mensagem_estoque
from database.models import CategoriaItem

router = Router()

# Mapeia palavras-chave de filtro para categorias reais
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

    # 1. Se o termo é um filtro de categoria (ex: "reagente"), busca a categoria inteira
    if termo_busca and termo_busca.strip().lower() in FILTROS_CATEGORIA:
        categoria = FILTROS_CATEGORIA[termo_busca.strip().lower()]
        resultados = listar_itens(categoria=categoria.value)
        texto_final = formatar_mensagem_estoque(resultados, termo_busca)
    else:
        # 2. Senão, busca por nome de item (imune a acentos e hífens)
        resultados = listar_itens(termo_busca=termo_busca)
        texto_final = formatar_mensagem_estoque(resultados, termo_busca)

    # Envia texto pro user
    await message.answer(texto_final, parse_mode="HTML")