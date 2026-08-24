import pytest
import httpx


@pytest.mark.asyncio
async def test_health_check(client: httpx.AsyncClient):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_check(client: httpx.AsyncClient):
    response = await client.get("/health/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["checks"]["database"] == "ok"
    assert data["checks"]["storage"] == "ok"


@pytest.mark.asyncio
async def test_root_route(client: httpx.AsyncClient):
    response = await client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "running"
    assert "/docs" in data["docs"]
