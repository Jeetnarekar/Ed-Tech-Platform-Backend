import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_check_endpoint(client: AsyncClient):
    """
    Tests that the health check endpoint returns 200 OK
    and includes status, timestamp, duration, and component statuses.
    """
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    
    data = response.json()
    assert "status" in data
    assert "timestamp" in data
    assert "duration_seconds" in data
    assert "components" in data
    
    # Since our conftest stub overrides get_async_db and get_redis
    # to mock databases/sessions, both should respond as healthy.
    assert data["status"] == "healthy"
    assert data["components"]["database"] == "healthy"
    assert data["components"]["redis"] == "healthy"
