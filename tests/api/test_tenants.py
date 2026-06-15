import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_tenant_lifecycle(client: AsyncClient):
    """
    Tests registering, retrieving, and updating a tenant.
    Exercises the API, Service, Repository, Model, and Schema layers.
    """
    # 1. Create a tenant
    payload = {
        "name": "Apex Coaching Institute",
        "subdomain": "apex-coaching",
        "settings": {"primary_color": "#ff0000", "allow_registration": True}
    }
    
    create_response = await client.post("/api/v1/tenants/", json=payload)
    assert create_response.status_code == 201
    
    tenant_data = create_response.json()
    assert tenant_data["name"] == payload["name"]
    assert tenant_data["subdomain"] == payload["subdomain"]
    assert tenant_data["settings"] == payload["settings"]
    assert "id" in tenant_data
    
    tenant_id = tenant_data["id"]

    # 2. Get tenant by ID
    get_id_response = await client.get(f"/api/v1/tenants/{tenant_id}")
    assert get_id_response.status_code == 200
    assert get_id_response.json()["name"] == payload["name"]

    # 3. Get tenant by subdomain (tests caching behavior)
    get_sub_response = await client.get(f"/api/v1/tenants/subdomain/apex-coaching")
    assert get_sub_response.status_code == 200
    assert get_sub_response.json()["id"] == tenant_id

    # 4. Attempt to create duplicate subdomain (should fail with 400)
    dup_response = await client.post("/api/v1/tenants/", json=payload)
    assert dup_response.status_code == 400
    assert dup_response.json()["error"]["code"] == "SUBDOMAIN_TAKEN"

    # 5. Update tenant settings
    update_payload = {
        "name": "Apex Academy",
        "settings": {"primary_color": "#0000ff"}
    }
    update_response = await client.put(f"/api/v1/tenants/{tenant_id}", json=update_payload)
    assert update_response.status_code == 200
    updated_data = update_response.json()
    assert updated_data["name"] == "Apex Academy"
    assert updated_data["settings"] == {"primary_color": "#0000ff"}
