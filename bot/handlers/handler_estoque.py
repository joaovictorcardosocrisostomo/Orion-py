# bot/handlers/estoque.py - gerencia os comandos relacionados ao estoque
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

# Importando os services
from services.service_estoque import listar_itens, formatar_mensagem_estoque

router = Router()

@router.message(Command("estoque"))
async def cmd_estoque(message: Message):
    argumentos = message.text.split(maxsplit=1)
    termo_busca = argumentos[1] if len(argumentos) > 1 else None

    # Retorna uma lista de pares: [(Reagente1, Lab1), (Reagente2, Lab2), ...] buscada no banco
    resultados = listar_itens(termo_busca)
    
    # Formata texto
    texto_final = formatar_mensagem_estoque(resultados, termo_busca)
    
    # Envia texto pro user
    await message.answer(texto_final, parse_mode="HTML")