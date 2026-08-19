import json
from datetime import datetime
from typing import cast
import pytz
from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionMessageParam,
    ChatCompletionToolParam,
    ChatCompletionMessageToolCall,
)
from core.config import settings

client = AsyncOpenAI(
    api_key=settings.GROQ_API_KEY,
    base_url="https://api.groq.com/openai/v1"
)

# 🧠 MEMÓRIA DE CURTO PRAZO: Dicionário para guardar as conversas de cada usuário
memoria_conversas = {}

# 🔐 Confirmações pendentes: telegram_id -> {"nome": ..., "args": ...}
# Ações que alteram dados só executam após o usuário confirmar.
confirmacoes_pendentes = {}

# Ações mutáveis exigem confirmação explícita do usuário antes de executar
ACOES_MUTAVEIS = {
    "registrar_agendamento",
    "registrar_consumo",
    "registrar_descarte",
    "registrar_reposicao",
    "criar_protocolo_experimental",
}

def _texto_negativo(texto: str) -> bool:
    """Detecta se o usuário recusou uma confirmação pendente."""
    if not texto:
        return False
    texto_lower = texto.lower().strip()
    negacoes = ("não", "nao", "nem", "cancela", "cancelar", "deixa", "depois", "nada", "nope")
    return any(texto_lower.startswith(n) or f" {n}" in texto_lower for n in negacoes)


def _texto_afirmativo(texto: str) -> bool:
    """Detecta se o usuário confirmou explicitamente uma ação pendente."""
    if not texto:
        return False
    texto_lower = texto.lower().strip()
    afirmacoes = (
        "sim", "pode", "ok", "okay", "claro", "confirmo", "confirma", "beleza",
        "agenda", "agendar", "reserva", "reservar", "faz", "fecha", "exato",
        "isso", "vai", "pode fazer", "pode agendar", "pode reservar",
    )
    return any(
        texto_lower == a
        or texto_lower.startswith(a + " ")
        or texto_lower.startswith(a + ",")
        or texto_lower.startswith(a + "!")
        for a in afirmacoes
    )

