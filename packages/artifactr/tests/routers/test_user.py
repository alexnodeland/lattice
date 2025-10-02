from fastapi.testclient import TestClient


def test_create_user(client: TestClient):
    response = client.post(
        "/users/", json={"name": "John Doe", "email": "john.doe@example.com"}
    )
    assert response.status_code == 200

    data = response.json()
    assert data["name"] == "John Doe"
    assert data["email"] == "john.doe@example.com"


def test_get_user(client: TestClient):
    response = client.post(
        "/users/", json={"name": "John Doe", "email": "john.doe@example.com"}
    )
    assert response.status_code == 200

    data = response.json()
    user_id = data["id"]

    response = client.get(f"/users/{user_id}")
    assert response.status_code == 200
    assert response.json() == {
        "id": user_id,
        "name": "John Doe",
        "email": "john.doe@example.com",
    }


def test_update_user(client: TestClient):
    response = client.post(
        "/users/", json={"name": "John Doe", "email": "john.doe@example.com"}
    )
    assert response.status_code == 200

    data = response.json()
    user_id = data["id"]

    response = client.put(f"/users/{user_id}", json={"name": "Jane Doe"})
    assert response.status_code == 200
    assert response.json() == {
        "id": user_id,
        "name": "Jane Doe",
        "email": "john.doe@example.com",
    }


def test_delete_user(client: TestClient):
    response = client.post(
        "/users/", json={"name": "John Doe", "email": "john.doe@example.com"}
    )
    assert response.status_code == 200

    data = response.json()
    user_id = data["id"]

    response = client.delete(f"/users/{user_id}")
    assert response.status_code == 200

    response = client.get(f"/users/{user_id}")
    assert response.status_code == 404
