from sqlmodel import Session
from database.db import engine
from database.models import Usuario, NivelAcesso

def salvar_usuario(telegram_id: int, nome: str, nivel: NivelAcesso) -> Usuario:
    """Cria um novo usuário ou atualiza os dados se já existir (Upsert)."""
    with Session(engine) as session:
        usuario = session.get(Usuario, telegram_id)
        
        if not usuario:
            # Usuário novo
            usuario = Usuario(telegram_id=telegram_id, nome=nome, nivel_acesso=nivel)
            session.add(usuario)
        else:
            # Usuário editando o perfil
            usuario.nome = nome
            usuario.nivel_acesso = nivel
            
        session.commit()
        session.refresh(usuario)
        return usuario

def buscar_usuario(telegram_id: int) -> Usuario:
    """Busca um usuário no banco para checar se ele já existe."""
    with Session(engine) as session:
        return session.get(Usuario, telegram_id)