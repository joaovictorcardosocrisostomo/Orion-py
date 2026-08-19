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
    GOOGLE_API_KEY: Optional[str] = None  # Usada pelo google-genai SDK
    
    # Segurança
    ADMIN_SECRET: str = "orion2026"
    
    # Webhooks pro futuro
    # WEBHOOK_URL: str = "http://localhost:8000"
    # WEBHOOK_PATH: str = "/webhook"

    @property
    def gemini_api_key_resolved(self) -> str:
        """Resolve a chave do Gemini: GOOGLE_API_KEY tem prioridade, fallback GEMINI_API_KEY."""
        return self.GOOGLE_API_KEY or self.GEMINI_API_KEY or ""

    class Config:
        env_file = ".env"
        extra = "ignore" # Isso diz ao Pydantic para ignorar extras no .env se houver

settings = Settings()