import pandas as pd
import re
from sqlmodel import Session, select
from database.db import engine
from database.models import Laboratorio, Reagente

def importar_dados(caminho_csv: str):
    print("Iniciando importação...")
    
    # Lendo o CSV com o pandas
    try:
        df = pd.read_csv(caminho_csv)
    except FileNotFoundError:
        print(f"❌ Erro: Arquivo '{caminho_csv}' não encontrado.")
        return

    with Session(engine) as session:
        for index, row in df.iterrows():
            # 1. Extração bruta dos dados
            nome_reagente = str(row['Reagente']).strip()
            qtd_bruta = str(row['Quantidade']).strip()
            lab_sigla = str(row['Laboratório (POA, LAT, etc.)']).strip()
            
            # Tratamento de campos opcionais para evitar "nan" no banco
            frascos = row.get('Unidade (Vol/Cap)')
            frascos = int(frascos) if pd.notna(frascos) else None
            
            local = str(row.get('Localização Exata', ''))
            local = None if local.lower() == 'nan' or local == '-' else local.strip()
            
            marca = str(row.get('Marca', ''))
            marca = None if marca.lower() in ['nan', '-', 'não especificada'] else marca.strip()
            
            lote = str(row.get('Lote', ''))
            lote = None if lote.lower() in ['nan', '-'] else lote.strip()
            
            validade = str(row.get('Validade', ''))
            validade = None if validade.lower() in ['nan', '-'] else validade.strip()

            # 2. Separação de Quantidade e Unidade (Regex)
            # Tenta separar número de letras (ex: "1000ml" -> 1000.0, "ml")
            match = re.match(r"([\d\.,]+)\s*([a-zA-Z]+)?", qtd_bruta)
            if match:
                quantidade = float(match.group(1).replace(',', '.'))
                unidade = match.group(2) if match.group(2) else "unidade"
            else:
                quantidade = 0.0
                unidade = qtd_bruta # Fallback se for algo bizarro

            # 3. Busca ou Criação do Laboratório
            statement = select(Laboratorio).where(Laboratorio.sigla == lab_sigla)
            lab = session.exec(statement).first()
            
            if not lab:
                # Se o laboratório não existir no banco, cria ele na hora
                lab = Laboratorio(nome=f"Laboratório {lab_sigla}", sigla=lab_sigla)
                session.add(lab)
                session.commit()
                session.refresh(lab)
                print(f"🏭 Novo laboratório criado: {lab.sigla}")

            # 4. Criação do Reagente
            novo_reagente = Reagente(
                nome=nome_reagente,
                quantidade=quantidade,
                unidade=unidade.lower(),
                frascos=frascos,
                localizacao=local,
                marca=marca,
                lote=lote,
                validade=validade,
                laboratorio_id=lab.id
            )
            session.add(novo_reagente)
        
        # Confirma as alterações no banco de dados
        session.commit()
        print(f"✅ Importação finalizada! {len(df)} reagentes foram salvos no banco de dados.")

if __name__ == "__main__":
    importar_dados("Banco de Dados do Orion - Inventário_Reagentes.csv")