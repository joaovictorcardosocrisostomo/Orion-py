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

### Módulo F: Comando `/experimento` — Planejamento Experimental Manual

O comando `/experimento` é a porta de entrada direta para o planejamento experimental no Orion, oferecendo uma versão estendida do fluxo relâmpago já existente. Enquanto o `/hoje` gerencia o que já está agendado, o `/experimento` **guia o usuário do zero até a execução** de um experimento.

**Fluxo do `/experimento`:**

1. **Início:** O usuário digita `/experimento` e o bot pergunta qual equipamento será utilizado.
2. **Seleção de Equipamento:** O usuário digita o nome. O sistema busca no banco e retorna o equipamento mais relevante.
   * *Validação:* Se o equipamento estiver em uso por outra pessoa, o sistema informa e bloqueia.
3. **Definição de Duração:** Botões de 1 a 4 horas (igual ao fluxo relâmpago), mas aqui o usuário também pode digitar um tempo personalizado em minutos.
4. **Confirmação de Recursos (Pré-RAG):** Nesta versão manual, o bot pergunta:
   * *"Quais reagentes e vidrarias você vai usar?"* (campo de texto livre)
   * O usuário lista os itens, e o sistema registra essa intenção no banco (tabela `LogUso` ou uma nova `Experimento`).
   * O sistema valida se cada item citado existe no inventário e alerta se algo estiver em falta.
5. **Início Imediato:** Após confirmar tudo, a reserva é criada com status **EM_ANDAMENTO**, o equipamento é marcado como "Em uso", e o alarme de fim é disparado.
6. **Finalização:** Ao terminar, o bot pergunta:
   * ✅ Como ficou o estado do equipamento (Bom / Avaria)?
   * ✅ Quanto de cada reagente foi consumido?
   * ✅ Algo foi descartado? Precisa de reposição?
   * Os dados são registrados na tabela `LogUso` e o estoque é atualizado automaticamente.

**Diferenças chave para o relâmpago:**
| Característica | `/hoje` (Relâmpago) | `/experimento` |
|---|---|---|
| Equipamento | Apenas 1 | 1 principal + lista de insumos |
| Registro de consumo | ❌ Não | ✅ Reagentes, descartes, reposição |
| Vínculo com RAG | ❌ | ✅ Futuramente engatilha o Módulo E |
| Protocolo salvo | ❌ | ✅ Gera um protocolo experimental reutilizável |

---

### ⚙️ Nota Arquitetural: Todas as Funções como Blocos para Orquestração por LLM

É fundamental registrar que **todas as funções e serviços que estamos construindo** (agendamento, estoque, relatório, scheduler, FSM de experimento, relatório de avarias) **não são fins em si mesmos** — são **building blocks** que a LLM orquestrará via *function calling* no futuro.

**Funções que a LLM precisará chamar:**

| Função | Serviço | Descrição |
|---|---|---|
| `buscar_reagente` | `services/estoque.py` | Busca reagente no inventário |
| `buscar_equipamento` | `services/estoque.py` | Busca equipamento no inventário |
| `buscar_vidraria` | `services/estoque.py` | Busca vidraria no inventário |
| `buscar_limpeza` | `services/estoque.py` | Busca material de limpeza |
| `registrar_agendamento` | `services/agendamento.py` | Cria uma reserva no banco |
| `cancelar_agendamento` | `services/agendamento.py` | Cancela uma reserva |
| `registrar_consumo` | (futuro) | Dá baixa em reagente consumido |
| `registrar_descarte` | (futuro) | Registra descarte de material |
| `registrar_reposicao` | (futuro) | Sinaliza necessidade de reposição |
| `consultar_rag` | `services/rag.py` | Busca POPs/artigos no banco vetorial |
| `criar_protocolo` | (futuro) | Salva um protocolo experimental |

**Fluxo futuro (Sprint 6):**
```
Usuário: "Vou fazer análise de Ferro amanhã"
  → LLM recebe a mensagem
  → LLM chama consultar_rag("análise de Ferro")
  → RAG retorna: "Método da Fenantrolina (POP-042)"
  → LLM identifica recursos: UV-Vis, Fenantrolina, Ácido Acético, Balão 60mL
  → LLM chama buscar_equipamento("UV-Vis") → "Disponível no Croma"
  → LLM chama buscar_reagente("Fenantrolina") → "325g no LAT, bancada 4"
  → LLM chama registrar_agendamento(item, inicio, fim) para CADA recurso
  → LLM pergunta: "Vou reservar tudo isso. Confirma?"
  → Usuário confirma → sistema executa todas as reservas atômicas
```

