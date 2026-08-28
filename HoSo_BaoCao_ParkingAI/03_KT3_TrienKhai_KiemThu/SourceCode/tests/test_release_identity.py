import main


def test_root_health_exposes_non_secret_release_identity(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["release_id"] == main.RELEASE_ID
