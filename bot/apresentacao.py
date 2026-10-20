import re
import unicodedata

MENSAGEM_APRESENTACAO = """🌌 <b>Olá! Eu sou o Orion</b>, assistente inteligente do laboratório.

Fui projetado para organizar o dia a dia da equipe no laboratório, cuidando do inventário, agendamentos, procedimentos e relatórios. Você pode conversar comigo em <b>linguagem natural</b> (basta me pedir o que precisa) ou usar os comandos rápidos:

📦 <b>Gestão de Estoque & Inventário</b>
• <b>Consultar itens:</b> <code>/estoque [termo]</code> ou me pergunte <i>"temos acetona no estoque?"</i>.
• <b>Cadastrar novos itens:</b> <code>/adicionar_item</code> ou me diga <i>"chegou 500g de sulfato da Synth no LAT na bancada 1"</i>.
• <b>Editar itens:</b> <code>/editar_item [nome]</code> para alterar quantidade, local, lote ou marca.
• <b>Movimentações:</b> Diga <i>"gastei 50ml de HCl"</i> (baixa) ou <i>"quebrou um béquer de 250ml"</i> (descarte).

🗓️ <b>Agendamento & Experimentos</b>
• <b>Painel do dia:</b> <code>/hoje</code> para ver suas reservas e experimentos agendados.
• <b>Planejar experimento:</b> <code>/experimento</code> para planejar rotinas com múltiplos recursos.
• <b>Reservar por conversa:</b> Diga <i>"reserva o espectrofotômetro amanhã das 14h às 16h"</i>.
• <b>Controle de bancada:</b> Alertas de fim de uso com opção de estender (+30min) ou finalizar.

📋 <b>Auditoria & Relatórios</b>
• <b>Relatório de uso:</b> <code>/relatorio</code> para registrar uso e apontar avarias ou quebras.
• <b>Auditoria noturna:</b> Questionário automático às 18h para atualizar o consumo do dia.

📚 <b>POPs & Base de Conhecimento (RAG)</b>
• <b>Consultar métodos:</b> Pergunte <i>"como fazer análise de ferro?"</i> para buscar em nossos POPs.
• <b>Acervo de POPs:</b> <code>/pops</code> para listar todos os procedimentos reais indexados.
• <b>Cadastrar novo POP:</b> <code>/adicionar_pop</code> para enviar arquivos PDF/DOCX para a base.

📊 <b>Painel Geral & MiniApp</b>
• <code>/dashboard</code>: Indicadores em tempo real e atalho para o <b>Telegram MiniApp</b> ou Web.

💡 <i>Dica: Você não precisa memorizar comandos! Pode conversar comigo naturalmente como falaria com um colega de laboratório.</i>"""


def _normalizar(texto: str) -> str:
    """Remove acentos, pontuação e converte para minúsculas para comparação flexível."""
    if not texto:
        return ""
    texto_limpo = unicodedata.normalize("NFKD", texto).encode("ASCII", "ignore").decode("utf-8")
    texto_limpo = re.sub(r"[^\w\s]", " ", texto_limpo)
    return " ".join(texto_limpo.lower().split())


PADROES_APRESENTACAO = [
    r"o que (voce|o bot|o orion) (e capaz de fazer|pode fazer|faz|sabe fazer)",
    r"o que (voce|o bot|o orion) faz",
    r"quais (sao|as) suas (funcoes|habilidades|capacidades|recursos)",
    r"quais suas (funcoes|habilidades|capacidades|recursos)",
    r"como (voce|o bot|o orion) pode me ajudar",
    r"como (voce|o bot|o orion) funciona",
    r"quem e (voce|o orion)",
    r"para que (voce|o bot|o orion) serve",
    r"o que posso fazer (aqui|com voce)",
    r"quais sao os comandos",
    r"quais comandos existem",
    r"me ajuda",
    r"^ajuda$",
    r"^help$",
    r"^funcoes$",
    r"^comandos$",
]

_REGEX_APRESENTACAO = re.compile("|".join(PADROES_APRESENTACAO), re.IGNORECASE)


def eh_pergunta_apresentacao(texto: str) -> bool:
    """Verifica se o usuário está perguntando sobre as capacidades ou funções do bot."""
    if not texto:
        return False
    texto_norm = _normalizar(texto)
    return bool(_REGEX_APRESENTACAO.search(texto_norm))