Quando o RAG for ativado, o **Módulo E** (planejamento via IA) e o **Módulo F** (comando manual `/experimento`) se fundirão: o `/experimento` será o atalho para disparar todo o pipeline RAG + agendamento automático.

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

* **Sprint 6: Orquestração Total Via LLM + RAG (Planejamento Experimental Inteligente)**
*Esta sprint unifica todas as anteriores e entrega o ápice do sistema: a LLM orquestrando todo o fluxo experimental via linguagem natural.*

**Objetivo:** Permitir que o usuário diga em linguagem natural o que quer fazer (ex: *"Vou fazer uma análise de quantificação de Ferro"*) e o Orion:
1. **Consulte o RAG** (`services/rag.py`) — busca nos POPs, artigos e livros dos laboratórios pelo método descrito para aquela análise.
2. **Extraia os recursos necessários** — o LLM identifica no documento quais reagentes, vidrarias e equipamentos são necessários.
3. **Cruze com o inventário real** — para cada recurso identificado, chama `buscar_*` para ver:
   * Se o item existe no estoque
   * Em qual laboratório está (POA, LAT, Croma, Lanagua, LabITech)
   * Se está disponível ou em uso
   * A quantidade/disponibilidade atual
4. **Monte o plano experimental** — o LLM propõe um cronograma com etapas, horários e alocação de recursos, negociando com o usuário.
5. **Execute as reservas** — após confirmação, chama:
   * `registrar_agendamento` para cada equipamento
   * `registrar_consumo` para cada reagente (já com previsão de quanto será usado)
   * `registrar_descarte` se o método prevê descarte
   * `registrar_reposicao` se algo precisa ser reposto
6. **Monitore e registre** — ao final do experimento, o sistema pergunta:
   * Quanto foi realmente consumido de cada reagente (ajuste fino)
   * Houve desvio do protocolo?
   * O equipamento foi devolvido em bom estado?
   * Precisa repor algo?

**Novas ferramentas necessárias no LLM (function calling):**
* `consultar_rag(termo_busca)` — busca vetorial por similaridade no banco de conhecimento
* `registrar_consumo(item_id, quantidade, unidade)` — dá baixa em reagente
* `registrar_descarte(item_id, quantidade, motivo)` — registra descarte
* `registrar_reposicao(item_id, quantidade_necessaria)` — sinaliza compra
* `criar_protocolo_experimental(plano_json)` — salva o protocolo para reuso futuro

**Nova tabela no banco:**
* **`ProtocoloExperimental`** — armazena protocolos salvos (título, descrição, etapas, recursos, duração estimada) para reuso e versionamento.

**Integração com `/experimento`:**
Quando o Sprint 6 estiver pronto, o comando `/experimento` ganhará um **modo inteligente**: se o RAG tiver um documento relevante para o que o usuário quer fazer, o sistema sugerirá o protocolo completo — se não, cai no fluxo manual do Módulo F.

---

* **Sprint 7: Painel Web LIMS & Integração Telegram MiniApp (Concluído)**
*Entrega uma interface visual de alto padrão estético para os analistas e coordenadores do laboratório, com acesso direto pelo Telegram e pelo navegador.*

**Funcionalidades Implementadas:**
1. **Dashboard SPA (FastAPI + HTML5/CSS3/JS puro):**
   * KPIs em tempo real: Total de Itens, Equipamentos em Uso, Alertas de Reposição Crítica, Agendamentos do Dia.
   * **Aba 1 (Inventário Geral):** Tabela responsiva com busca instantânea, filtros por categoria (Reagentes, Equipamentos, Vidrarias, Limpeza), laboratório (LAT, POA, Croma, Lanagua, LabITech) e status com badges visuais.
   * **Aba 2 (Reposições & Compras):** Itens com estoque zerado ou sinalizados no `LogUso` (`reposicao_necessaria = True`), com nível de urgência e botão de reabastecimento rápido.
   * **Aba 3 (Agendamentos & Bancada):** Linha do tempo de reservas ativas com indicação em tempo real de equipamentos em uso.
   * **Aba 4 (Histórico de Auditoria & Avarias):** Feed das últimas prestações de contas das 17h e registros de quebras.
   * **Aba 5 (Protocolos & POPs):** Visualização dos métodos operacionais salvos e procedimentos vetorizados no RAG.
   * **Exportação CSV:** Download instantâneo da planilha de inventário formatada para auditorias.
