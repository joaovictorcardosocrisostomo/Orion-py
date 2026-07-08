# lida com manipulações e leitura de estoque
from sqlmodel import Session, select
from database.db import engine
from database.models import Item, Laboratorio, CategoriaItem

def listar_itens(termo_busca: str = None, categoria: str = None):
    """Busca itens com filtro opcional de categoria."""
    with Session(engine) as session:
        statement = select(Item, Laboratorio).join(Laboratorio, isouter=True)
        
        if termo_busca:
            statement = statement.where(Item.nome.ilike(f"%{termo_busca}%"))
            
        if categoria:
            statement = statement.where(Item.categoria == categoria)
            
        # Limite para não explodir a mensagem no Telegram
        statement = statement.limit(15)
        
        return session.exec(statement).all()
    
def formatar_mensagem_estoque(resultados, termo_busca: str = None) -> str:
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