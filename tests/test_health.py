async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["data"]["status"] == "ok"
    assert body["error"] is None
