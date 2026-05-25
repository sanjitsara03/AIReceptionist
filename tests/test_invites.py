from app.config import settings


async def test_create_invite_requires_admin_secret(client, business):
    r = await client.post(f"/invites?business_id={business.id}")
    assert r.status_code == 422  # X-Admin-Secret missing


async def test_create_invite_wrong_secret(client, business):
    r = await client.post(
        f"/invites?business_id={business.id}",
        headers={"X-Admin-Secret": "wrong"},
    )
    assert r.status_code == 403


async def test_create_and_fetch_invite(client, business):
    r = await client.post(
        f"/invites?business_id={business.id}",
        headers={"X-Admin-Secret": settings.admin_secret},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["business_name"] == "Test Plumbing"
    assert body["claimed"] is False
    token = body["token"]

    # Public lookup
    r2 = await client.get(f"/invites/{token}")
    assert r2.status_code == 200
    assert r2.json()["business_name"] == "Test Plumbing"


async def test_invite_not_found(client, business):
    r = await client.get("/invites/does-not-exist")
    assert r.status_code == 404
