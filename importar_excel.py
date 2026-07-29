import pandas as pd
from sqlmodel import Session, select
from database.db import engine
from database.models import Usuario, Item, Laboratorio, CategoriaItem, NivelAcesso, StatusItem

Caminho_Planilha = "Banco de Dados do Orion.xlsx"

def importar_dados():
    print("⏳ Iniciando a migração da planilha para o banco de dados...")
    xls = pd.ExcelFile(Caminho_Planilha)
    
    with Session(engine) as session:
        # 1. IMPORTAR USUÁRIOS
        print("👤 Importando Usuários...")
        df_usuarios = pd.read_excel(xls, "Usuarios").dropna(subset=['ID_Telegram'])
        for _, row in df_usuarios.iterrows():
            # Converte Admin/Membro da planilha para os nossos Enums restritos
            nivel = NivelAcesso.ADMIN if str(row['Nivel_Acesso']).strip().lower() == "administrador" else NivelAcesso.MEMBRO
            usuario = Usuario(
                telegram_id=int(row['ID_Telegram']),
                nome=str(row['Nome']),
                nivel_acesso=nivel
            )
            # Usa merge para não duplicar se rodar o script duas vezes
            session.merge(usuario)
        
        # 2. DESCOBRIR E CRIAR LABORATÓRIOS
        print("🏢 Identificando Laboratórios...")
        labs_encontrados = set()
        for aba in ["Inventário_Reagentes", "Inventário_Ferramentas", "Inventário_Limpeza"]:
            df = pd.read_excel(xls, aba)
            # Pega a coluna que tem "Laboratório" no nome
            col_lab = [col for col in df.columns if "Laboratório" in col][0]
            labs = df[col_lab].dropna().unique()
            labs_encontrados.update(labs)
        
        dict_labs = {} # Dicionário para guardar as IDs dos laboratórios criados
        for nome_lab in labs_encontrados:
            lab_obj = session.exec(select(Laboratorio).where(Laboratorio.sigla == nome_lab)).first()
            if not lab_obj:
                lab_obj = Laboratorio(nome=nome_lab, sigla=nome_lab)
                session.add(lab_obj)
                session.commit()
                session.refresh(lab_obj)
            dict_labs[nome_lab] = lab_obj.id

        # 3. IMPORTAR REAGENTES
        print("🧪 Importando Reagentes...")
        df_reagentes = pd.read_excel(xls, "Inventário_Reagentes")
        for _, row in df_reagentes.iterrows():
            lab_nome = row[[c for c in df_reagentes.columns if "Laboratório" in c][0]]
            item = Item(
                nome=str(row['Reagente']),
                categoria=CategoriaItem.REAGENTE,
                quantidade_atual=float(str(row['Quantidade']).replace('g','').replace('ml','').strip() if pd.notna(row['Quantidade']) else 0),
                unidade_medida="un", # Simplificado para o script; você pode refinar
                frascos=int(row['Unidade (Vol/Cap)']) if pd.notna(row['Unidade (Vol/Cap)']) else None,
                laboratorio_id=dict_labs.get(lab_nome),
                localizacao_exata=str(row['Localização Exata']) if pd.notna(row['Localização Exata']) else None,
                marca=str(row['Marca']) if pd.notna(row['Marca']) else None,
                lote=str(row['Lote']) if pd.notna(row['Lote']) else None
            )
            session.add(item)

        # 4. IMPORTAR FERRAMENTAS E EQUIPAMENTOS
        print("⚙️ Importando Equipamentos e Vidrarias...")
        df_ferramentas = pd.read_excel(xls, "Inventário_Ferramentas")
        for _, row in df_ferramentas.iterrows():
            lab_nome = row['Laboratório']
            categoria = CategoriaItem.VIDRARIA if str(row['Categoria']).strip().lower() == "vidrarias" else CategoriaItem.EQUIPAMENTO
            
            # Mapeamento do status
            status_planilha = str(row['Estado/Condição']).strip().lower()
            if "uso" in status_planilha: status = StatusItem.EM_USO
            else: status = StatusItem.BOM

            item = Item(
                nome=str(row['Nome do Item']),
                categoria=categoria,
                quantidade_atual=float(row['Quantidade']) if pd.notna(row['Quantidade']) else 1.0,
                unidade_medida="unidades",
                laboratorio_id=dict_labs.get(lab_nome),
                localizacao_exata=str(row['Localização Exata']) if pd.notna(row['Localização Exata']) else None,
                estado=status
            )
            session.add(item)

        # 5. IMPORTAR MATERIAL DE LIMPEZA
        print("🧹 Importando Materiais de Limpeza...")
        df_limpeza = pd.read_excel(xls, "Inventário_Limpeza")
        for _, row in df_limpeza.iterrows():
            lab_nome = row['Laboratório']
            item = Item(
                nome=str(row['Material']),
                categoria=CategoriaItem.LIMPEZA,
                quantidade_atual=float(str(row['Quantidade']).replace('L','').strip() if pd.notna(row['Quantidade']) else 0),
                unidade_medida="L",
                laboratorio_id=dict_labs.get(lab_nome),
                localizacao_exata=str(row['Localização Exata']) if pd.notna(row['Localização Exata']) else None
            )
            session.add(item)

        session.commit()
        print("✅ Migração concluída com sucesso! Banco populado.")

if __name__ == "__main__":
    importar_dados()