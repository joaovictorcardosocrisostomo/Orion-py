# bot/handlers/start.py
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

# Instanciando o Router
router = Router()

@router.message(Command("start")) # teste
async def cmd_start(message: Message):
    await message.answer(f"Olá, <b>{message.from_user.first_name}</b>! O Orion está ativo via Polling!")