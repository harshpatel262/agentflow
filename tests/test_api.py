import pytest
from fastapi.testclient import TestClient

from agentflow.api.main import create_app

INVOICE = "Invoice INV-1042 from Acme Corp. Amount due: $1,875.50 USD by 2026-07-01."
UNCLEAR = "This ambiguous document mentions some kind of payment, maybe."


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("AGENTFLOW_MOCK_MODE", "true")
    from agentflow.config import get_settings

    get_settings.cache_clear()
    return TestClient(create_app())


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_straight_through_workflow(client):
    response = client.post("/workflows", json={"document": INVOICE})
    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "completed"
    assert body["awaiting_human_review"] is False


def test_review_lifecycle(client):
    started = client.post("/workflows", json={"document": UNCLEAR}).json()
    assert started["status"] == "needs_review"
    workflow_id = started["workflow_id"]

    fetched = client.get(f"/workflows/{workflow_id}").json()
    assert fetched["awaiting_human_review"] is True

    resolved = client.post(
        f"/workflows/{workflow_id}/decision",
        json={"approved": True, "notes": "verified manually"},
    ).json()
    assert resolved["status"] == "completed"

    # a second decision on a finished workflow is rejected
    again = client.post(f"/workflows/{workflow_id}/decision", json={"approved": True})
    assert again.status_code == 409


def test_unknown_workflow_returns_404(client):
    assert client.get("/workflows/nope").status_code == 404


def test_streaming_emits_agent_updates(client):
    with client.stream("POST", "/workflows/stream", json={"document": INVOICE}) as response:
        text = "".join(response.iter_text())
    assert "event: started" in text
    assert "event: agent_update" in text
    assert "event: done" in text
