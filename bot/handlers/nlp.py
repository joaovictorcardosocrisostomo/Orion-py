from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import StateFilter
from datetime import datetime
from services.llm import executar_loop_funcoes, sintetizar_com_rag
from services.estoque import listar_itens, formatar_mensagem_estoque, atualizar_quantidade
from services.agendamento import criar_reserva
from services.rag import formatar_contexto_rag, listar_todos_procedimentos
from services.log_uso import registrar_log_uso
from services.protocolo import criar_protocolo_experimental, formatar_protocolo
from services.scheduler import agendar_alarme_inicio
from database.models import StatusItem
from bot.apresentacao import eh_pergunta_apresentacao, MENSAGEM_APRESENTACAO
from bot.telegram_helpers import responder_com_seguranca

router = Router()


# ════════════════════════════════════════════════════════════════════
# IMPLEMENTAÇÕES REAIS DAS FERRAMENTAS (executor do loop de tools)
# Cada função recebe (args: dict, telegram_id: int) e retorna str.
# ════════════════════════════════════════════════════════════════════

def _buscar_item_por_termo(termo: str, categoria: str | None = None):
    """Busca um item no estoque. Retorna (item, lab) ou None."""
    resultados = listar_itens(termo_busca=termo, categoria=categoria)
    if not resultados:
        return None
    return resultados[0]


async def _tool_buscar(termo: str, categoria: str) -> str:
    """Consulta genérica de estoque (reagente/equipamento/vidraria/limpeza)."""
    resultados = listar_itens(termo_busca=termo, categoria=categoria)
    return formatar_mensagem_estoque(resultados, termo)


async def executor_buscar_reagente(args: dict, telegram_id: int) -> str:
    return await _tool_buscar(args.get("termo", ""), "reagente")


async def executor_buscar_equipamento(args: dict, telegram_id: int) -> str:
    return await _tool_buscar(args.get("termo", ""), "equipamento")


async def executor_buscar_vidraria(args: dict, telegram_id: int) -> str:
    return await _tool_buscar(args.get("termo", ""), "vidraria")


async def executor_buscar_limpeza(args: dict, telegram_id: int) -> str:
    return await _tool_buscar(args.get("termo", ""), "limpeza")


async def executor_registrar_agendamento(args: dict, telegram_id: int) -> str:
    termo = args.get("termo_equipamento", "")
    inicio_str = args.get("data_inicio_iso", "")
    fim_str = args.get("data_fim_iso", "")

    if not all([termo, inicio_str, fim_str]):
        return "❌ Faltam informações para agendar (item, data de início e fim)."

    try:
        dt_inicio = datetime.strptime(inicio_str, "%Y-%m-%d %H:%M")
        dt_fim = datetime.strptime(fim_str, "%Y-%m-%d %H:%M")
    except ValueError:
        return "❌ Não consegui entender o formato das datas. Use: YYYY-MM-DD HH:MM."

    encontrado = _buscar_item_por_termo(termo, "equipamento")
    if not encontrado:
        # Tenta sem filtro de categoria (pode ser vidraria etc.)
        encontrado = _buscar_item_por_termo(termo)
    if not encontrado:
        return f"❌ Não encontrei nenhum item parecido com '{termo}' no sistema."

    item_obj = encontrado[0]
    resposta_db = criar_reserva(
        telegram_id=telegram_id,
        item_id=item_obj.id,
        data_inicio=dt_inicio,
        data_fim=dt_fim,
    )

    if resposta_db["sucesso"]:
        agendar_alarme_inicio(
            dt_inicio,
            telegram_id,
            resposta_db["item_nome"],
            resposta_db["reserva"].id,
        )
        return (
            f"✅ Reserva confirmada!\n"
            f"Item: {resposta_db['item_nome']}\n"
            f"Início: {dt_inicio.strftime('%d/%m/%Y às %H:%M')}\n"
            f"Término: {dt_fim.strftime('%d/%m/%Y às %H:%M')}"
        )
    return f"❌ Erro na reserva: {resposta_db['erro']}"


async def executor_consultar_rag(args: dict, telegram_id: int) -> str:
    termo = args.get("termo_busca", "")
    if not termo:
        return "Sobre qual procedimento você quer saber?"

    contexto = formatar_contexto_rag(termo, limite=2)
    if not contexto:
        return (
            f"🔍 Não encontrei nenhum procedimento relacionado a '{termo}' "
            f"no banco de conhecimento do laboratório."
        )

    # Retorna o contexto extraído dos POPs diretamente para o orquestrador sintetizar,
    # eliminando a chamada intermediária redundante de IA (economiza mais de 3.000 tokens)
    return contexto


