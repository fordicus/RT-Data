from fastapi.testclient import TestClient
from backend.app import app

client = TestClient(app)

def test_get_tick_data():
	response = client.get("/api/tick?symbol=UNIUSDC&date=2025-05-17")
	assert response.status_code == 200
	data = response.json()
	assert isinstance(data, list)
	assert all("time" in d and "value" in d for d in data)