2. **Integração Telegram (/dashboard e /painel):**
   * Comando `/dashboard` ou `/painel` no Telegram envia um resumo dos indicadores com botões inline:
     - `📱 Abrir MiniApp no Telegram` (via `WebAppInfo`, abrindo o painel direto na tela do Telegram).
     - `🌐 Abrir no Navegador` (para acesso via desktop/Chrome).
     - `🔄 Atualizar Indicadores` (atualiza os números direto na mensagem do chat).
3. **Endpoints REST Implementados (`api/dashboard.py`):**
   * `GET /dashboard` — Interface web completa.
   * `GET /api/dashboard/stats` — Métricas globais.
   * `GET /api/dashboard/itens` — Inventário filtrado.
   * `GET /api/dashboard/reposicoes` — Compras pendentes.
   * `GET /api/dashboard/agendamentos` — Reservas do laboratório.
   * `GET /api/dashboard/logs` — Auditorias recentes.
   * `GET /api/dashboard/protocolos` — Protocolos e POPs.
   * `POST /api/dashboard/itens/{id}/reabastecer` — Atualização rápida de estoque com auditoria por analista.
   * `POST /api/dashboard/auth/login` — Autenticação de Membro (acesso direto) ou Administrador (com senha mestre).
   * `GET /api/dashboard/usuarios` — Lista de pesquisadores cadastrados.
4. **Auto-Refresh em Tempo Real & Autenticação Web:**
   * **Sincronização Contínua:** Polling a cada 15 segundos com indicador visual dinâmico (`Ao Vivo (15s)`), sem interromper a navegação ou preenchimento de modais.
   * **Identificação de Usuário ("Laboratório Orion"):** O botão no cabeçalho funciona como login dinâmico:
     - Permite entrada como **Membro** (acesso rápido pelo nome) ou **Administrador** (validação com senha mestre).
     - Integração transparente com Telegram WebApp e persistência no `localStorage`.
     - Exibição de card de perfil com privilégios ativos e opção de logout/troca de usuário.

---

* **Sprint 8: Relatórios Automatizados, Tempo de Bancada, Caderno ELN, Gestão de Manutenção & Briefing Noturno (Concluído)**
*Entrega 5 novas dimensões críticas de automação laboratorial e conformidade metrológica (ISO/IEC 17025 e BPL) tanto no Telegram Bot quanto no Painel Web LIMS.*

**Funcionalidades Implementadas:**

1. **Módulo G: Rastreamento de Tempo Real de Bancada & Relatórios Automatizados (`services/relatorio_bancada.py`):**
   - **Medição Real:** Registro de `inicio_real`, `fim_real`, cálculo de duração em minutos e desvio planejado (`desvio_planejado_minutos`) nas reservas.
   - **Botão Iniciar:** Ativação instantânea do experimento direto pelo Telegram (`/hoje`) registrando o início real da bancada com alarme sincronizado.
   - **Métricas Consolidadas:** Agregação de horas totais, desvio médio de agenda, tempo por equipamento e produtividade por analista.
   - **Exportação Multiformato:** Geração de relatórios analíticos em Markdown e planilhas em CSV (`/api/dashboard/relatorios/tempo-bancada/csv`).
   - **Interface Web:** Aba "Tempo de Bancada" no dashboard com 3 KPI cards, filtro por período (7, 15, 30, 90 dias) e tabela de histórico.

2. **Módulo H: Caderno de Laboratório Eletrônico Automatizado (ELN) (`services/caderno.py`):**
   - **Código Sequencial ISO:** Geração automática e atômica de código de ensaio rastreável (`EXP-YYYY-XXXX`).
   - **Registro Completo:** Amostra/lote, objetivo, materiais, dados brutos/leituras analíticas, desvios e tempo de bancada vinculado.
   - **Comando `/caderno`:** Máquina de estados (FSM) no Telegram permitindo abertura guiada de folha de ensaio direto da bancada.
   - **Exportação Markdown:** Download de relatórios técnicos individuais formatados para auditoria (`/api/dashboard/caderno/{id}/exportar`).
   - **Interface Web:** Aba "Caderno (ELN)" com busca instantânea em tempo real, badges de status de conformidade e exportação.

