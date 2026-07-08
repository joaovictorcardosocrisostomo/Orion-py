```python
import pandas as pd

filepath = "Banco de Dados do Orion.xlsx"
try:
    xls = pd.ExcelFile(filepath)
    print("Sheets:", xls.sheet_names)
    for sheet in xls.sheet_names:
        df = pd.read_excel(filepath, sheet_name=sheet)
        print(f"\n--- Sheet: {sheet} ---")
        print(df.head(3).to_markdown())
except Exception as e:
    print(f"Error reading file: {e}")


```

```text
Sheets: ['Inventário_Reagentes', 'Inventário_Ferramentas', 'Inventário_Limpeza', 'Log_Agendamentos', 'Usuarios', 'Experimentos_Ativos', 'Backup_Reagentes']

--- Sheet: Inventário_Reagentes ---
|    | Reagente              | Quantidade   |   Unidade (Vol/Cap) | Laboratório (POA, LAT, etc.)   | Localização Exata   | Marca    | Lote     | Validade            |
|---:|:----------------------|:-------------|--------------------:|:-------------------------------|:--------------------|:---------|:---------|:--------------------|
|  0 | 1-10 Fenantrolina     | 325g         |                   2 | LAT                            | Bancada 4           | Vetec    | DCBB4670 | 2025-12-01 00:00:00 |
|  1 | Ácido Acético Glacial | 1000ml       |                   3 | POA                            | Armário de Ácidos   | Dinâmica | 28831    | 2027-05-01 00:00:00 |
|  2 | Nitrato de Prata      | 50g          |                   1 | POA                            | bancada geral       | Merck    | K4923123 | 2029-01-01 00:00:00 |

--- Sheet: Inventário_Ferramentas ---
|    | Nome do Item                  | Categoria    |   Quantidade | Laboratório   | Localização Exata      | Estado/Condição   | Última Calibração/Manutenção   |
|---:|:------------------------------|:-------------|-------------:|:--------------|:-----------------------|:------------------|:-------------------------------|
|  0 | Almofariz com pistilo         | vidrarias    |            8 | POA           | Estantes de 1 a 4      | Bom               | NaT                            |
|  1 | pHmetro de Bancada DM-22      | equipamentos |            1 | Lanagua       | Bancada Principal      | Em uso            | 2025-10-01 00:00:00            |
|  2 | Espectrofotômetro UV-Vis 1800 | equipamentos |            1 | Croma         | Sala de Instrumentação | Em uso            | 2024-05-06 00:00:00            |

--- Sheet: Inventário_Limpeza ---
|    | Material                   | Quantidade   | Laboratório   | Localização Exata           |
|---:|:---------------------------|:-------------|:--------------|:----------------------------|
|  0 | Detergente Neutro (Extran) | 5 L          | LAT           | Armário da Pia              |
|  1 | Papel Toalha (Fardo)       | 3            | Lanagua       | Prateleira 1 - Almoxarifado |
|  2 | Álcool 70% (Galão)         | 10 L         | LabITech      | Bancada Central             |

--- Sheet: Log_Agendamentos ---
|    | ID_Sessão   |   ID_Telegram | Data       | Hora_Início   | Hora_Fim   | Analista    | Experiência/Método              | Itens Reservados                            | Estado    |
|---:|:------------|--------------:|:-----------|:--------------|:-----------|:------------|:--------------------------------|:--------------------------------------------|:----------|
|  0 | AG-001      |  nan          | 20/02/2026 | nan           | nan        | João        | Análise de Ferro                | 1-10 Fenantrolina, Espectrofotômetro UV-Vis | Concluído |
|  1 | AG-002      |  nan          | 21/02/2026 | nan           | nan        | Maria       | Titulação                       | Ácido Acético, pHmetro                      | Agendado  |
|  2 | AG-5773     |    6.1039e+09 | sexta      | 14:00:00      | 16:30:00   | João Victor | Análise de substâncias químicas | Espectrofotômetro UV-Vis                    | Agendado  |

--- Sheet: Usuarios ---
|    |   ID_Telegram | Nome                          | Nivel_Acesso   | Modo_Atual   |
|---:|--------------:|:------------------------------|:---------------|:-------------|
|  0 |    6103903943 | João Victor                   | Administrador  | Normal       |
|  1 |     910353240 | Thiago                        | Membro         | Normal       |
|  2 |    6520159314 | Américo Vitor Moreira Barbosa | Membro         | nan          |

--- Sheet: Experimentos_Ativos ---
|    |   ID_Experimento |   ID_Telegram |   Nome_Experimento |   Etapa |   Ordem |   Tempo_Minutos |   Materiais_Necessarios |   Status |   Hora_Alarme |   Avisos |
|---:|-----------------:|--------------:|-------------------:|--------:|--------:|----------------:|------------------------:|---------:|--------------:|---------:|
|  0 |              nan |           nan |                nan |     nan |     nan |             nan |                     nan |      nan |           nan |        0 |
|  1 |              nan |           nan |                nan |     nan |     nan |             nan |                     nan |      nan |           nan |        0 |
|  2 |              nan |           nan |                nan |     nan |     nan |             nan |                     nan |      nan |           nan |        0 |

--- Sheet: Backup_Reagentes ---
|    | Reagente        |   Quantidade | Unidade (Vol/Cap)   | Laboratório (POA, LAT, etc.)   | Localização Exata   | Marca   | Lote   | Validade            |
|---:|:----------------|-------------:|:--------------------|:-------------------------------|:--------------------|:--------|:-------|:--------------------|
|  0 | Ácido Sulfúrico |          500 | ml                  | POA                            | Armário de Ácidos   | Merck   | AS9988 | 2028-12-01 00:00:00 |


```

