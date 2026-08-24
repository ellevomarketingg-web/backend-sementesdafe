# Backend — Deus Conhece o Seu Nome

## 1. Objetivo

Construir um backend responsável por:

- receber e validar compras;
- identificar o comprador pelo e-mail;
- verificar se existe um livro disponível para aquele comprador;
- gerar/personalizar o livro;
- controlar o status da produção e entrega;
- gerar e validar templates de comunicação;
- orquestrar mensagens de comunicação;
- enviar mensagens via Evolution API;
- registrar todas as tentativas de comunicação;
- permitir reprocessamento seguro em caso de falha;
- manter histórico/auditoria das entregas.

### Stack

- **FastAPI** — API REST e camada de aplicação.
- **PostgreSQL** — persistência.
- **Docker / Docker Compose** — execução dos serviços.
- **Evolution API** — comunicação via WhatsApp.
- **Python** — domínio, geração e orquestração.
- **SQLAlchemy + Alembic** — ORM e migrations.
- **Pydantic** — validação de entrada/saída e configuração.

---

# 2. Arquitetura

```text
                           ┌─────────────────────┐
                           │     Checkout        │
                           │ Mercado Pago/etc.   │
                           └──────────┬──────────┘
                                      │
                                      ▼
                           ┌─────────────────────┐
                           │      FastAPI        │
                           │                     │
                           │ Orders / Books      │
                           │ Templates           │
                           │ Communication       │
                           │ Webhooks             │
                           └──────────┬──────────┘
                                      │
                    ┌─────────────────┼──────────────────┐
                    │                 │                  │
                    ▼                 ▼                  ▼
             ┌──────────────┐ ┌──────────────┐  ┌──────────────┐
             │ PostgreSQL   │ │ Book Worker  │  │ Message      │
             │              │ │              │  │ Worker       │
             │ compradores  │ │ geração      │  │ comunicação  │
             │ livros       │ │ PDF          │  │              │
             │ templates    │ │ personalização│ │ Evolution    │
             │ mensagens    │ └──────────────┘  └──────┬───────┘
             └──────────────┘                           │
                                                        ▼
                                               ┌────────────────┐
                                               │ Evolution API  │
                                               └───────┬────────┘
                                                       │
                                                       ▼
                                                    WhatsApp
```

## 2.1 Serviços Docker

Inicialmente:

```text
backend
postgres
evolution-api
```

Opcional/recomendado posteriormente:

```text
redis
worker
scheduler
nginx
```

Para a primeira versão, o backend pode funcionar sem Redis/RabbitMQ. Entretanto, a arquitetura deve deixar a camada de jobs desacoplada para permitir introdução de uma fila posteriormente.

---

# 3. Estrutura do projeto

```text
backend/
├── app/
│   ├── main.py
│   │
│   ├── core/
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── security.py
│   │   └── logging.py
│   │
│   ├── models/
│   │   ├── buyer.py
│   │   ├── order.py
│   │   ├── book.py
│   │   ├── book_template.py
│   │   ├── communication_template.py
│   │   ├── message.py
│   │   └── delivery.py
│   │
│   ├── schemas/
│   │   ├── buyer.py
│   │   ├── order.py
│   │   ├── book.py
│   │   ├── template.py
│   │   ├── message.py
│   │   └── webhook.py
│   │
│   ├── api/
│   │   ├── routes/
│   │   │   ├── buyers.py
│   │   │   ├── orders.py
│   │   │   ├── books.py
│   │   │   ├── templates.py
│   │   │   ├── messages.py
│   │   │   └── webhooks.py
│   │   └── router.py
│   │
│   ├── services/
│   │   ├── buyer_service.py
│   │   ├── order_service.py
│   │   ├── book_service.py
│   │   ├── book_generator.py
│   │   ├── template_service.py
│   │   ├── communication_service.py
│   │   ├── delivery_service.py
│   │   └── evolution_service.py
│   │
│   ├── workers/
│   │   ├── book_worker.py
│   │   └── message_worker.py
│   │
│   └── utils/
│       ├── email.py
│       ├── phone.py
│       └── idempotency.py
│
├── migrations/
├── tests/
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

---

# 4. Conceito central: comprador → livro → entrega

O sistema não deve simplesmente verificar:

```text
email existe?
```

A validação correta deve responder:

```text
Este e-mail possui uma compra válida?
        ↓