3. **Módulo I: Controle Metrológico & Gestão de Manutenções (`services/manutencao.py`):**
   - **Ciclo Preventivo e Calibrações:** Agendamento periódico (`frequencia_manutencao_dias`), cálculo de vencimento (`proxima_manutencao`) e registro de certificados metrológicos com rastreabilidade RBC.
   - **Horímetro de Operação:** Monitoramento de horas de operação limite (`horas_operacao_limite`) vs acumuladas (`horas_operacao_acumuladas`) para substituição preventiva de lâmpadas UV/deuterio, colunas e bombas.
   - **Abertura Corretiva Automática:** Ao relatar avaria no checklist de finalização, o sistema cria automaticamente um ticket corretivo e coloca o equipamento em estado "Quebrado".
   - **Alerta Diário às 08h00:** Job agendado matinal que avisa os administradores sobre calibrações vencidas ou próximas de vencer (15 dias).
   - **Comando `/manutencao` & Aba Web:** Visualização metrológica completa, 4 KPIs de status e histórico de intervenções.

4. **Módulo J: Sistema Centralizado de Notificações (`services/notificacoes.py`):**
   - **Persistência Estruturada:** Tabela `Notificacao` no banco de dados com categoria (`ALERTA_ESTOQUE`, `MANUTENCAO`, `AGENDAMENTO`, `BRIEFING_DIARIO`, `GERAL`), título e status de entrega/leitura.
   - **Disparo Resiliente:** Tratamento de bloqueios do Telegram Bot (`TelegramForbiddenError`, timeout) sem interromper a rotina do servidor.
   - **Notificação de Administradores:** Broadcast automático para todos os administradores cadastrados em caso de quebras ou cancelamentos operacionais.

5. **Módulo K: Briefing Noturno de Planejamento Registrado (`services/scheduler.py`):**
   - **Disparo Automático às 17h30:** Executado de segunda a sexta-feira via APScheduler.
   - **Público-Alvo Inteligente:** Identifica analistas que possuem agendamentos confirmados para o dia útil seguinte.
   - **Briefing Detalhado:** Envia resumo com horários de início/fim, equipamento alocado, insumos previstos e botões interativos `[✅ Confirmar Planejamento]` e `[✏️ Ajustar no Painel]`.

6. **Endpoints REST Implementados (`api/dashboard.py`):**
   - `GET /api/dashboard/relatorios/tempo-bancada` & `/csv`
   - `GET /api/dashboard/caderno`, `POST /api/dashboard/caderno`, `GET /api/dashboard/caderno/{id}/exportar`
   - `GET /api/dashboard/manutencoes/status`, `GET /api/dashboard/manutencoes/historico`, `POST /api/dashboard/manutencoes`
   - `GET /api/dashboard/notificacoes`, `POST /api/dashboard/notificacoes/{id}/lida`

---

* **Sprint 9: Governança Laboratorial, Autoria do Caderno ELN, RBAC de Reservas & Sistema Centralizado de Notificações (Em Implementação)**
*Estabelece o controle rigoroso de autoria e conformidade científica (ISO 17025 e BPL) no Caderno de Laboratório Eletrônico e na gestão de bancada, integrando mensageria ativa e proteção contra sobreposição indevida.*

**Diretrizes e Funcionalidades:**

1. **Caderno de Laboratório Eletrônico (ELN) por Usuário:**
   * **Identificação com Iniciais no Código:** O código do ensaio adota o padrão EXP-{INICIAIS}-{ANO}-{SEQ:04d} (ex: EXP-JV-2026-0001 para João Victor, EXP-T-2026-0001 para Thiago, EXP-AV-2026-0001 para Américo Vitor). A extração automática de iniciais garante rastreabilidade imediata da autoria do ensaio.
   * **Transparência de Leitura Universal:** Qualquer membro ou administrador cadastrado pode ler, auditar e exportar as folhas de ensaio de todos os pesquisadores do laboratório, promovendo reprodutibilidade e cooperação científica.
   * **Edição Exclusiva do Autor (Imutabilidade de Terceiros):** Apenas o pesquisador criador/dono da folha de ensaio tem permissão para alterar títulos, observações, dados brutos, desvios e medições. Nem mesmo administradores podem alterar o registro técnico de outro analista, resguardando a fidedignidade analítica.
   * **Tela Dedicada com Sistema de Busca Avançado:**
     - Pílulas de alternância rápida: [ Todos os Cadernos ] e [ Meus Cadernos ] com contador dinâmico.
     - Busca textual instantânea (código, título, analista, amostra, objetivo, reagente).
     - Filtro por Pesquisador/Analista (select dropdown dinâmico com todos os membros).
     - Filtro por Status do Ensaio (Finalizado, Em Andamento, Rascunho).
     - Filtro por Período de Registro (Hoje, Últimos 7 dias, Últimos 30 dias, Todos).
     - Ações por folha: Visualizar (todos), Editar (somente o autor) e Baixar Markdown (todos).

