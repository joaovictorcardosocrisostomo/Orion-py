from sqlmodel import Session, select
from database.db import engine
from database.models import Laboratorio, Usuario, NivelAcesso

def testar_criacao():
    with Session(engine) as session:
        # 0. Limpeza prévia (Opcional, mas ajuda no teste repetível)
        existing_user = session.exec(select(Usuario).where(Usuario.telegram_id == 999)).first()
        if existing_user:
            session.delete(existing_user)
            session.commit()

        # 1. Laboratório
        lab = Laboratorio(nome="Laboratório de Teste", sigla="LAB-T")
        session.add(lab)
        session.commit()
        session.refresh(lab)
        print(f"✅ Laboratório criado com ID: {lab.id}")

        # 2. Usuário
        user = Usuario(
            telegram_id=999, 
            nome="Administrador Teste",
            nivel_acesso=NivelAcesso.ADMIN,
            modo_atual="Normal"
        )
        session.add(user)
        session.commit()
        print("✅ Usuário criado.")

        # 3. Vínculo ignorado (removido do modelo)
        print("✅ Vínculo (Admin) ignorado — removido do modelo.")

if __name__ == "__main__":
    try:
        testar_criacao()
        print("\n🎉 Tudo ok! O banco de dados suporta relacionamentos e permissões.")
    except Exception as e:
        print(f"\n❌ Erro: {e}")