Este é um passo monumental para o projeto. Sair de planilhas estáticas para uma arquitetura relacional baseada em grafos de conhecimento e LLMs vai transformar o Orion de um simples "bot de registro" em um verdadeiro Assistente Digital de Laboratório (LIMS - *Laboratory Information Management System*).

Com base na sua descrição detalhada do fluxo de uso e na análise da estrutura atual do seu `Banco de Dados do Orion.xlsx`, elaborei a **Documentação Arquitetural e o Plano de Execução do Sistema Orion**.

---

# 🌌 Documentação Arquitetural: Sistema Orion (MVP)

## 1. Visão Geral e Stack Tecnológica

O Orion é um sistema assíncrono de gestão laboratorial operado inteiramente via Telegram através de processamento de linguagem natural (NLP). Ele substitui o antigo fluxo em planilhas por um banco de dados relacional e inteligência artificial para planejamento experimental.

* **Interface:** Telegram Bot API (via `aiogram` 3.x)
* **Servidor e Orquestração:** FastAPI (para gestão de ciclo de vida e futuras integrações web) rodando em contêineres Docker gerenciados por Docker Compose em uma VPS.
* **Banco de Dados:** PostgreSQL (armazenamento relacional) com extensão `pgvector` (armazenamento vetorial para o RAG).
* **ORM (Mapeamento de Dados):** SQLModel (combina Pydantic para validação e SQLAlchemy para queries).
* **Inteligência Artificial (LLM & NLP):** OpenAI Python SDK. (Iniciando com Groq API para o MVP de alta velocidade e migração futura transparente para instâncias locais de Ollama/llama.cpp).
* **Agendador de Tarefas (Cron):** `APScheduler` (responsável pelo gatilho diário de prestação de contas às 17h).

---

## 2. Reestruturação do Banco de Dados (De Excel para SQL)

A transição das abas da sua planilha para tabelas relacionais exige normalização para suportar rastreabilidade estruturada.

* **Tabela `Usuario` (Antiga aba *Usuarios*):**
* Campos: `telegram_id` (PK), `nome`, `nivel_acesso` (Admin/Membro).


* **Tabela `Item` (Base unificada para as abas de *Inventário*):**
* Em vez de três tabelas soltas, criamos categorias. Campos: `id` (PK), `nome`, `tipo` (Reagente, Equipamento, Vidraria, Limpeza), `quantidade_atual`, `unidade_medida`, `localizacao_exata`, `laboratorio_id` (FK), `marca/lote`, `estado` (Bom, Em uso, Requer Calibração, Quebrado).


* **Tabela `Agendamento` (Antiga aba *Log_Agendamentos*):**
* Campos: `id` (PK), `usuario_id` (FK), `item_id` (FK), `data_inicio`, `data_fim`, `status` (Agendado, Concluído, Cancelado, Em conflito).


* **Tabela `Log_Uso` (Nova):**
* Para o controle estrito exigido: registra *quem*, tirou *o quê*, *de onde*, usou *quanto* e devolveu *aonde* e em *qual estado*.


* **Tabela `Procedimento_RAG` (Nova):**
* Armazena os embeddings vetoriais dos POPs (Procedimentos Operacionais Padrão) para consulta do LLM.



---

## 3. Fluxos de Uso e Módulos do Sistema

### Módulo A: Onboarding e Controle de Acesso (RBAC)

* **Fluxo Inicial:** Ao dar `/start` pela primeira vez, o bot verifica se o `telegram_id` existe. Se não, apresenta botões interativos (*InlineKeyboard*): `[Sou Membro]` ou `[Sou Administrador]`.
* *Nota de Segurança:* Para evitar que alunos se declarem administradores, a opção "Administrador" exigirá uma senha mestre de configuração inicial ou aprovação de um Super Admin.


* **Regras de Edição:**
* **Membros:** Só têm permissão de CRUD (Criar, Ler, Atualizar, Deletar) sobre agendamentos com o seu próprio `telegram_id`.
* **Admins:** Possuem *override*. Se um Admin cancelar a reserva de um Membro, o sistema dispara um gatilho via `aiogram` que envia uma notificação push direta para o Membro: *"⚠️ Seu agendamento do [Equipamento] para [Data] foi cancelado por [Nome do Admin]. Por favor, alinhe o remanejamento."*



