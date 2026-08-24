# Backend — Deus Conhece o Seu Nome

Backend de produção construído em **FastAPI**, **PostgreSQL**, **SQLAlchemy 2.0 + Alembic** e **Evolution API** para a plataforma *"Deus Conhece o Seu Nome"*.

---

## 1. Visão Geral e Arquitetura

O sistema é responsável por:
- Receber webhooks de checkout/compras com garantia de **idempotência**.
- Identificar e normalizar compradores (`email_normalized`, formatação de telefone E.164).
- Gerar livros personalizados em **PDF** via **ReportLab** com validação de integridade do arquivo.
- Orquestrar templates de mensagens com catálogo de variáveis e versionamento imutável.
- Enviar mensagens e documentos via **Evolution API (WhatsApp)** com retry e backoff exponencial.
- Controlar o ciclo de vida e histórico de entregas (`Delivery`) desacoplado das mensagens.
- Fornecer consulta segura de disponibilidade por e-mail com **2FA temporário** e **download assinado via JWT**.

```text
                           ┌─────────────────────┐
                           │     Checkout        │
                           │  Mercado Pago/etc.  │
                           └──────────┬──────────┘
                                      │
                                      ▼
                           ┌─────────────────────┐
                           │      FastAPI        │
                           │                     │
                           │ Orders / Books      │
                           │ Templates           │
                           │ Communication       │
                           │ Webhooks            │
                           └──────────┬──────────┘
                                      │
                     ┌────────────────┼─────────────────┐
                     │                │                 │
                     ▼                ▼                 ▼
              ┌──────────────┐ ┌──────────────┐  ┌──────────────┐
              │  PostgreSQL  │ │ Book Worker  │  │ Message      │
              │              │ │ (Geração PDF │  │ Worker       │
              │ compradores  │ │ ReportLab)   │  │ (Retry &     │
              │ livros       │ └──────────────┘  │ Evolution)   │
              │ templates    │                   └──────┬───────┘
              │ mensagens    │                          │
              └──────────────┘                          ▼
                                                ┌────────────────┐
                                                │ Evolution API  │
                                                └───────┬────────┘
                                                        │
                                                        ▼
                                                     WhatsApp
```

---

## 2. Estrutura do Projeto

```text
backend/
├── app/
│   ├── main.py                          # FastAPI app, CORS, lifespan e rotas
│   ├── core/
│   │   ├── config.py                    # Pydantic Settings (.env, DATABASE_URL, EVOLUTION_*)
│   │   ├── database.py                  # Engine assíncrono e sessão get_db
│   │   ├── security.py                  # Tokens JWT temporários de download, 2FA e API Keys
│   │   └── logging.py                   # Logs estruturados com request_id e order_id
│   ├── models/                          # Modelos ORM SQLAlchemy 2.0
│   │   ├── base.py                      # Base declarativa e mixins (UUID, timestamps)
│   │   ├── buyer.py                     # Buyer com email_normalized único
│   │   ├── order.py                     # Order com status e external_order_id
│   │   ├── book.py                      # Book com status (PENDING, GENERATING, READY, etc.)
│   │   ├── book_template.py             # BookTemplate versionado
│   │   ├── communication_template.py    # CommunicationTemplate com validação de variáveis
│   │   ├── message.py                   # Message com status e correlation com Evolution
│   │   ├── delivery.py                  # Delivery para rastreio de entrega
│   │   ├── processed_event.py           # ProcessedEvent para idempotência de webhooks
│   │   └── verification_code.py         # VerificationCode para 2FA temporário
│   ├── schemas/                         # Schemas Pydantic para validação e serialização
│   ├── api/
│   │   ├── deps.py                      # Injeção de dependências e autenticação admin
│   │   ├── router.py                    # Agregador de rotas /api/v1
│   │   └── routes/                      # Rotas de Health, Buyers, Orders, Books, Templates, Messages, Webhooks
│   ├── services/
│   │   ├── buyer_service.py             # Normalização e busca/criação idempotente
│   │   ├── order_service.py             # Gestão do estado da compra
│   │   ├── book_generator.py            # Motor ReportLab de geração do PDF
│   │   ├── book_service.py              # Ciclo de vida do livro, availability e download seguro
│   │   ├── template_service.py          # Parser de {{variaveis}}, preview e versionamento
│   │   ├── communication_service.py      # Resolução de eventos -> templates -> mensagens
│   │   ├── delivery_service.py          # Rastreio de entregas
│   │   └── evolution_service.py         # Cliente HTTP assíncrono para Evolution API
│   ├── workers/
│   │   ├── queue.py                     # Abstração JobQueue desacoplada
│   │   ├── book_worker.py               # Worker de geração de PDF
│   │   └── message_worker.py            # Worker de envio WhatsApp com retry/backoff
│   └── utils/
│       ├── email.py                     # Normalização de e-mails
│       ├── phone.py                     # Normalização E.164
│       └── idempotency.py               # Helpers de idempotência
├── migrations/                          # Migrações Alembic
├── tests/                               # Suite de testes com pytest
├── Dockerfile
├── docker-compose.yml
├── alembic.ini
├── requirements.txt
└── .env.example
```

