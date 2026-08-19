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