# lida com manipulações e leitura de estoque
import uuid
import unicodedata
from sqlmodel import Session, select
from database.db import engine
from database.models import Item, Laboratorio, CategoriaItem

def normalizar_texto(texto: str) -> str:
    """Remove acentos, hífens e deixa tudo minúsculo para a busca."""
    if not texto:
        return ""
    # Remove os acentos da string
    texto_sem_acento = unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8')
    # Troca o hífen por espaço e deixa minúsculo
    return texto_sem_acento.replace("-", " ").lower()

def listar_itens(termo_busca: str | None = None, categoria: str | None = None):
    """Busca itens com filtro opcional de categoria, imune a acentos e hífens."""
    with Session(engine) as session:
        statement = select(Item, Laboratorio).join(Laboratorio, isouter=True)
        
        # Filtra a categoria direto no SQL (isso é rápido e exato)
        if categoria:
            statement = statement.where(Item.categoria == categoria)
            
        todos_itens = session.exec(statement).all()
        
        # Filtra o nome com Inteligência no Python
        if termo_busca:
            termo_limpo = normalizar_texto(termo_busca)
            resultados_filtrados = []
            
            for item, lab in todos_itens:
                nome_item_limpo = normalizar_texto(item.nome)
                
                # Se a palavra buscada estiver dentro do nome do item
                if termo_limpo in nome_item_limpo:
                    resultados_filtrados.append((item, lab))
                    
            # Limite para não explodir a mensagem no Telegram
            return resultados_filtrados[:15]
            
        return todos_itens[:15]
    
def formatar_mensagem_estoque(resultados, termo_busca: str | None = None) -> str:
    """Recebe a lista do banco de dados e transforma no texto final do Telegram."""
    if not resultados:
        if termo_busca:
            return f"🔍 Nenhum reagente encontrado para: <b>{termo_busca}</b>"
        return "O estoque está vazio no momento."

    if termo_busca:
        texto = f"<b>🧪 Resultados para '{termo_busca}':</b>\n\n"
    else:
        texto = "<b>📦 Visão Geral do Estoque:</b>\n<i>(Busque um item com /estoque nome)</i>\n\n"

    for item, lab in resultados:
        sigla_lab = lab.sigla if lab else "N/A"
        
        local = f" | 📍 {item.localizacao_exata}" if item.localizacao_exata else ""
        marca = f" | 🏷️ {item.marca}" if item.marca else ""
        lote = f" | Lote: {item.lote}" if item.lote else ""
        frascos = f" ({item.frascos} frascos/un)" if item.frascos else ""
        
        # Define um ícone visual baseado na categoria do item
        icone = "🔹"
        if item.categoria == "equipamento": icone = "⚙️"
        elif item.categoria == "vidraria": icone = "⚗️"
        elif item.categoria == "limpeza": icone = "🧹"
        elif item.categoria == "reagente": icone = "🧪"

        texto += f"{icone} <b>{item.nome}</b>\n"
        texto += f"  Qtd: {item.quantidade_atual} {item.unidade_medida}{frascos}\n"
        texto += f"  Lab: {sigla_lab}{local}{marca}{lote}\n"
        texto += f"  Estado: <i>{item.estado.value}</i>\n\n"
        
    return texto

def atualizar_quantidade(item_id: uuid.UUID, quantidade: float) -> bool:
    """Decrementa a quantidade atual de um item. Se zerar, marca como ESGOTADO."""
    from database.models import StatusItem
    with Session(engine) as session:
        item = session.get(Item, item_id)
        if not item:
            return False

        item.quantidade_atual = max(0.0, item.quantidade_atual - quantidade)

        if item.quantidade_atual <= 0:
            item.estado = StatusItem.ESGOTADO

        session.commit()
        return True

def editar_item(item_id: uuid.UUID, dados_atualizacao: dict) -> bool:
    """Atualiza dinamicamente os campos de um item com base nas regras da categoria."""
    from services.schemas_estoque import get_edit_schema
    with Session(engine) as session:
        item = session.get(Item, item_id)
        if not item:
            return False

        # Valida os dados usando o schema adequado para a categoria do item
        schema_class = get_edit_schema(item.categoria)
        
        # Filtra e valida via Pydantic
        try:
            dados_validados = schema_class(**dados_atualizacao)
        except Exception:
            return False

        # Aplica apenas os campos que foram enviados (não None)
        atualizacoes = dados_validados.model_dump(exclude_unset=True)
        for chave, valor in atualizacoes.items():
            setattr(item, chave, valor)

        session.add(item)
        session.commit()
        return True