---

## 3. Configuração do Ambiente

### 3.1 Variáveis de Ambiente (`.env`)

Copie o `.env.example` para `.env`:

```bash
cp .env.example .env
```

Principais variáveis:
- `DATABASE_URL`: String de conexão com o PostgreSQL (ex: `postgresql+psycopg://app:password@localhost:5432/deus_conhece_nome`).
- `EVOLUTION_API_URL`: URL da sua Evolution API (ex: `http://localhost:8080`).
- `EVOLUTION_API_KEY`: Chave de autenticação da Evolution API.
- `EVOLUTION_INSTANCE`: Nome da instância do WhatsApp (ex: `deus-conhece-nome`).
- `ADMIN_API_KEY`: Chave secreta para rotas administrativas (`X-Admin-API-Key`).
- `SECRET_KEY`: Chave para geração e validação de tokens JWT de download.

---

## 4. Execução Local e Docker

### 4.1 Com Docker Compose (Recomendado)

Inicie todos os serviços (API FastAPI + PostgreSQL):

```bash
docker compose up -d --build
```

A API estará disponível em `http://localhost:8000`.
Documentação interativa Swagger: `http://localhost:8000/docs`.

### 4.2 Localmente com Python

1. Crie o ambiente virtual e instale as dependências:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Execute as migrações do banco de dados:
```bash
alembic upgrade head
```

3. Inicie o servidor:
```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

---

## 5. Endpoints Principais da API

| Método | Endpoint | Descrição | Autenticação |
|---|---|---|---|
| `GET` | `/health` | Health check básico | Pública |
| `GET` | `/health/ready` | Readiness check (DB & Storage) | Pública |
| `POST` | `/api/v1/webhooks/cakto` | Webhook oficial da Cakto (`purchase_approved`) | `secret` no payload |
| `POST` | `/api/v1/webhooks/cakto/purchase-approved` | Alias para webhook da Cakto | `secret` no payload |
| `POST` | `/api/v1/webhooks/orders` | Webhook genérico de compras com idempotência | Pública / Assinatura |
| `POST` | `/api/v1/webhooks/evolution` | Webhook de status da Evolution API | Pública |
| `POST` | `/api/v1/books/availability` | Consulta se há livro disponível por e-mail (inicia 2FA) | Pública |
| `POST` | `/api/v1/books/verify-code` | Valida código 2FA de 6 dígitos e emite token de download | Pública |
| `GET` | `/api/v1/books/{id}/download` | Download seguro do PDF do livro | Token JWT ou Admin |
| `POST` | `/api/v1/books/generate` | Dispara geração manual assíncrona do livro | Admin |
| `POST` | `/api/v1/templates/messages` | Cria template de mensagem | Admin |
| `POST` | `/api/v1/templates/messages/{id}/preview` | Testa preview do template com variáveis | Admin |
| `POST` | `/api/v1/templates/messages/{id}/publish` | Publica versão tornando-a ativa e imutável | Admin |
| `POST` | `/api/v1/messages/{id}/retry` | Reprocessa envio de mensagem com falha | Admin |

---

## 6. Executando os Testes Automatizados

A suíte de testes com `pytest` cobre todas as camadas do sistema (webhooks, geração de PDF, templates, segurança e idempotência):

```bash
.venv/bin/pytest -v
```
