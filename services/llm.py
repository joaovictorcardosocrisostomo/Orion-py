import json
from datetime import datetime
import pytz
from openai import AsyncOpenAI
from core.config import settings

client = AsyncOpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# 🧠 MEMÓRIA DE CURTO PRAZO: Dicionário para guardar as conversas de cada usuário
memoria_conversas = {}

TOOLS = [
    # Ferramentas de busca (MANTIDAS)
    {
        "type": "function", "function": {
            "name": "buscar_reagente", "description": "Busca produtos químicos.",
            "parameters": {"type": "object", "properties": {"termo": {"type": "string"}}, "required": ["termo"]}
        }
    },
    {
        "type": "function", "function": {
            "name": "buscar_equipamento", "description": "Busca equipamentos.",
            "parameters": {"type": "object", "properties": {"termo": {"type": "string"}}, "required": ["termo"]}
        }
    },
    {
        "type": "function", "function": {
            "name": "buscar_vidraria", "description": "Busca vidrarias.",
            "parameters": {"type": "object", "properties": {"termo": {"type": "string"}}, "required": ["termo"]}
        }
    },
    {
        "type": "function", "function": {
            "name": "buscar_limpeza", "description": "Busca materiais de limpeza.",
            "parameters": {"type": "object", "properties": {"termo": {"type": "string"}}, "required": ["termo"]}
        }
    },
    # NOVA FERRAMENTA DE AGENDAMENTO
    {
        "type": "function",
        "function": {
            "name": "registrar_agendamento",
            "description": "Acione APENAS quando tiver todas as informações: nome do item, data de início e data de término. Se faltar a hora ou o dia, não acione a função, responda ao usuário perguntando o que falta.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo_equipamento": {"type": "string", "description": "Nome do equipamento. Ex: espectrofotômetro"},
                    "data_inicio_iso": {"type": "string", "description": "Formato EXATO: YYYY-MM-DD HH:MM"},
                    "data_fim_iso": {"type": "string", "description": "Formato EXATO: YYYY-MM-DD HH:MM"}
                },
                "required": ["termo_equipamento", "data_inicio_iso", "data_fim_iso"]
            }
        }
    }
]

async def analisar_intencao(texto_usuario: str, telegram_id: int):
    """Agora a IA sabe quem está falando e que horas são."""
    
    # ⏱️ INJEÇÃO DE TEMPO
    fuso = pytz.timezone("America/Fortaleza")
    agora = datetime.now(fuso)
    data_hora_atual = agora.strftime("%Y-%m-%d %H:%M")
    dia_semana = agora.strftime("%A")

    prompt_sistema = f"""Você é o Orion, IA de gestão do laboratório.
Data e hora exatas de agora: {data_hora_atual} ({dia_semana}).

REGRA DE AGENDAMENTO:
1. O usuário precisa de um item, hora de início e hora de fim. 
2. Use a matemática do calendário atual para converter "amanhã de tarde" em datas e horas ISO 8601 aproximadas (ex: 14:00 às 17:00).
3. Se ele disser "quero usar o forno amanhã" mas NÃO disser a hora, NÃO CHAME a ferramenta registrar_agendamento. Converse em linguagem natural e pergunte "Qual horário de início e fim?"
4. Só chame a ferramenta quando tiver o pacote completo."""

    # 🧠 RECUPERANDO A MEMÓRIA DO USUÁRIO
    if telegram_id not in memoria_conversas:
        memoria_conversas[telegram_id] = []
    
    # Adiciona a frase atual do usuário na memória
    memoria_conversas[telegram_id].append({"role": "user", "content": texto_usuario})
    
    # Limita a memória às últimas 6 interações (para não estourar o limite de tokens da API)
    if len(memoria_conversas[telegram_id]) > 6:
        memoria_conversas[telegram_id] = memoria_conversas[telegram_id][-6:]

    # Constrói o histórico final juntando o Sistema + Memória
    mensagens_para_ia = [{"role": "system", "content": prompt_sistema}] + memoria_conversas[telegram_id]

    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=mensagens_para_ia,
            tools=TOOLS,
            tool_choice="auto",
            temperature=0.0
        )

        mensagem = response.choices[0].message
        
        # Salva a resposta da IA na memória para ela lembrar do que perguntou!
        if mensagem.content:
            memoria_conversas[telegram_id].append({"role": "assistant", "content": mensagem.content})

        if hasattr(mensagem, 'tool_calls') and mensagem.tool_calls:
            tool_call = mensagem.tool_calls[0]
            return {
                "tipo": "funcao",
                "nome": tool_call.function.name,
                "args": json.loads(tool_call.function.arguments)
            }
        
        return {"tipo": "texto", "conteudo": mensagem.content}
        
    except Exception as e:
        print(f"Erro no LLM: {e}")
        return {"tipo": "erro", "conteudo": "Falha na comunicação neural."}