async def executor_listar_procedimentos(args: dict, telegram_id: int) -> str:
    """Lista todos os POPs e protocolos realmente cadastrados no banco de dados."""
    from sqlmodel import Session, select
    from database.db import engine
    from database.models import ProtocoloExperimental

    pops = listar_todos_procedimentos()
    with Session(engine) as session:
        protocolos = session.exec(select(ProtocoloExperimental)).all()

    if not pops and not protocolos:
        return "📚 Não há nenhum POP ou protocolo cadastrado no banco de conhecimento no momento. Use o comando /adicionar_pop para cadastrar um novo documento."

    linhas = ["📚 <b>Documentos e POPs cadastrados no laboratório:</b>\n"]
    if pops:
        linhas.append("<b>Procedimentos Operacionais Padrão (POPs):</b>")
        for p in pops:
            linhas.append(f"• 📄 <b>{p['titulo']}</b>")
        linhas.append("")

    if protocolos:
        linhas.append("<b>Protocolos Experimentais:</b>")
        for proto in protocolos:
            linhas.append(f"• 📋 <b>{proto.titulo}</b> (v{proto.versao})")

    linhas.append("\nPara consultar o passo a passo ou reagentes de qualquer um deles, me diga o nome do procedimento!")
    return "\n".join(linhas)


async def _tool_movimentar_estoque(
    args: dict,
    telegram_id: int,
    observacoes: str,
    estado: StatusItem,
    reposicao: bool = False,
) -> str:
    """Base comum para consumo / descarte / reposição."""
    termo = args.get("termo_item", "")
    quantidade = float(args.get("quantidade", 0) or 0)

    if not termo:
        return "❌ Preciso do nome do item para executar esta ação."

    encontrado = _buscar_item_por_termo(termo)
    if not encontrado:
        return f"❌ Não encontrei nenhum item parecido com '{termo}' no sistema."

    item_obj = encontrado[0]

    if quantidade > 0:
        atualizar_quantidade(item_obj.id, quantidade)

    log, nome_item = registrar_log_uso(
        usuario_id=telegram_id,
        item_id=item_obj.id,
        quantidade=quantidade,
        estado=estado,
        observacoes=observacoes or None,
        reposicao_necessaria=reposicao,
    )
    return (
        f"✅ Registrado!\n"
        f"Item: {nome_item}\n"
        f"Quantidade: {quantidade} {item_obj.unidade_medida}\n"
        f"Observação: {observacoes or '—'}"
    )


async def executor_registrar_consumo(args: dict, telegram_id: int) -> str:
    qtd = args.get("quantidade", 0)
    obs = f"Consumo: {qtd} {args.get('unidade', '')}".strip()
    return await _tool_movimentar_estoque(
        args, telegram_id,
        observacoes=obs if qtd else "Uso registrado (sem consumo)",
        estado=StatusItem.BOM,
    )


async def executor_registrar_descarte(args: dict, telegram_id: int) -> str:
    motivo = args.get("motivo", "Descarte registrado")
    return await _tool_movimentar_estoque(
        args, telegram_id,
        observacoes=f"Descartado: {motivo}",
        estado=StatusItem.QUEBRADO,
    )


async def executor_registrar_reposicao(args: dict, telegram_id: int) -> str:
    qtd_necessaria = args.get("quantidade_necessaria", 0)
    return await _tool_movimentar_estoque(
        args, telegram_id,
        observacoes=f"Precisa repor {qtd_necessaria} (verificar quantidade disponível)",
        estado=StatusItem.BOM,
        reposicao=True,
    )


async def executor_criar_protocolo_experimental(args: dict, telegram_id: int) -> str:
    titulo = args.get("titulo", "")
    etapas = args.get("etapas", "")
    if not titulo or not etapas:
        return "❌ Preciso de título e etapas para salvar o protocolo."

    protocolo = criar_protocolo_experimental(
        titulo=titulo,
        descricao=args.get("descricao"),
        etapas=etapas,
        recursos=args.get("recursos"),
        duracao_estimada_min=args.get("duracao_estimada_min"),
        criado_por=telegram_id,
    )
    return (
        f"✅ Protocolo salvo!\n"
        f"{formatar_protocolo(protocolo)}"
    )


