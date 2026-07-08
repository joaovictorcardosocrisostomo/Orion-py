from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    # Configurações do Telegram
    TELEGRAM_BOT_TOKEN: str
    
    # Configurações do Banco
    DATABASE_URL: str
    REDIS_URL: str
    
    # Configurações de IA
    GROQ_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    PINECONE_API_KEY: Optional[str] = None 
    
    # Webhooks pro futuro
    # WEBHOOK_URL: str = "http://localhost:8000"
    # WEBHOOK_PATH: str = "/webhook"

    class Config:
        env_file = ".env"
        extra = "ignore" # Isso diz ao Pydantic para ignorar extras no .env se houver

settings = Settings()