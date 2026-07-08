import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# Importações internas
from core.config import settings
from database.db import init_db, reset_db
from bot.handlers import handler_estoque, start, nlp

# Logging
logging.basicConfig(level=logging.INFO)

# Instâncias
bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()

# Handlers - transferidos pra pasta bot em forma de Routers
# Conectando routers ao dispatcher
dp.include_router(start.router)
dp.include_router(handler_estoque.router)
dp.include_router(nlp.router)

# Função que mantém o bot rodando em segundo plano
async def run_bot():
    logging.info("Iniciando Polling do Telegram...")
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)
    
# Lifespan do FastAPI
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup - APENAS NESTA EXECUÇÃO, DESCOMENTE A LINHA ABAIXO
    # reset_db() 
    # logging.info("Banco de dados resetado com sucesso!")
    
    init_db()
    logging.info("Banco de dados pronto.")
    
    # Inicia o bot em segundo plano
    task = asyncio.create_task(run_bot())
    
    yield
    
    # Shutdown
    task.cancel()
    logging.info("Bot parado.")

app = FastAPI(title="Orion Cientista API", lifespan=lifespan)

@app.get("/")
def read_root():
    return {"status": "Servidor Orion rodando. Bot via Polling."}