async def executor_cadastrar_item(args: dict, telegram_id: int) -> str:
    """Executa o cadastro de um novo item no estoque através de function calling."""
    from services.estoque import cadastrar_novo_item

    nome = args.get("nome", "").strip()
    categoria = args.get("categoria", "reagente")
    qtd = args.get("quantidade", 0)
    unidade = args.get("unidade_medida", "un")
    lab = args.get("laboratorio", "LAT")
    bancada = args.get("bancada")
    complemento = args.get("complemento_local") or args.get("complemento")
    marca = args.get("marca")
    lote = args.get("lote")
    validade = args.get("validade")
    frascos = args.get("frascos")

    if not nome:
        return "❌ O nome do item é obrigatório para cadastrá-lo."

    try:
        qtd_num = float(qtd)
    except (ValueError, TypeError):
        return f"❌ Quantidade inválida: '{qtd}'. Informe um número válido."

    try:
        item = cadastrar_novo_item(
            nome=nome,
            categoria=categoria,
            quantidade_inicial=qtd_num,
            unidade_medida=unidade,
            laboratorio_sigla=lab,
            bancada=bancada,
            complemento=complemento,
            marca=marca,
            lote=lote,
            validade=validade,
            frascos=frascos,
            estado="Bom",
        )

        local_formatado = item.localizacao_exata if item.localizacao_exata else "Não especificada"
        lab_sigla = lab.upper() if lab else "LAT"

        linhas = [
            f"✅ <b>Item cadastrado com sucesso no inventário!</b>\n",
            f"📦 <b>Nome:</b> {item.nome}",
            f"🏷️ <b>Categoria:</b> {item.categoria.value if hasattr(item.categoria, 'value') else item.categoria}",
            f"⚖️ <b>Quantidade:</b> {item.quantidade_atual} {item.unidade_medida}",
            f"🏢 <b>Laboratório:</b> {lab_sigla}",
            f"📍 <b>Localização:</b> {local_formatado}",
        ]
        if item.frascos:
            linhas.append(f"🧪 <b>Frascos:</b> {item.frascos}")
        if item.marca:
            linhas.append(f"🏭 <b>Marca:</b> {item.marca}")
        if item.lote:
            linhas.append(f"🔢 <b>Lote:</b> {item.lote}")
        if item.validade:
            linhas.append(f"📅 <b>Validade:</b> {item.validade.strftime('%d/%m/%Y')}")

        return "\n".join(linhas)
    except Exception as e:
        return f"❌ Erro ao cadastrar item no banco de dados: {str(e)}"


# ════════════════════════════════════════════════════════════════════
# EXECUTOR — mapeia o nome da tool para a implementação real
# ════════════════════════════════════════════════════════════════════
EXECUTOR = {
    "buscar_reagente": executor_buscar_reagente,
    "buscar_equipamento": executor_buscar_equipamento,
    "buscar_vidraria": executor_buscar_vidraria,
    "buscar_limpeza": executor_buscar_limpeza,
    "registrar_agendamento": executor_registrar_agendamento,
    "consultar_rag": executor_consultar_rag,
    "listar_procedimentos": executor_listar_procedimentos,
    "cadastrar_item": executor_cadastrar_item,
    "registrar_consumo": executor_registrar_consumo,
    "registrar_descarte": executor_registrar_descarte,
    "registrar_reposicao": executor_registrar_reposicao,
    "criar_protocolo_experimental": executor_criar_protocolo_experimental,
}


@router.message(StateFilter(None), F.text & ~F.text.startswith('/'))
async def chat_natural(message: Message):
    if message.bot is None or message.from_user is None or message.text is None:
        return

    # Se o usuário perguntar o que o bot é capaz de fazer / suas funções
    if eh_pergunta_apresentacao(message.text):
        await message.answer(MENSAGEM_APRESENTACAO, parse_mode="HTML")
        return

    # Se o usuário pedir o dashboard diretamente sem a barra
    texto_limpo = message.text.lower().strip()
    if texto_limpo in {"dashboard", "painel", "abrir dashboard", "abrir painel", "ver dashboard", "ver painel", "link dashboard", "link do dashboard"}:
        from bot.handlers.dashboard import cmd_dashboard
        await cmd_dashboard(message)
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    # O loop de function calling resolve a tarefa em múltiplas rodadas:
    # LLM chama tools → executor executa → resultado volta ao LLM → continua.
    resultado = await executar_loop_funcoes(
        texto_usuario=message.text,
        telegram_id=message.from_user.id,
        executor=EXECUTOR,
    )

    conteudo = resultado.get("conteudo") or "Tive um problema ao processar seu pedido."
    await responder_com_seguranca(message, conteudo)