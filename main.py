import asyncio
import logging # só pra exibir mensagem no terminal
from contextlib import asynccontextmanager
from fastapi import FastAPI
from aiogram import Bot, Dispatcher
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.storage.redis import RedisStorage

# Importações internas
from core.config import settings
from database.db import init_db, reset_db, redis_client
from bot.handlers import (
    handler_estoque,
    nlp,
    onboarding,
    experimento,
    relatorio,
    auditoria,
    adicionar_pop,
    dashboard,
    caderno,
    manutencao,
    briefing,
)
from services.scheduler import iniciar_scheduler
from api.dashboard import router as dashboard_api_router

from bot.middlewares.auth import AuthMiddleware

# Logging
logging.basicConfig(level=logging.INFO)

# Instâncias
bot = Bot(token=settings.TELEGRAM_BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher(storage=RedisStorage(redis=redis_client))

# Middleware global de autorização (restringe acesso a Membros e Administradores)
dp.message.outer_middleware(AuthMiddleware())
dp.callback_query.outer_middleware(AuthMiddleware())

# Handlers - transferidos pra pasta bot em forma de Routers
# Conectando routers ao dispatcher (com verificação para evitar re-anexo)
routers = [
    onboarding.router,
    dashboard.router,
    handler_estoque.router,
    relatorio.router,
    caderno.router,
    manutencao.router,
    briefing.router,
    nlp.router,
    experimento.router,
    auditoria.router,
    adicionar_pop.router,
]
for r in routers:
    if r.parent_router is None:
        dp.include_router(r)

# Função que mantém o bot rodando em segundo plano
async def run_bot():
    logging.info("Iniciando Polling do Telegram...")
    # ⏰ LIGA O RELÓGIO AQUI, PASSANDO A INSTÂNCIA DO BOT!
    iniciar_scheduler(bot)
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
    try:
        await task
    except asyncio.CancelledError:
        pass
    try:
        await redis_client.aclose()
    except Exception:
        pass
    try:
        await bot.session.close()
    except Exception:
        pass
    logging.info("Bot e conexões parados.")

from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse

STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Orion Cientista API", lifespan=lifespan)

# Middleware de Segurança Defensiva HTTP (Defesa em Profundidade)
@app.middleware("http")
async def security_headers_middleware(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.include_router(dashboard_api_router)

@app.get("/")
def read_root():
    return RedirectResponse(url="/dashboard")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)