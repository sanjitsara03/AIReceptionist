async def test_list_technicians(client, business):
    r = await client.get("/technicians")
    assert r.status_code == 200
    techs = r.json()
    assert len(techs) == 2
    assert {t["name"] for t in techs} == {"Alice Tester", "Bob Tester"}


async def test_create_technician(client, business):
    r = await client.post("/technicians", json={
        "name": "Carol Tester",
        "phone": "+15550001003",
    })
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Carol Tester"
    assert body["active"] is True

    list_resp = await client.get("/technicians")
    assert len(list_resp.json()) == 3


async def test_update_technician(client, business):
    techs = (await client.get("/technicians")).json()
    tech_id = techs[0]["id"]
    r = await client.patch(f"/technicians/{tech_id}", json={"active": False})
    assert r.status_code == 200
    assert r.json()["active"] is False


async def test_delete_technician(client, business):
    techs = (await client.get("/technicians")).json()
    tech_id = techs[0]["id"]
    r = await client.delete(f"/technicians/{tech_id}")
    assert r.status_code == 204
    remaining = (await client.get("/technicians")).json()
    assert len(remaining) == 1


async def test_update_nonexistent_returns_404(client, business):
    r = await client.patch("/technicians/9999", json={"name": "Nope"})
    assert r.status_code == 404
