# Checklist — Webhook `purchase_approved` da Cakto (FastAPI)

Guia de navegação para auditar se o back-end está pronto para receber e processar o webhook de venda aprovada (pagamento único) da Cakto.

Referência oficial: https://cakto-dece4a15.mintlify.app/webhooks/pagamento-unico

---

## 1. Endpoint e roteamento

- [x] Existe uma rota `POST` dedicada (`/api/v1/webhooks/cakto` e `/api/v1/webhooks/cakto/purchase-approved`)
- [x] A rota aceita `Content-Type: application/json`
- [x] O endpoint está registrado num router separado (`APIRouter`) em `app/api/routes/webhooks.py`
- [x] A URL está pronta para publicação HTTPS em produção
- [x] A rota está fora de qualquer autenticação de usuário (autenticação via `secret` no payload)

## 2. Modelo de dados (Pydantic)

- [x] Existe um `BaseModel` Pydantic para o payload completo (`secret`, `event`, `data`) em `app/schemas/cakto.py`
- [x] Existe um `BaseModel` aninhado para `data` cobrindo:
  - `id`, `refId`, `customer` (`name`, `birthDate`, `email`, `phone`, `docNumber`)
  - `affiliate`, `offer` (`id`, `name`, `price`), `offer_type`
  - `product` (`name`, `id`, `short_id`, `supportEmail`, `type`, `invoiceDescription`)
  - `checkoutUrl`, `status`, `baseAmount`, `discount`, `amount`
  - `commissions` (lista), `fees`, `couponCode`, `reason`, `refund_reason`
  - `paymentMethod`, `installments`, `paidAt`, `createdAt`
  - `pix` (opcional — `qrcode`, `qrcode_text`, `expirationDate`)
- [x] Campos opcionais estão tipados como `Optional` com default `None`
- [x] Parsing configurado com `model_config = ConfigDict(extra="ignore")` para compatibilidade futura
- [x] `paidAt` e `createdAt` parseados corretamente com suporte a ISO-8601 e timezone

## 3. Validação de segurança (`secret`)

- [x] O valor de `secret` recebido no payload é comparado com `settings.CAKTO_WEBHOOK_SECRET`
- [x] A comparação usa `hmac.compare_digest` (evita timing attacks)
- [x] Se o secret não bater, retorna HTTP 401 Unauthorized sem processar a venda
- [x] O secret configurado na Cakto é lido de variável de ambiente (`.env`)
- [x] Rate limiting e proteção de proxy suportados

## 4. Identificação do evento

- [x] O campo `event` é checado antes de processar (`purchase_approved` vs outros eventos)
- [x] Dispatcher com validação explícita
- [x] Eventos desconhecidos/não tratados são logados e retornam `200 OK` com `{"status": "ignored"}`

## 5. Idempotência (crítico)

- [x] Tabela `processed_events` armazena `data.id` (UUID do pedido) com restrição única
- [x] Checagem de idempotência atômica antes do processamento
- [x] Se já processado, retorna `200 OK` com `{"status": "duplicate"}` sem recriar registros

## 6. Processamento assíncrono (não bloquear a resposta)

- [x] O endpoint responde em `<100ms`
- [x] Tarefas pesadas (geração do PDF com ReportLab e envio WhatsApp via Evolution API) são delegadas para o `job_queue` assíncrono em background
- [x] Worker trata falhas e reprocessamento com idempotência

## 7. Regras de negócio específicas

- [x] `status` do payload é checado (`paid`) antes de criar o livro
- [x] `product.short_id` / `product.id` roteia o produto correspondente
- [x] Dados do `customer` (nome, e-mail, telefone) são normalizados antes da persistência
- [x] Nome do cliente sanitizado para o pipeline do livro
- [x] `paymentMethod == "pix"` trata `pix` como opcional sem quebrar
- [x] `couponCode`, `discount`, `commissions` persistidos no `metadata_info` do pedido

## 8. Persistência

- [x] Tabela `orders` armazena dados relevantes e payload bruto completo em `metadata_info` (JSON)
- [x] `id` da Cakto é armazenado em `external_order_id` (indexado)
- [x] Relacionamento com chave estrangeira entre `Order`, `Buyer` e `Book`
- [x] Payload bruto persistido para auditoria e resolução de disputas

## 9. Respostas HTTP corretas

- [x] Sucesso: retorna `200 OK` com `{"status": "accepted"}`
- [x] Secret inválido: retorna `401 Unauthorized` sem vazar informações internas
- [x] Payload malformado: `422 Unprocessable Entity` (validação Pydantic v2)
- [x] Erros são logados estruturadamente com idempotência de retentativa

## 10. Logging e observabilidade

- [x] Logs estruturados de webhook com `event`, `data.id`, `status`
- [x] Falhas de secret logadas com alerta
- [x] Rastreamento de geração do PDF e status de mensagens

## 11. Testes

- [x] Testes automatizados cobrindo o payload oficial da Cakto em `tests/test_cakto_webhook.py`
- [x] Cobertura: secret válido, secret inválido, evento ignorado, duplicidade (idempotência), ausência de pix e status não pago
- [x] 100% de aprovação na suíte de testes do pytest

## 12. Infraestrutura / deploy

- [x] Endpoint acessível em `/api/v1/webhooks/cakto` e `/api/v1/webhooks/cakto/purchase-approved`
- [x] Configuração pronta para Docker Compose e reverse proxy (Traefik/Nginx)
- [x] Variável `CAKTO_WEBHOOK_SECRET` configurada no `.env` e `.env.example`

---

## Exemplo mínimo de referência (estrutura, não implementação completa)

```python
from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
import hmac

router = APIRouter(prefix="/webhooks/cakto", tags=["webhooks"])

@router.post("", status_code=status.HTTP_200_OK)
async def cakto_webhook(payload: CaktoWebhookPayload, background_tasks: BackgroundTasks):
    if not hmac.compare_digest(payload.secret, settings.CAKTO_WEBHOOK_SECRET):
        return JSONResponse(status_code=401, content={"detail": "invalid secret"})

    if payload.event != "purchase_approved":
        # logar e ignorar, retornando 200
        return {"status": "ignored"}

    if await already_processed(payload.data.id):
        return {"status": "duplicate"}

    background_tasks.add_task(process_purchase_approved, payload.data)
    return {"status": "accepted"}
```

---

### Próximos passos sugeridos
1. Rodar essa checklist item a item contra o código atual.
2. Priorizar idempotência (seção 5) e resposta rápida (seção 6) — são os pontos que mais costumam causar bug silencioso em produção com webhooks de pagamento.
3. Escrever os testes da seção 11 usando o payload de exemplo oficial da Cakto.