A compra possui um produto compatível?
        ↓
Existe um livro associado à compra?
        ↓
O livro está disponível para entrega?
        ↓
Já foi entregue?
        ↓
Existe alguma entrega pendente?
```

Isso evita que qualquer pessoa que conheça um e-mail consiga receber um livro indevidamente.

---

# 5. Entidades do banco

## 5.1 Buyer

Representa o comprador.

Campos principais:

```text
id
email
email_normalized
name
phone
created_at
updated_at
```

### Regra

Sempre normalizar o e-mail:

```text
Patrick@Email.COM
```

vira:

```text
patrick@email.com
```

O banco deve possuir índice/unique constraint em `email_normalized`.

---

# 6. Order

Representa a compra.

```text
id
external_order_id
buyer_id
product_code
product_name
amount
status
created_at
updated_at
paid_at
metadata
```

Status:

```text
PENDING
PAID
CANCELLED
REFUNDED
CHARGEBACK
```

Somente compras `PAID` devem liberar a geração/entrega do produto.

---

# 7. Book

Representa a unidade digital gerada.

```text
id
buyer_id
order_id
template_id
status
file_path
file_url
generation_started_at
generated_at
delivered_at
created_at
updated_at
```

Status:

```text
PENDING
GENERATING
READY
DELIVERING
DELIVERED
FAILED
CANCELLED
```

### Regra fundamental

Um livro só pode entrar em `READY` depois que a geração foi concluída e o arquivo foi validado.

---

# 8. Book Template

Template estrutural do livro.

```text
id
name
version
status
template_data
created_at
updated_at
```

Exemplo:

```json
{
  "cover": {
    "title": "Deus Conhece o Seu Nome",
    "subtitle": "{{child_name}}"
  },
  "pages": [
    {
      "type": "story",
      "title": "Olá, {{child_name}}",
      "content": "..."
    }
  ]
}
```

O template deve possuir versionamento.

Exemplo:

```text
deus-conhece-seu-nome
v1
v2
v3
```

Livros já gerados não devem mudar retroativamente quando um template novo for publicado.

---

# 9. Communication Template

Separar o template do livro do template de comunicação.

Exemplo:

```text
id
code
name
channel
event
version
content
variables
status
created_at
updated_at
```

### Códigos sugeridos

```text
PURCHASE_CONFIRMED
BOOK_GENERATING
BOOK_READY
DELIVERY_STARTED
DELIVERY_COMPLETED
DELIVERY_FAILED
REMINDER_BOOK_READY
SUPPORT_REQUESTED
```

### Exemplo

```text
Code:
BOOK_READY

Content:

Olá, {{buyer_name}}! ❤️

O livro personalizado "{{book_name}}" já está pronto.

Acesse aqui:
{{delivery_url}}
```

---

# 10. Sistema de variáveis

Os templates devem utilizar placeholders.

Exemplo:

```text
{{buyer_name}}
{{child_name}}
{{book_name}}
{{delivery_url}}
{{order_id}}
```

O backend deve validar se todas as variáveis utilizadas pelo template existem.

### Exemplo inválido

```text
Olá {{buyer_name}}!

