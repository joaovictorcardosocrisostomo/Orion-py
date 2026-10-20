import re
import logging
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest


TAGS_PERMITIDAS_TELEGRAM = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "tg-spoiler", "a", "code", "pre", "blockquote"
}

MAPA_SUPERSCRIPT = {
    '0': '⁰', '1': '¹', '2': '²', '3': '³', '4': '⁴',
    '5': '⁵', '6': '⁶', '7': '⁷', '8': '⁸', '9': '⁹',
    '+': '⁺', '-': '⁻', '=': '⁼', '(': '⁽', ')': '⁾',
    'n': 'ⁿ', 'x': 'ˣ'
}

MAPA_SUBSCRIPT = {
    '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
    '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉',
    '+': '₊', '-': '₋', '=': '₌', '(': '₍', ')': '₎'
}


def converter_latex_para_unicode(texto: str) -> str:
    """Converte notação matemática/química de LaTeX para texto legível com Unicode."""
    if not texto:
        return ""

    s = texto

    # 1. Trata blocos de equações \[ ... \] e \( ... \)
    s = re.sub(r"\\\[\s*(.*?)\s*\\\]", r"\n<code>\1</code>\n", s, flags=re.DOTALL)
    s = re.sub(r"\\\(\s*(.*?)\s*\\\)", r"\1", s, flags=re.DOTALL)

    # 2. Remove comandos de estilo de texto do LaTeX
    s = re.sub(r"\\(?:text|mathrm|mathbf|mathit|textbf){([^}]+)}", r"\1", s)

    # 3. Converte setas e operadores químicos/matemáticos
    s = re.sub(r"\\(?:rightleftharpoons|leftrightarrows)", "⇌", s)
    s = re.sub(r"\\(?:rightarrow|to)", "→", s)
    s = re.sub(r"\\(?:leftarrow)", "←", s)
    s = re.sub(r"\\(?:cdot|bullet)", "·", s)
    s = re.sub(r"\\(?:times)", "×", s)
    s = re.sub(r"\\(?:pm)", "±", s)
    s = re.sub(r"\\(?:approx)", "≈", s)
    s = re.sub(r"\\(?:leq|le)", "≤", s)
    s = re.sub(r"\\(?:geq|ge)", "≥", s)
    s = re.sub(r"\\(?:neq|ne)", "≠", s)
    s = re.sub(r"\\(?:Delta)", "Δ", s)
    s = re.sub(r"\\(?:mu)", "µ", s)
    s = re.sub(r"\\(?:alpha)", "α", s)
    s = re.sub(r"\\(?:beta)", "β", s)
    s = re.sub(r"\\(?:gamma)", "γ", s)
    s = re.sub(r"\\(?:lambda)", "λ", s)
    s = re.sub(r"\\(?:circ|degree)", "°", s)

    # 4. Trata subíndices compostos como H_{2(g)} -> H₂(g)
    def _rep_sub_fase(m: re.Match) -> str:
        num = "".join(MAPA_SUBSCRIPT.get(c, c) for c in m.group(1))
        fase = m.group(2)
        return f"{num}({fase})"
    s = re.sub(r"_{([0-9]+)\(([a-zA-Z]+)\)}", _rep_sub_fase, s)

    # 5. Sobrescritos e subscritos numéricos / cargas
    def _rep_sup(m: re.Match) -> str:
        return "".join(MAPA_SUPERSCRIPT.get(c, c) for c in m.group(1))

    def _rep_sub(m: re.Match) -> str:
        return "".join(MAPA_SUBSCRIPT.get(c, c) for c in m.group(1))

    s = re.sub(r"\^{([^}]+)}", _rep_sup, s)
    s = re.sub(r"\^([0-9\+\-])", _rep_sup, s)
    s = re.sub(r"_{([0-9\+\-]+)}", _rep_sub, s)
    s = re.sub(r"_([0-9])", _rep_sub, s)

    # 6. Limpa chaves soltas restantes de agrupamentos LaTeX (ex: {Al})
    s = re.sub(r"{([a-zA-Z0-9\(\)]+)}", r"\1", s)

    return s


