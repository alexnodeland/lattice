from fastapi.testclient import TestClient


def test_create_thread(client: TestClient):
    """Test creating a new thread."""
    response = client.post(
        "/threads/",
        json={"title": "Test Thread", "description": "This is a test thread"},
    )
    assert response.status_code == 200

    data = response.json()
    assert data["title"] == "Test Thread"
    assert data["description"] == "This is a test thread"
    assert "id" in data
    assert "created_at" in data
    assert "updated_at" in data


def test_get_thread(client: TestClient):
    """Test retrieving a thread by ID."""
    # First create a thread
    response = client.post(
        "/threads/",
        json={"title": "Test Thread", "description": "This is a test thread"},
    )
    assert response.status_code == 200

    data = response.json()
    thread_id = data["id"]

    # Now get the thread by ID
    response = client.get(f"/threads/{thread_id}")
    assert response.status_code == 200

    thread_data = response.json()
    assert thread_data["id"] == thread_id
    assert thread_data["title"] == "Test Thread"
    assert thread_data["description"] == "This is a test thread"
    assert "created_at" in thread_data
    assert "updated_at" in thread_data


def test_update_thread(client: TestClient):
    """Test updating a thread."""
    # First create a thread
    response = client.post(
        "/threads/",
        json={
            "title": "Original Thread",
            "description": "This is the original description",
        },
    )
    assert response.status_code == 200

    data = response.json()
    thread_id = data["id"]

    # Now update the thread
    response = client.put(
        f"/threads/{thread_id}",
        json={
            "title": "Updated Thread",
            "description": "This is the updated description",
        },
    )
    assert response.status_code == 200

    updated_data = response.json()
    assert updated_data["id"] == thread_id
    assert updated_data["title"] == "Updated Thread"
    assert updated_data["description"] == "This is the updated description"

    # Verify via a GET request that the update was persisted
    response = client.get(f"/threads/{thread_id}")
    assert response.status_code == 200
    get_data = response.json()
    assert get_data["title"] == "Updated Thread"


def test_delete_thread(client: TestClient):
    """Test deleting a thread."""
    # First create a thread
    response = client.post(
        "/threads/",
        json={
            "title": "Thread to Delete",
            "description": "This thread will be deleted",
        },
    )
    assert response.status_code == 200

    data = response.json()
    thread_id = data["id"]

    # Now delete the thread
    response = client.delete(f"/threads/{thread_id}")
    assert response.status_code == 200
    assert response.json() == {"message": "Thread deleted"}

    # Verify the thread is gone
    response = client.get(f"/threads/{thread_id}")
    assert response.status_code == 404


def test_thread_not_found(client: TestClient):
    """Test appropriate error responses for non-existent threads."""
    # Try to get a non-existent thread
    response = client.get("/threads/999999")
    assert response.status_code == 404

    # Try to update a non-existent thread
    response = client.put(
        "/threads/999999",
        json={
            "title": "Updated Thread",
            "description": "This is the updated description",
        },
    )
    assert response.status_code == 404

    # Try to delete a non-existent thread
    response = client.delete("/threads/999999")
    assert response.status_code == 404