2. **Gestão de Reservas e Sessões de Bancada com Privilégio Administrativo:**
   * **Visibilidade Coletiva:** Todos os membros têm acesso de leitura à agenda completa e aos equipamentos em uso pelos colegas de laboratório.
   * **Permissões de Modificação & Cancelamento:**
     - Membros comuns podem alterar e cancelar exclusivamente os seus próprios agendamentos.
     - Administradores têm permissão de gerenciamento total (*admin override*), podendo reagendar, modificar horários/equipamentos e cancelar reservas de qualquer membro em caso de manutenções emergenciais, calibrações ou redistribuição de bancada.
   * **Filtro de Visualização:** Interface de agendamentos com filtros [ Todos os Agendamentos ] vs [ Meus Agendamentos ], status e laboratório.

3. **Sistema Centralizado de Notificações Multicanal (services/notificacoes.py):**
   * **Objetivo Geral:** Criar uma infraestrutura unificada de mensageria proativa e reativa via Telegram Bot e Dashboard Web para eventos críticos de bancada, estoque e governança.
   * **Sub-itens e Alertas Prioritários:**
     - **[Sub-item Obrigatório] Alerta de Modificação de Agendamento por Administrador:** Disparo automático de notificação direta (Telegram + notificação web persistida) ao dono do agendamento sempre que um Administrador realizar qualquer alteração, reagendamento ou cancelamento na sua reserva, contendo o nome do administrador responsável, equipamento e justificativa operacional.
     - **Alerta de Cancelamento de Reserva:** Notificação imediata ao membro caso sua reserva seja cancelada administrativamente.
      - **Alerta Preditivo de Término de Garantia de Calibração/Manutenção:** Disparo proativo ao coordenador e técnicos quando uma manutenção ou calibração executada estiver próxima de expirar a garantia (com antecedência configurável pelo usuário, ex: 15 dias), sinalizando a necessidade de recontratação ou novo ciclo de aferição metrológica antes do bloqueio de uso do equipamento.
     - **Alerta Matinal de Calibração e Manutenção Preventiva:** Aviso automático às 08h00 sobre equipamentos com calibração vencida ou próxima ao vencimento.
     - **Alerta de Estoque Crítico:** Notificação aos coordenadores quando itens atingem estoque zero ou forem sinalizados para compra urgente.
     - **Briefing Noturno Diário (17h30):** Envio de agenda personalizada para analistas com ensaios programados no dia útil seguinte.



4. **Controle de Garantias e Ciclo de Recalibração Metrológica (ISO/IEC 17025):**
   * **Registro Completo de Execução:** Ao registrar uma manutenção ou calibração no sistema, o usuário especifica a data de execução real, o responsável técnico/empresa externa, número do certificado/OS e custo.
   * **Prazo de Garantia Parametrizável:** O usuário define o período de garantia da intervenção (opções rápidas: 30 dias, 90 dias, 180 dias / 6 meses, 365 dias / 1 ano, 730 dias / 2 anos ou valor customizado em dias).
   * **Cálculo Automático de Vigência:** O sistema calcula automaticamente a data_fim_garantia (data_manutencao + tempo_garantia_dias) e sincroniza com a data limite do equipamento.
   * **Monitoramento Preditivo de Recalibração:** O usuário define quantos dias antes do vencimento da garantia quer ser notificado (padrão de 15 dias). O scheduler diário das 08h00 e o botão manual no dashboard monitoram os prazos, geram notificações persistentes no banco de dados (Notificacao na categoria MANUTENCAO_ALERTA) e enviam avisos via Telegram aos administradores, evitando equipamentos operando sem garantia técnica válida.
   * **Interface Visual com Badges Dinâmicos:** A tabela de histórico exibe o status em tempo real da garantia (Vigente, ⚠️ Vence em X dias, Expirada, Sem garantia), permitindo auditoria visual imediata.