Seu livro de {{unknown_variable}} está pronto.
```

A publicação deve ser bloqueada porque:

```text
unknown_variable
```

não está no catálogo permitido.

---

# 11. Catálogo de variáveis

Criar uma definição central:

```text
buyer_name
buyer_email
buyer_phone
child_name
book_name
book_id
order_id
delivery_url
support_url
```

Cada template declara suas variáveis permitidas.

Exemplo:

```json
{
  "required": [
    "buyer_name",
    "book_name",
    "delivery_url"
  ]
}
```

---

# 12. Validação de disponibilidade

Criar endpoint:

```http
POST /api/v1/books/availability
```

Request:

```json
{
  "email": "cliente@email.com"
}
```

Response possível:

```json
{
  "available": true,
  "book_id": "uuid",
  "status": "READY",
  "delivery_available": true
}
```

Caso não exista:

```json
{
  "available": false,
  "reason": "BOOK_NOT_FOUND"
}
```

Possíveis razões:

```text
BUYER_NOT_FOUND
ORDER_NOT_FOUND
ORDER_NOT_PAID
BOOK_NOT_FOUND
BOOK_GENERATING
BOOK_FAILED
BOOK_ALREADY_DELIVERED
```

---

# 13. Regra de segurança para consulta por e-mail

Não retornar informações sensíveis somente porque o usuário informou um e-mail.

Idealmente, a validação pública deve exigir uma segunda informação:

```text
email + token
```

ou:

```text
email + código recebido
```

Fluxo:

```text
1. Usuário informa e-mail.
2. Backend verifica se existe compra.
3. Backend gera código temporário.
4. Código é enviado para o canal autorizado.
5. Usuário confirma código.
6. Backend libera acesso ao livro.
```

Isso reduz risco de exposição de dados e download indevido.

---

# 14. Geração do livro

Fluxo:

```text
Compra PAID
     ↓
Criar Book
     ↓
Selecionar Book Template
     ↓
Validar dados do comprador
     ↓
Renderizar conteúdo
     ↓
Gerar PDF
     ↓
Validar PDF
     ↓
Salvar arquivo
     ↓
Book = READY
     ↓
Disparar comunicação BOOK_READY
```

A geração deve ser idempotente.

Se o mesmo evento for processado duas vezes:

```text
não gerar dois livros.
```

---

# 15. Identificador de idempotência

Eventos externos devem possuir:

```text
event_id
```

Antes de processar:

```text
event_id já processado?
```

Se sim:

```text
retornar sucesso
sem executar novamente.
```

Criar tabela:

```text
processed_events

id
event_id
event_type
payload
processed_at
```

Com:

```text
UNIQUE(event_id)
```

---

# 16. Comunicação

A comunicação deve ser orientada a eventos.

Exemplo:

```text
ORDER_PAID
    ↓
BOOK_GENERATION_REQUESTED
    ↓
BOOK_READY
    ↓
DELIVERY_REQUESTED
    ↓
DELIVERY_COMPLETED
```

Cada evento pode gerar uma ou mais mensagens.

---

# 17. Evolution API

Criar um serviço isolado:

```text
EvolutionService
```

Responsável exclusivamente por conversar com a Evolution API.

Não colocar chamadas HTTP da Evolution dentro das regras de negócio.

Exemplo conceitual:

```python
evolution.send_text(
    phone=buyer.phone,
    message=message
)
```

O restante da aplicação não precisa conhecer:

```text
URL
API key
instance
headers
```

da Evolution.

Tudo fica em configuração.

---

# 18. Configuração da Evolution

`.env`:

```env
EVOLUTION_API_URL=http://evolution-api:8080
EVOLUTION_API_KEY=
EVOLUTION_INSTANCE=
```

Nunca colocar essas credenciais no código.

---

# 19. Message

Registrar cada mensagem.

```text
id
buyer_id
book_id
template_id
channel
destination
content
status
external_message_id
attempts
error_message
scheduled_at
sent_at
created_at
updated_at
```

Status:

```text
PENDING
PROCESSING
SENT
DELIVERED
FAILED
CANCELLED
```

---

# 20. Delivery

Separar entrega do livro da mensagem.

```text
id
book_id
buyer_id
channel
status
destination
delivery_url
attempts
last_error
created_at
updated_at
completed_at
```

Isso permite futuramente suportar:

```text
WhatsApp
E-mail
Área do cliente
Download
```

sem alterar o domínio do livro.

---

# 21. Orquestração

O `CommunicationService` decide:

```text
qual evento aconteceu?
        ↓
qual template deve ser utilizado?
        ↓
quais variáveis precisam ser preenchidas?
        ↓
qual canal?
        ↓
qual destinatário?
        ↓
quando enviar?
```

Exemplo:

```text
BOOK_READY
    ↓
buscar BOOK_READY template
    ↓
montar variáveis
    ↓
validar template
    ↓
criar Message
    ↓
enviar para worker
    ↓
Evolution API
```

---

# 22. Worker de mensagens

Não é recomendado que a requisição HTTP fique esperando a Evolution API.

Evitar:

```text
POST /books/generate

