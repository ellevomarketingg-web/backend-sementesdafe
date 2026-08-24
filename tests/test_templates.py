import pytest
import httpx
from app.services.template_service import TemplateService


def test_template_variable_extraction():
    text = "Olá {{buyer_name}}! O livro {{book_name}} para {{child_name}} está em {{delivery_url}}."
    vars_found = TemplateService.extract_variables(text)
    assert vars_found == ["buyer_name", "book_name", "child_name", "delivery_url"]


def test_template_variable_validation_valid():
    text = "Olá {{buyer_name}}, acesse {{delivery_url}} para o livro {{book_name}}."
    result = TemplateService.validate_variables(text)
    assert result.valid is True
    assert len(result.errors) == 0


def test_template_variable_validation_invalid():
    text = "Olá {{buyer_name}}, sua compra de {{unknown_secret_variable}} está pronta."
    result = TemplateService.validate_variables(text)
    assert result.valid is False
    assert len(result.errors) == 1
    assert result.errors[0].variable == "unknown_secret_variable"
    assert result.errors[0].reason == "VARIABLE_NOT_ALLOWED"


def test_template_rendering():
    text = "Olá {{buyer_name}}, o livro de {{child_name}} está pronto em {{delivery_url}}!"
    context = {
        "buyer_name": "Maria Silva",
        "child_name": "Gabriel",
        "delivery_url": "https://deusconheceoseunome.com.br/d/123",
    }
    rendered = TemplateService.render(text, context)
    assert "Olá Maria Silva" in rendered
    assert "livro de Gabriel" in rendered
    assert "https://deusconheceoseunome.com.br/d/123" in rendered


@pytest.mark.asyncio
async def test_communication_template_api_lifecycle(client: httpx.AsyncClient, admin_headers: dict):
    # 1. Create communication template
    payload = {
        "code": "BOOK_DELIVERED_TEST",
        "name": "Entrega Concluída Teste",
        "channel": "WHATSAPP",
        "event": "delivery.completed",
        "content": "Olá {{buyer_name}}! Seu livro {{book_name}} foi entregue.",
        "version": 1,
    }
    create_res = await client.post("/api/v1/templates/messages", json=payload, headers=admin_headers)
    assert create_res.status_code == 201
    created_data = create_res.json()
    tmpl_id = created_data["id"]
    assert created_data["status"] == "DRAFT"

    # 2. Preview template
    preview_payload = {
        "variables": {
            "buyer_name": "Ana Paula",
            "book_name": "Deus Conhece o Seu Nome",
        }
    }
    preview_res = await client.post(f"/api/v1/templates/messages/{tmpl_id}/preview", json=preview_payload, headers=admin_headers)
    assert preview_res.status_code == 200
    assert "Olá Ana Paula! Seu livro Deus Conhece o Seu Nome foi entregue." in preview_res.json()["rendered_content"]

    # 3. Publish template
    publish_res = await client.post(f"/api/v1/templates/messages/{tmpl_id}/publish", headers=admin_headers)
    assert publish_res.status_code == 200
    assert publish_res.json()["status"] == "PUBLISHED"


@pytest.mark.asyncio
async def test_communication_template_creation_rejects_invalid_variable(client: httpx.AsyncClient, admin_headers: dict):
    payload = {
        "code": "INVALID_TMPL",
        "name": "Template Inválido",
        "channel": "WHATSAPP",
        "event": "test.invalid",
        "content": "Olá {{hacker_injection}}",
        "version": 1,
    }
    res = await client.post("/api/v1/templates/messages", json=payload, headers=admin_headers)
    assert res.status_code == 400
    assert "hacker_injection" in res.json()["detail"]