### Módulo B: Prevenção de Conflitos e Agendamento Inteligente

* **Mecanismo:** Antes de confirmar um agendamento, o backend executa uma *query* verificando se há intersecção de horário (`data_inicio` e `data_fim`) para o mesmo `item_id`.
* **Tratamento:** Caso positivo, o LLM traduz o erro do banco de dados em linguagem natural: *"O Espectrofotômetro UV-Vis já está reservado pelo Thiago das 14:00 às 16:30. Deseja agendar para as 16:45?"*

### Módulo C: Busca em Linguagem Natural e Controle de Baixa

* **Intenção Tripla:** O *Function Calling* do LLM terá um seletor estrito. Se o usuário diz *"Vou usar o ácido acético"*, o LLM sabe que a categoria é `Reagente` e aciona a função de baixa específica que engatilha o questionário de consumo.
* **Uso e Descarte:** Para itens retornáveis (equipamentos/vidrarias), a IA pergunta: *"Você lavou a vidraria e guardou no [Armário 8] ou precisou descartar?"*. Para reagentes: *"Qual volume foi consumido?"*. Isso deduz do banco na hora.

### Módulo D: O Auditor Diário (Rotina das 17h)

* **Gatilho:** A biblioteca `APScheduler` dispara uma rotina todos os dias às 17h00.
* **Lógica:** O sistema busca no banco quem estava com agendamento ativo ou fez pesquisas no dia.
* **Questionário Interativo:** O bot envia uma mensagem: *"Resumo do expediente! Notei que você usou o pHmetro de Bancada DM-22 e 50g de Nitrato de Prata hoje. Confirma?"*
* Em caso de equipamentos: *"Houve alguma avaria ou necessidade de reposição (ex: gás) no equipamento?"*
* A resposta atualiza a coluna `estado` no banco para acionar alertas de manutenção.



### Módulo E: Planejamento Experimental IA (RAG)

Este é o ápice do sistema, dividido em 4 etapas:

1. **Ingestão de Intenção:** *"Quero fazer uma análise de Ferro amanhã de manhã."*
2. **Busca Vetorial (RAG):** O banco de dados (usando `pgvector`) busca os documentos do laboratório sobre "Análise de Ferro" (ex: método de fenantrolina).
3. **Proposição do LLM:** A IA gera um JSON estruturado com o fluxo, que o Orion traduz para o chat:
* *Cronograma Sugerido:*
* 08:00 - 08:30: Preparo de bancada e calibração.
* 08:30 - 10:00: Reação com 1-10 Fenantrolina e Ácido Acético.
* 10:00 - 11:30: Leitura no UV-Vis 1800.
* 11:30 - 12:00: Organização, descarte e lavagem.


* *Recursos Necessários:* UV-Vis, Balão 60mL, Fenantrolina, Álcool 70%.


4. **Negociação e *Commit*:** O usuário pode responder *"Vou usar 2 balões em vez de 1 e não preciso calibrar"*. O LLM ajusta, pede confirmação final e, ao receber o "Ok", dispara as funções de escrita no banco de dados, "trancando" todos aqueles recursos para o usuário naquelas janelas de tempo de uma só vez.

---

## 4. Plano de Execução (Roadmap de Construção)

Para construirmos isso de forma organizada, proponho dividirmos o código em Sprints (ciclos):

* **Sprint 1: Modelagem e Migração (Sem IA ainda)**
* Ajustar os `models.py` para refletir o schema relacional acima.
* Escrever um script de importação (com a biblioteca `pandas`) para ler o seu `.xlsx` atual e popular o novo PostgreSQL para não perder o histórico do LAT, POA, Croma e Lanagua.


* **Sprint 2: O Motor do LLM (Intenção e Busca)**
* Consolidar o `services/llm.py` usando `AsyncOpenAI` e *Function Calling* para rotear as mensagens para "buscar reagente", "buscar equipamento" ou "agendar".


* **Sprint 3: O Sistema de Agendamentos e Conflitos**
* Criar o CRUD de reservas.
* Implementar a lógica de colisão de horários e envio de mensagens inter-usuários (notificação de admin).


* **Sprint 4: Rotina de Pós-Expediente (17h)**
* Configurar o `APScheduler` rodando em segundo plano junto com o *polling* do Aiogram.
* Desenhar a máquina de estados (*FSM - Finite State Machine* do Aiogram) para guiar o usuário passo a passo pelas perguntas de final do dia sem que ele se perca.


* **Sprint 5: O Cérebro RAG (Planejamento Experimental)**
* Configurar o banco vetorial e inserir os primeiros POPs (documentos em PDF/texto).
* Criar a cadeia de *prompt* avançada que cruza o documento RAG com a disponibilidade em tempo real dos itens do banco de dados.



Você está pronto para começarmos pelo **Sprint 1**, alterando oficialmente os modelos do banco de dados para suportarem todo esse grau de detalhamento exigido pelos módulos futuros?