gera livro
↓
envia WhatsApp
↓
espera Evolution
↓
responde
```

Preferir:

```text
POST /books/generate
        ↓
cria job
        ↓
HTTP 202
        ↓
worker processa
        ↓
Evolution API
```

Na primeira versão, o worker pode ser um processo separado.

Posteriormente:

```text
FastAPI
   ↓
Redis/RabbitMQ
   ↓
Workers
```

---

# 23. Retry

Falhas temporárias devem possuir retry.

Exemplo:

```text
tentativa 1 → falhou
aguarda
tentativa 2 → falhou
aguarda
tentativa 3 → sucesso
```

Backoff:

```text
1 minuto
5 minutos
15 minutos
30 minutos
```

Depois do limite:

```text
FAILED
```

E registrar o erro.

---

# 24. Webhooks da Evolution

Criar:

```http
POST /api/v1/webhooks/evolution
```

Receber eventos como:

```text
message.sent
message.delivered
message.failed
message.received
```

O backend deve correlacionar:

```text
external_message_id
```

com:

```text
Message.id
```

Nunca confiar somente no texto da mensagem para fazer essa correlação.

---

# 25. Webhook de compra

Criar:

```http
POST /api/v1/webhooks/orders
```

Fluxo:

```text
Checkout
   ↓
Webhook
   ↓
validar assinatura
   ↓
idempotência
   ↓
buscar/criar Buyer
   ↓
criar Order
   ↓
se PAID
   ↓
criar Book
   ↓
disparar geração
```

A implementação específica da validação de assinatura depende do gateway utilizado.

---

# 26. Estados do pedido

```text
PENDING
   ↓
PAID
   ↓
BOOK_CREATED
   ↓
BOOK_GENERATING
   ↓
BOOK_READY
   ↓
DELIVERY_PENDING
   ↓
DELIVERED
```

Falhas:

```text
BOOK_GENERATION_FAILED
DELIVERY_FAILED
```

Não misturar estado de pedido com estado de livro.

---

# 27. API sugerida

## Buyers

```http
GET /api/v1/buyers/{id}
```

## Orders

```http
POST /api/v1/orders
GET /api/v1/orders/{id}
```

## Books

```http
POST /api/v1/books/generate
GET /api/v1/books/{id}
POST /api/v1/books/availability
GET /api/v1/books/{id}/download
```

## Templates

```http
POST /api/v1/templates/books
GET /api/v1/templates/books
POST /api/v1/templates/books/{id}/validate
POST /api/v1/templates/books/{id}/publish

POST /api/v1/templates/messages
GET /api/v1/templates/messages
POST /api/v1/templates/messages/{id}/validate
POST /api/v1/templates/messages/{id}/publish
```

## Messages

```http
POST /api/v1/messages
GET /api/v1/messages/{id}
POST /api/v1/messages/{id}/retry
```

## Webhooks

```http
POST /api/v1/webhooks/orders
POST /api/v1/webhooks/evolution
```

---

# 28. Validação de template

Criar um parser simples para detectar:

```text
{{variavel}}
```

Exemplo:

```text
Olá {{buyer_name}}.
Seu livro {{book_name}} está pronto.
```

Extrair:

```text
buyer_name
book_name
```

Comparar com:

```text
allowed_variables
```

Resultado:

```json
{
  "valid": true,
  "variables": [
    "buyer_name",
    "book_name"
  ]
}
```

Caso inválido:

```json
{
  "valid": false,
  "errors": [
    {
      "variable": "unknown",
      "reason": "VARIABLE_NOT_ALLOWED"
    }
  ]
}
```

---

# 29. Preview de template

Adicionar:

```http
POST /api/v1/templates/messages/{id}/preview
```

Request:

```json
{
  "buyer_name": "João",
  "child_name": "Maria",
  "book_name": "Deus Conhece o Seu Nome",
  "delivery_url": "https://..."
}
```

Response:

```json
{
  "content": "Olá João! ❤️ ..."
}
```

Isso permite testar os templates antes de publicar.

---

# 30. Versionamento

Nunca editar um template publicado diretamente.

Exemplo:

```text
BOOK_READY v1
BOOK_READY v2
BOOK_READY v3
```

Apenas uma versão pode estar:

```text
PUBLISHED
```

Livros/mensagens já processados devem guardar referência à versão utilizada.

---

# 31. Segurança

Obrigatório:

- `.env` para secrets;
- API key da Evolution fora do código;
- CORS configurado;
- validação Pydantic;
- autenticação para endpoints administrativos;
- rate limit no endpoint público de disponibilidade;
- logs sem expor tokens;
- validação de webhook;
- idempotência;
- controle de acesso aos downloads;
- URLs de download assinadas/temporárias quando possível.

Não criar:

```text
GET /books?email=...
```

sem proteção.

---

# 32. Download do livro

O arquivo não deve ficar necessariamente exposto diretamente.

Fluxo:

```text
GET /books/{id}/download
        ↓
