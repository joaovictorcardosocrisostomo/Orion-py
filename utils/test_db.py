from sqlmodel import Session
from database.db import engine
from database.models import Laboratorio, Usuario, UsuarioLaboratorio, Role

def testar_criacao():
    with Session(engine) as session:
        # 1. Laboratório
        lab = Laboratorio(nome="Laboratório de Teste", sigla="LAB-T")
        session.add(lab)
        session.commit()
        session.refresh(lab)
        print(f"✅ Laboratório criado com ID: {lab.id}")

        # 2. Usuário (Passando os campos extras que o banco está cobrando)
        user = Usuario(
            telegram_id=999, 
            nome="Administrador Teste",
            nivel_acesso="admin", # Campo que o banco está exigindo
            modo_atual="normal"   # Campo que o banco está exigindo
        )
        session.add(user)
        session.commit()
        print("✅ Usuário criado.")

        # 3. Vínculo
        vinculo = UsuarioLaboratorio(
            usuario_id=user.telegram_id, 
            laboratorio_id=lab.id, 
            role=Role.ADMIN
        )
        session.add(vinculo)
        session.commit()
        print("✅ Vínculo (Admin) criado com sucesso!")

if __name__ == "__main__":
    try:
        testar_criacao()
        print("\n🎉 Tudo ok! O banco de dados suporta relacionamentos e permissões.")
    except Exception as e:
        print(f"\n❌ Erro: {e}")