def converter_markdown_para_html(texto: str) -> str:
    """Converte formatação Markdown padrão para tags HTML suportadas pelo Telegram."""
    if not texto:
        return ""

    s = texto

    # Blocos de código ```linguagem\nconteúdo\n```
    s = re.sub(
        r"```(?:[a-zA-Z0-9_-]+)?\n(.*?)\n```",
        r"<pre><code>\1</code></pre>",
        s,
        flags=re.DOTALL
    )

    # Código inline `código`
    s = re.sub(r"`([^`\n]+)`", r"<code>\1</code>", s)

    # Cabeçalhos #, ##, ### -> <b>Título</b>
    s = re.sub(r"^(?:#{1,6})\s+(.*?)$", r"<b>\1</b>\n", s, flags=re.MULTILINE)

    # Negrito **texto** ou __texto__
    s = re.sub(r"\*\*([^\*\n]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"__([^_\n]+)__", r"<b>\1</b>", s)

    # Itálico *texto* ou _texto_ (evitando listas com asterisco)
    s = re.sub(r"(?<!\*|\w)\*([^\*\s\n][^\*\n]*[^\*\s\n])\*(?!\*|\w)", r"<i>\1</i>", s)
    s = re.sub(r"(?<!_|\w)_([^_\s\n][^_\n]*[^_\s\n])_(?!_|\w)", r"<i>\1</i>", s)

    # Tachado ~~texto~~
    s = re.sub(r"~~([^~\n]+)~~", r"<s>\1</s>", s)

    # Citações de bloco > texto
    s = re.sub(r"^>\s*(.*?)$", r"<blockquote>\1</blockquote>", s, flags=re.MULTILINE)

    return s


def sanitizar_html_telegram(texto: str) -> str:
    """Pipeline completo de normalização: LaTeX -> Markdown -> HTML do Telegram."""
    if not texto:
        return ""

    # 1. Converte equações e fórmulas LaTeX em Unicode limpo
    s = converter_latex_para_unicode(texto)

    # 2. Converte Markdown comum (**negrito**, `código`) para HTML
    s = converter_markdown_para_html(s)

    # 3. Trata quebras de linha e estruturas de bloco comuns
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<hr\s*/?>", "\n---\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<li>", "\n• ", s, flags=re.IGNORECASE)
    s = re.sub(r"</li>", "", s, flags=re.IGNORECASE)
    s = re.sub(r"</p>", "\n\n", s, flags=re.IGNORECASE)
    s = re.sub(r"<p>", "\n", s, flags=re.IGNORECASE)
    s = re.sub(r"&nbsp;", " ", s, flags=re.IGNORECASE)

    # 4. Converte tags de cabeçalho h1-h6 residuais para negrito
    s = re.sub(r"<h[1-6][^>]*>(.*?)</h[1-6]>", r"\n<b>\1</b>\n", s, flags=re.IGNORECASE | re.DOTALL)

    # 5. Protege APENAS as tags HTML válidas suportadas pelo Telegram
    tags_salvas: list[str] = []

    def _proteger_tag(match: re.Match) -> str:
        tag = match.group(0)
        # Se for link <a> sem href, descarta
        if tag.lower().startswith("<a") and not tag.startswith("</") and 'href=' not in tag.lower():
            return ""
        tags_salvas.append(tag)
        return f"\x00TG_TAG_{len(tags_salvas) - 1}\x00"

    padrao_tags = re.compile(
        r"</?(?:b|strong|i|em|u|ins|s|strike|del|tg-spoiler|code|pre|blockquote)\b[^>]*>|"
        r"<a\s+href=[\"'][^\"']*[\"'][^>]*>|</a\s*>",
        flags=re.IGNORECASE,
    )
    s = padrao_tags.sub(_proteger_tag, s)

    # 6. Remove quaisquer outras tags HTML remanescentes (ex: <div>, <span>, etc.)
    s = re.sub(r"</?[a-zA-Z][a-zA-Z0-9_-]*(?:\s+[^>]*)?>", "", s)

    # 7. Escapa caracteres reservados do Telegram HTML (&, <, >) no texto restante
    s = re.sub(r"&(?!amp;|lt;|gt;)", "&amp;", s)
    s = s.replace("<", "&lt;").replace(">", "&gt;")

    # 8. Restaura as tags permitidas que foram protegidas
    for i, tag in enumerate(tags_salvas):
        s = s.replace(f"\x00TG_TAG_{i}\x00", tag)

    # 9. Normaliza múltiplos saltos de linha desnecessários
    s = re.sub(r"\n{3,}", "\n\n", s)

    return s.strip()


def dividir_em_pedacos(texto: str, max_tamanho: int = 3900) -> list[str]:
    """Divide um texto em blocos de até max_tamanho caracteres, preservando linhas."""
    if not texto or len(texto) <= max_tamanho:
        return [texto] if texto else []

    pedacos: list[str] = []
    linhas = texto.splitlines(keepends=True)
    buffer = ""

    for linha in linhas:
        if len(buffer) + len(linha) <= max_tamanho:
            buffer += linha
        else:
            if buffer:
                pedacos.append(buffer.strip())
                buffer = ""
            while len(linha) > max_tamanho:
                pedacos.append(linha[:max_tamanho].strip())
                linha = linha[max_tamanho:]
            buffer = linha

    if buffer and buffer.strip():
        pedacos.append(buffer.strip())

    return pedacos


async def responder_com_seguranca(message: Message, conteudo: str) -> None:
    """Envia resposta via Telegram de forma à prova de falhas com suporte completo a Markdown e LaTeX."""
    if not conteudo:
        return

    conteudo_sanitizado = sanitizar_html_telegram(conteudo)
    pedacos = dividir_em_pedacos(conteudo_sanitizado, max_tamanho=3900)

    for pedaco in pedacos:
        if not pedaco:
            continue
        try:
            await message.answer(pedaco, parse_mode="HTML")
        except TelegramBadRequest as e:
            logging.warning(
                f"Telegram rejeitou envio HTML ({e.message}). "
                f"Enviando bloco em texto plano como fallback seguro."
            )
            # Remove todas as tags residuais para texto puro
            texto_puro = re.sub(r"<[^>]+>", "", pedaco)
            sub_pedacos = dividir_em_pedacos(texto_puro, max_tamanho=3900)
            for sp in sub_pedacos:
                if sp:
                    await message.answer(sp)