validar autorização
        ↓
verificar status READY/DELIVERED
        ↓
gerar URL temporária
        ↓
redirect/download
```

Alternativamente, utilizar storage S3-compatible.

Exemplos:

```text
Cloudflare R2
MinIO
AWS S3
```

Para MVP, o arquivo pode ficar em volume Docker.

---

# 33. PostgreSQL

Banco inicial:

```text
deus_conhece_nome
```

Docker volume:

```text
postgres_data
```

Variáveis:

```env
POSTGRES_DB=deus_conhece_nome
POSTGRES_USER=app
POSTGRES_PASSWORD=
DATABASE_URL=postgresql+psycopg://app:password@postgres:5432/deus_conhece_nome
```

---

# 34. Docker Compose inicial

Estrutura:

```yaml
services:

  api:
    build:
      context: .
      dockerfile: Dockerfile
    restart: unless-stopped
    env_file:
      - .env
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy

  postgres:
    image: postgres:16-alpine
    restart: unless-stopped
    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"]
      interval: 5s
      timeout: 5s
      retries: 10

volumes:
  postgres_data:
```

A Evolution API pode ser adicionada ao mesmo Compose ou permanecer como serviço separado, dependendo da infraestrutura atual.

---

# 35. Dockerfile

Objetivo:

```text
Python slim
↓
instalar requirements
↓
copiar app
↓
executar Uvicorn
```

Comando:

```text
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

---

# 36. Health checks

Criar:

```http
GET /health
```

Resposta:

```json
{
  "status": "ok"
}
```

E:

```http
GET /health/ready
```

que verifica:

```text
PostgreSQL
Evolution API
dependências críticas
```

---

# 37. Observabilidade

Cada operação importante deve possuir:

```text
request_id
event_id
order_id
book_id
message_id
```

Exemplo de log:

```text
INFO BOOK_GENERATION_STARTED
order_id=...
book_id=...
```

Erro:

```text
ERROR MESSAGE_SEND_FAILED
message_id=...
external_message_id=...
error=...
```

Não registrar:

```text
API keys
tokens
senhas
dados desnecessários
```

---

# 38. Fluxo completo da compra

```text
Cliente compra
      ↓
Gateway
      ↓
Webhook
      ↓
FastAPI
      ↓
validar assinatura
      ↓
idempotência
      ↓
Buyer
      ↓
Order = PAID
      ↓
Book = PENDING
      ↓
Job de geração
      ↓
Book = GENERATING
      ↓
gera PDF
      ↓
valida PDF
      ↓
Book = READY
      ↓
evento BOOK_READY
      ↓
CommunicationService
      ↓
Template BOOK_READY
      ↓
renderização
      ↓
Message = PENDING
      ↓
Worker
      ↓
Evolution API
      ↓
WhatsApp
      ↓
webhook Evolution
      ↓
Message = DELIVERED
```

---

# 39. Fluxo de validação do comprador

```text
Usuário informa e-mail
        ↓
normalizar e-mail
        ↓
buscar Buyer
        ↓
buscar Order PAID
        ↓
buscar Book
        ↓
validar status
        ↓
solicitar autenticação adicional
        ↓
liberar acesso
```

---

# 40. Regras de negócio principais

### Regra 1

Compra cancelada/refundada não libera livro.

### Regra 2

Um mesmo pedido não deve gerar dois livros.

### Regra 3

Um mesmo evento externo não pode ser processado duas vezes.

### Regra 4

Template publicado deve ser imutável.

