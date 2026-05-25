async def test_get_my_business(client, business):
    r = await client.get("/businesses/me")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Test Plumbing"
    assert body["twilio_number"] == "+15550001000"
    assert "owner_auth0_id" not in body  # not exposed in response schema


async def test_patch_business(client, business):
    r = await client.patch(
        "/businesses/me",
        json={"name": "Renamed Plumbing", "voice_greeting": "Hello!"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Renamed Plumbing"
    assert body["voice_greeting"] == "Hello!"
    # Untouched field unchanged
    assert body["address"] == "1 Test St"


async def test_patch_business_partial(client, business):
    """Only provided fields are updated; missing ones aren't nulled."""
    r = await client.patch("/businesses/me", json={"address": "2 New St"})
    assert r.status_code == 200
    body = r.json()
    assert body["address"] == "2 New St"
    assert body["name"] == "Test Plumbing"