def cadastrar_novo_item(
    nome: str,
    categoria: str,
    quantidade_inicial: float,
    unidade_medida: str,
    laboratorio_sigla: str | None = None,
    bancada: str | None = None,
    complemento: str | None = None,
    marca: str | None = None,
    lote: str | None = None,
    validade: str | None = None,
    frascos: int | None = None,
    estado: str = "Bom",
) -> Item:
    """
    Cadastra um novo item unificado no inventário do laboratório.
    Suporta reagentes, equipamentos, vidrarias e insumos de limpeza.
    A localização exata é composta por bancada e complemento (ex: 'Bancada 01 (do lado da pia)').
    """
    from datetime import datetime
    from database.models import StatusItem

    # Normalização da Categoria
    cat_lower = (categoria or "").lower().strip()
    if "reag" in cat_lower:
        cat_enum = CategoriaItem.REAGENTE
    elif "equip" in cat_lower:
        cat_enum = CategoriaItem.EQUIPAMENTO
    elif "vidr" in cat_lower:
        cat_enum = CategoriaItem.VIDRARIA
    elif "limp" in cat_lower:
        cat_enum = CategoriaItem.LIMPEZA
    else:
        cat_enum = CategoriaItem.REAGENTE

    # Normalização do Status/Estado
    est_lower = (estado or "").lower().strip()
    if "uso" in est_lower:
        est_enum = StatusItem.EM_USO
    elif "manut" in est_lower or "calibr" in est_lower:
        est_enum = StatusItem.REQUER_MANUTENCAO
    elif "quebr" in est_lower:
        est_enum = StatusItem.QUEBRADO
    elif "esgot" in est_lower:
        est_enum = StatusItem.ESGOTADO
    else:
        est_enum = StatusItem.BOM

    # Composição da localização detalhada: bancada + complemento
    bancada_str = (bancada or "").strip()
    comp_str = (complemento or "").strip()
    if bancada_str and comp_str:
        localizacao = f"{bancada_str} ({comp_str})"
    elif bancada_str:
        localizacao = bancada_str
    elif comp_str:
        localizacao = comp_str
    else:
        localizacao = None

    # Parsing de validade se fornecida
    dt_validade = None
    if validade:
        if isinstance(validade, datetime):
            dt_validade = validade
        elif isinstance(validade, str) and validade.strip() and validade.strip() != "—":
            val_clean = validade.strip()
            for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y/%m/%d"):
                try:
                    dt_validade = datetime.strptime(val_clean, fmt)
                    break
                except ValueError:
                    continue

    with Session(engine) as session:
        lab_id = None
        if laboratorio_sigla and laboratorio_sigla.strip() and laboratorio_sigla.strip().lower() != "todos":
            lab_busca = laboratorio_sigla.strip()
            lab_existente = session.exec(
                select(Laboratorio).where(
                    (Laboratorio.sigla.ilike(lab_busca)) | (Laboratorio.nome.ilike(lab_busca))
                )
            ).first()
            if lab_existente:
                lab_id = lab_existente.id
            else:
                novo_lab = Laboratorio(nome=lab_busca.upper(), sigla=lab_busca.upper())
                session.add(novo_lab)
                session.commit()
                session.refresh(novo_lab)
                lab_id = novo_lab.id

        novo_item = Item(
            nome=nome.strip(),
            categoria=cat_enum,
            quantidade_atual=max(0.0, float(quantidade_inicial)),
            unidade_medida=unidade_medida.strip() if unidade_medida else "un",
            frascos=int(frascos) if frascos is not None and str(frascos).isdigit() else None,
            laboratorio_id=lab_id,
            localizacao_exata=localizacao,
            marca=marca.strip() if marca and marca.strip() != "—" else None,
            lote=lote.strip() if lote and lote.strip() != "—" else None,
            validade=dt_validade,
            estado=est_enum,
        )
        session.add(novo_item)
        session.commit()
        session.refresh(novo_item)
        return novo_item