### Regra 5

Livro deve guardar a versão do template utilizada.

### Regra 6

Mensagem deve guardar a versão do template utilizada.

### Regra 7

Falha de WhatsApp não deve invalidar o livro.

### Regra 8

Falha de geração não deve criar mensagem `BOOK_READY`.

### Regra 9

Retry deve ser idempotente.

### Regra 10

Download deve exigir autorização.

---

# 41. MVP — ordem de implementação

## Fase 1 — Infraestrutura

- [ ] Dockerfile
- [ ] docker-compose.yml
- [ ] PostgreSQL
- [ ] FastAPI
- [ ] `.env`
- [ ] health check
- [ ] Alembic

## Fase 2 — Domínio

- [ ] Buyer
- [ ] Order
- [ ] Book
- [ ] BookTemplate
- [ ] CommunicationTemplate
- [ ] Message
- [ ] Delivery
- [ ] ProcessedEvent

## Fase 3 — Compra

- [ ] webhook de compra
- [ ] validação da compra
- [ ] idempotência
- [ ] criação do comprador
- [ ] criação do livro

## Fase 4 — Livro

- [ ] template do livro
- [ ] validação do template
- [ ] engine de variáveis
- [ ] geração do PDF
- [ ] validação do arquivo
- [ ] armazenamento
- [ ] status do livro

## Fase 5 — Comunicação

- [ ] templates
- [ ] validação de variáveis
- [ ] preview
- [ ] versionamento
- [ ] CommunicationService
- [ ] Message
- [ ] retry

## Fase 6 — WhatsApp

- [ ] EvolutionService
- [ ] envio de texto
- [ ] envio de mídia/documento
- [ ] webhook Evolution
- [ ] atualização de status

## Fase 7 — Orquestração

- [ ] worker
- [ ] jobs
- [ ] retry
- [ ] backoff
- [ ] eventos
- [ ] logs estruturados

## Fase 8 — Segurança

- [ ] autenticação administrativa
- [ ] rate limit
- [ ] validação de webhook
- [ ] acesso seguro ao download
- [ ] URLs temporárias

---

# 42. Evolução futura

A arquitetura deve permitir adicionar:

```text
Redis
RabbitMQ
Celery
S3/R2
e-mail
SMS
área do cliente
dashboard administrativo
analytics
```

sem alterar profundamente as entidades centrais.

A principal separação deve ser:

```text
DOMÍNIO
   ↓
SERVIÇOS
   ↓
INFRAESTRUTURA
```

Assim, trocar Evolution API por outro provedor não exige reescrever a lógica de entrega.

---

# 43. Decisão arquitetural recomendada

Para o MVP:

```text
FastAPI
PostgreSQL
SQLAlchemy
Alembic
Docker
Evolution API
Worker Python
```

Não adicionar Redis/RabbitMQ imediatamente se o volume inicial ainda for baixo.

A aplicação deve, porém, ter uma abstração de jobs:

```python
JobQueue
```

permitindo começar com:

```text
Local/Database Queue
```

e posteriormente migrar para:

```text
Redis/RQ
```

ou:

```text
RabbitMQ/Celery
```

sem modificar o domínio.

---

# 44. Resultado esperado

Ao final, o sistema deverá ser capaz de executar este processo de ponta a ponta:

```text
COMPRA
  ↓
VALIDAÇÃO
  ↓
COMPRADOR
  ↓
PEDIDO
  ↓
LIVRO
  ↓
GERAÇÃO
  ↓
VALIDAÇÃO DO ARQUIVO
  ↓
LIVRO DISPONÍVEL
  ↓
TEMPLATE DE COMUNICAÇÃO
  ↓
VALIDAÇÃO DO TEMPLATE
  ↓
RENDERIZAÇÃO
  ↓
MENSAGEM
  ↓
WORKER
  ↓
EVOLUTION API
  ↓
WHATSAPP
  ↓
CONFIRMAÇÃO
  ↓
ENTREGA
```

O ponto central da arquitetura é **não tratar o envio do WhatsApp como a entrega em si**. O livro, a autorização do comprador, a geração, a mensagem e a entrega devem possuir estados próprios. Isso torna o sistema rastreável, idempotente e preparado para escalar.