TOOLS: list[ChatCompletionToolParam] = [
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
    },
    # FERRAMENTA DE BUSCA RAG (POPs / Procedimentos)
    {
        "type": "function",
        "function": {
            "name": "consultar_rag",
            "description": "Busca procedimentos experimentais, POPs (Procedimentos Operacionais Padrão) e documentos do laboratório por similaridade semântica. Use quando o usuário perguntar 'como fazer' algo ou pedir um protocolo/procedimento.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo_busca": {
                        "type": "string",
                        "description": "O que o usuário quer fazer. Ex: análise de ferro, titulação, quantificação de proteínas"
                    }
                },
                "required": ["termo_busca"]
            }
        }
    },
    # FERRAMENTA DE CONSUMO — Dá baixa em estoque
    {
        "type": "function",
        "function": {
            "name": "registrar_consumo",
            "description": "Dá baixa no estoque quando um reagente ou material foi consumido/usado. Use quando o usuário disser que usou, gastou, consumiu ou gastou uma quantidade de um item.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo_item": {"type": "string", "description": "Nome ou parte do nome do item consumido. Ex: ácido clorídrico, fenantrolina"},
                    "quantidade": {"type": "number", "description": "Quantidade consumida (número positivo). Ex: 5"},
                    "unidade": {"type": "string", "description": "Unidade de medida, se informada. Ex: ml, g, unidades"}
                },
                "required": ["termo_item", "quantidade"]
            }
        }
    },
    # FERRAMENTA DE DESCARTE
    {
        "type": "function",
        "function": {
            "name": "registrar_descarte",
            "description": "Registra o descarte de material (vidraria quebrada, reagente vencido, sobra de amostra etc.). Use quando o usuário mencionar descartar, quebrar, jogar fora ou desprezar.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo_item": {"type": "string", "description": "Nome ou parte do nome do item descartado"},
                    "quantidade": {"type": "number", "description": "Quantidade descartada (número positivo)"},
                    "motivo": {"type": "string", "description": "Motivo do descarte. Ex: vidraria quebrada, reagente vencido"}
                },
                "required": ["termo_item", "quantidade", "motivo"]
            }
        }
    },
    # FERRAMENTA DE REPOSIÇÃO
    {
        "type": "function",
        "function": {
            "name": "registrar_reposicao",
            "description": "Sinaliza que um item precisa ser reposto/comprado. Use quando o usuário disser que algo acabou, está no último frasco, ou precisa ser comprado/reabastecido.",
            "parameters": {
                "type": "object",
                "properties": {
                    "termo_item": {"type": "string", "description": "Nome ou parte do nome do item a repor"},
                    "quantidade_necessaria": {"type": "number", "description": "Quantidade estimada que precisa ser comprada (número positivo)"}
                },
                "required": ["termo_item", "quantidade_necessaria"]
            }
        }
    },
    # FERRAMENTA DE PROTOCOLO EXPERIMENTAL
    {
        "type": "function",
        "function": {
            "name": "criar_protocolo_experimental",
            "description": "Salva um protocolo experimental no banco de conhecimento para reuso futuro. Use quando o usuário pedir para salvar/guardar um protocolo, procedimento ou método que ele descreveu ou que veio do RAG.",
            "parameters": {
                "type": "object",
                "properties": {
                    "titulo": {"type": "string", "description": "Título do protocolo. Ex: Análise de Ferro por Fenantrolina"},
                    "descricao": {"type": "string", "description": "Breve descrição do objetivo do protocolo"},
                    "etapas": {"type": "string", "description": "Etapas do procedimento, uma por linha, numeradas"},
                    "recursos": {"type": "string", "description": "Recursos necessários (reagentes, equipamentos, vidrarias) separados por vírgula"},
                    "duracao_estimada_min": {"type": "integer", "description": "Duração estimada em minutos"}
                },
                "required": ["titulo", "etapas", "recursos"]
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

REGRAS DE FERRAMENTAS:

[AGENDAMENTO]
1. O usuário precisa de um item, hora de início e hora de fim. 
2. Use a matemática do calendário atual para converter "amanhã de tarde" em datas e horas ISO 8601 aproximadas (ex: 14:00 às 17:00).
3. Se ele disser "quero usar o forno amanhã" mas NÃO disser a hora, NÃO CHAME a ferramenta registrar_agendamento. Converse em linguagem natural e pergunte "Qual horário de início e fim?"
4. Só chame a ferramenta quando tiver o pacote completo.

[CONSULTA A PROCEDIMENTOS - RAG]
1. Se o usuário perguntar COMO FAZER um experimento, análise ou procedimento (ex: "como fazer análise de ferro?", "qual o método para titulação?"), use a ferramenta consultar_rag para buscar nos documentos do laboratório.
2. Se o usuário mencionar o nome de um método ou POP (ex: "método da fenantrolina", "POP-042"), também use consultar_rag.
3. Depois de receber o resultado do RAG, traduza em linguagem natural e pergunte se o usuário quer agendar os recursos necessários.
4. Para conversa fiada ou perguntas gerais (não sobre procedimentos), não chame a ferramenta, apenas responda."""

    # 🧠 RECUPERANDO A MEMÓRIA DO USUÁRIO
    if telegram_id not in memoria_conversas:
        memoria_conversas[telegram_id] = []
    
    # Adiciona a frase atual do usuário na memória
    memoria_conversas[telegram_id].append({"role": "user", "content": texto_usuario})
    
    # Limita a memória às últimas 6 interações (para não estourar o limite de tokens da API)
    if len(memoria_conversas[telegram_id]) > 6:
        memoria_conversas[telegram_id] = memoria_conversas[telegram_id][-6:]

    # Constrói o histórico final juntando o Sistema + Memória
    mensagens_para_ia: list[ChatCompletionMessageParam] = [{"role": "system", "content": prompt_sistema}] + memoria_conversas[telegram_id]

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

        if mensagem.tool_calls:
            tool_call = cast(ChatCompletionMessageToolCall, mensagem.tool_calls[0])
            return {
                "tipo": "funcao",
                "nome": tool_call.function.name,
                "args": json.loads(tool_call.function.arguments)
            }
        
        return {"tipo": "texto", "conteudo": mensagem.content}
        
    except Exception as e:
        print(f"Erro no LLM: {e}")
        return {"tipo": "erro", "conteudo": "Falha na comunicação neural."}


async def sintetizar_com_rag(
    pergunta_usuario: str,
    contexto_rag: str,
    telegram_id: int,
) -> str:
    """
    Envia o contexto dos documentos encontrados pelo RAG de volta ao LLM
    para que ele sintetize uma resposta em linguagem natural.

    Esta função NÃO expõe tools — é uma chamada de síntese pura,
    impossibilitando loop de ferramentas.

    Args:
        pergunta_usuario: A pergunta original do usuário.
        contexto_rag: Os documentos encontrados (saída de formatar_contexto_rag()).
        telegram_id: ID do usuário no Telegram (para recuperar memória).

    Returns:
        Resposta em linguagem natural (string formatada com HTML simples).
    """
    # ⏱️ INJEÇÃO DE TEMPO
    fuso = pytz.timezone("America/Fortaleza")
    agora = datetime.now(fuso)
    data_hora_atual = agora.strftime("%Y-%m-%d %H:%M")
    dia_semana = agora.strftime("%A")

    prompt_sintese = f"""Você é o Orion, IA de gestão do laboratório.
Data e hora exatas de agora: {data_hora_atual} ({dia_semana}).

Você recebeu documentos do banco de conhecimento do laboratório que são relevantes
para a pergunta do usuário.

INSTRUÇÕES:
1. Use APENAS as informações contidas nos documentos fornecidos abaixo.
2. Responda em LINGUAGEM NATURAL, de forma clara e concisa.
3. Seja didático(a) — explique o procedimento em etapas quando aplicável.
4. Ao final, pergunte educadamente se o usuário quer agendar os equipamentos ou recursos necessários.
5. Se os documentos não tiverem informação suficiente para responder, avise o usuário honestamente.
6. NÃO invente informações — USE APENAS o conteúdo dos documentos.
7. Use formatação HTML simples quando ajudar (negrito para termos importantes).

CONTEXTO DOS DOCUMENTOS ENCONTRADOS:
{contexto_rag}"""

    mensagens: list[ChatCompletionMessageParam] = [
        {"role": "system", "content": prompt_sintese},
        {"role": "user", "content": pergunta_usuario},
    ]

    try:
        response = await client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=mensagens,
            temperature=0.3,  # Sem tools — evita loop de chamadas
        )

        resposta = response.choices[0].message.content
        if not resposta:
            return "❌ Não consegui sintetizar uma resposta com os documentos encontrados."

        # Salva na memória de curto prazo para contexto futuro
        if telegram_id in memoria_conversas:
            memoria_conversas[telegram_id].append({"role": "assistant", "content": resposta})
            if len(memoria_conversas[telegram_id]) > 6:
                memoria_conversas[telegram_id] = memoria_conversas[telegram_id][-6:]

        return resposta

    except Exception as e:
        print(f"Erro no sintetizar_com_rag: {e}")
        return "❌ Ocorreu um erro ao processar os documentos. Tente novamente."


# ════════════════════════════════════════════════════════════════════
# LOOP DE FUNCTION CALLING (Sprint 6 — Orquestração Multi-Ferramenta)
# ════════════════════════════════════════════════════════════════════

PROMPT_ORQUESTRADOR = """Você é o Orion, IA de gestão do laboratório.
Data e hora exatas de agora: {data_hora} ({dia_semana}).

Você tem acesso a ferramentas que executam ações REAIS no sistema:
buscar_* (consulta inventário), registrar_agendamento (reserva),
consultar_rag (busca procedimentos), registrar_consumo / registrar_descarte /
registrar_reposicao (movimentação de estoque) e criar_protocolo_experimental.

REGRAS:
1. Use as ferramentas quantas vezes forem necessárias para completar a tarefa do usuário.
   Ex: se ele quer agendar um experimento, BUSQUE os recursos primeiro e só então registre as reservas.
2. Quando uma ferramenta retornar um resultado, ANALISE-O antes de decidir o próximo passo:
   - Se não encontrou o item, informe o usuário e pergunte o que ele quer fazer.
   - Se encontrou, use o resultado para a próxima chamada.
3. Antes de executar ações que alteram dados (reservar, dar baixa, descartar, repor, salvar protocolo),
   SEMPRE resuma o que você vai fazer e peça CONFIRMAÇÃO ao usuário.
4. Só chame registrar_agendamento com todas as informações completas (item + início + fim).
5. Responda em português, de forma clara e concisa.
6. Quando terminar de executar tudo, entregue um resumo final em linguagem natural."""


async def executar_loop_funcoes(
    texto_usuario: str,
    telegram_id: int,
    executor: dict,
    max_iteracoes: int = 5,
) -> dict:
    """
    Loop de function calling multi-turn.

    Fluxo:
        LLM decide chamar ferramenta(s) → executor executa cada uma →
        resultado volta ao LLM como mensagem de role "tool" →
        LLM analisa e decide: chama mais ferramentas OU responde texto final.

    Ações que ALTERAM dados (reserva, consumo, descarte, reposição, protocolo)
    são interceptadas: o LLM recebe "aguardando confirmação" e o usuário deve
    confirmar (ou recusar) antes da ação ser realmente executada.

    Args:
        texto_usuario: Mensagem do usuário.
        telegram_id: ID do usuário (memória curta).
        executor: Dict {nome_funcao: async def(args: dict, telegram_id: int) -> str}.
                  Quem fornece as implementações reais das ferramentas.
        max_iteracoes: Guarda anti-loop infinito.

    Returns:
        dict com "tipo": "texto" (resposta final) ou "erro".
    """
    fuso = pytz.timezone("America/Fortaleza")
    agora = datetime.now(fuso)
    data_hora_atual = agora.strftime("%Y-%m-%d %H:%M")
    dia_semana = agora.strftime("%A")

    prompt_sistema = PROMPT_ORQUESTRADOR.format(
        data_hora=data_hora_atual,
        dia_semana=dia_semana,
    )

    # Memória de curto prazo
    if telegram_id not in memoria_conversas:
        memoria_conversas[telegram_id] = []
    memoria_conversas[telegram_id].append({"role": "user", "content": texto_usuario})
    if len(memoria_conversas[telegram_id]) > 6:
        memoria_conversas[telegram_id] = memoria_conversas[telegram_id][-6:]

    # 🔐 Confirmação pendente: resolve ANTES de mandar a mensagem ao LLM
    pendencia = confirmacoes_pendentes.get(telegram_id)
    if pendencia:
        if _texto_negativo(texto_usuario):
            # Usuário recusou → cancela e informa o LLM
            confirmacoes_pendentes.pop(telegram_id, None)
            memoria_conversas[telegram_id][-1] = {
                "role": "user",
                "content": (
                    f"O usuário RECUSOU a ação {pendencia['nome']} que você propôs "
                    f"com os dados {json.dumps(pendencia['args'], ensure_ascii=False)}. "
                    f"Pergunte como ele quer prosseguir ou se deseja algo diferente."
                ),
            }
        elif _texto_afirmativo(texto_usuario):
            # Usuário confirmou → executa a ação pendente imediatamente
            confirmacoes_pendentes.pop(telegram_id, None)
            funcao = executor.get(pendencia["nome"])
            if funcao:
                try:
                    resultado = await funcao(pendencia["args"], telegram_id)
                except Exception as e:
                    print(f"Erro ao executar {pendencia['nome']}: {e}")
                    resultado = f"❌ Erro ao executar {pendencia['nome']}: {e}"
            else:
                resultado = (
                    f"⚠️ Ação confirmada, mas a ferramenta {pendencia['nome']} "
                    f"não está disponível agora."
                )

            memoria_conversas[telegram_id][-1] = {
                "role": "user",
                "content": (
                    f"[O usuário CONFIRMOU a ação {pendencia['nome']} com os dados "
                    f"{json.dumps(pendencia['args'], ensure_ascii=False)}. "
                    f"Resultado da execução: {resultado}]"
                ),
            }
        else:
            # Usuário mudou de assunto → mantém a pendência e deixa o LLM guiar
            memoria_conversas[telegram_id][-1] = {
                "role": "user",
                "content": (
                    f"{texto_usuario}\n\n"
                    f"[Ainda existe uma ação pendente de confirmação: {pendencia['nome']} "
                    f"com os dados {json.dumps(pendencia['args'], ensure_ascii=False)}. "
                    f"Se o usuário pedir outra coisa primeiro, execute; senão, retome a confirmação.]"
                ),
            }

    mensagens: list[ChatCompletionMessageParam] = [{"role": "system", "content": prompt_sistema}] + memoria_conversas[telegram_id]

    try:
        for _ in range(max_iteracoes):
            response = await client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=mensagens,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.0,
            )

            mensagem = response.choices[0].message

            # LLM pediu para chamar ferramentas?
            tool_calls = getattr(mensagem, "tool_calls", None)
            if tool_calls:
                # Guarda a intenção do LLM na conversa (obrigatório no protocolo)
                mensagens.append(cast(ChatCompletionMessageParam, mensagem.model_dump(exclude_none=True)))

                for tool_call in tool_calls:
                    nome = tool_call.function.name
                    try:
                        args = json.loads(tool_call.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}

                    # 🔐 AÇÕES MUTÁVEIS: exigem confirmação do usuário
                    if nome in ACOES_MUTAVEIS:
                        # Guarda a pendência e devolve ao LLM um aviso de confirmação
                        confirmacoes_pendentes[telegram_id] = {"nome": nome, "args": args}
                        resultado = (
                            f"⚠️ AÇÃO PENDENTE DE CONFIRMAÇÃO: antes de executar {nome}, "
                            f"pergunte ao usuário se ele confirma esta ação com os dados: {json.dumps(args, ensure_ascii=False)}. "
                            f"Não execute ainda. Aguarde a resposta (sim/não) do usuário."
                        )
                    else:
                        # Executa a ferramenta real (fornecida pelo handler)
                        funcao = executor.get(nome)
                        if not funcao:
                            resultado = f"❌ Ferramenta desconhecida: {nome}"
                        else:
                            try:
                                resultado = await funcao(args, telegram_id)
                            except Exception as e:
                                print(f"Erro ao executar {nome}: {e}")
                                resultado = f"❌ Erro ao executar {nome}: {e}"

                    # Devolve o resultado ao LLM no formato esperado
                    mensagens.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": resultado,
                    })
                continue  # Próxima iteração: LLM analisa os resultados

            # LLM respondeu texto final → acabou o loop
            resposta_final = mensagem.content
            if not resposta_final:
                return {"tipo": "erro", "conteudo": "A IA não conseguiu gerar uma resposta."}

            # Salva na memória
            memoria_conversas[telegram_id].append({"role": "assistant", "content": resposta_final})
            if len(memoria_conversas[telegram_id]) > 6:
                memoria_conversas[telegram_id] = memoria_conversas[telegram_id][-6:]

            return {"tipo": "texto", "conteudo": resposta_final}

        # Esgotou as iterações sem resposta final
        return {
            "tipo": "erro",
            "conteudo": "A sequência de ações ficou longa demais. Vamos por partes? Me diga o próximo passo.",
        }

    except Exception as e:
        print(f"Erro no executar_loop_funcoes: {e}")
        return {"tipo": "erro", "conteudo": "Falha na comunicação neural."}