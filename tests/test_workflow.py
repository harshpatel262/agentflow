import uuid

import pytest

from agentflow.config import Settings
from agentflow.graph.builder import build_graph
from agentflow.llm import MockLLM

INVOICE = "Invoice INV-1042 from Acme Corp. Amount due: $1,875.50 USD by 2026-07-01."
UNCLEAR = "This ambiguous document mentions some kind of payment, maybe."


@pytest.fixture
def engine():
    return build_graph(MockLLM(), Settings(mock_mode=True))


def _config():
    return {"configurable": {"thread_id": str(uuid.uuid4())}}


def test_confident_document_completes_straight_through(engine):
    result = engine.invoke({"workflow_id": "t1", "document": INVOICE, "source": "test"}, _config())

    assert result["status"] == "completed"
    assert result["category"] == "invoice"
    assert result["extraction"]["invoice_number"] == "INV-1042"
    agents = [entry["agent"] for entry in result["audit"]]
    assert agents == ["intake", "classifier", "extractor", "validator", "finalizer"]


def test_low_confidence_document_pauses_for_review(engine):
    config = _config()
    engine.invoke({"workflow_id": "t2", "document": UNCLEAR, "source": "test"}, config)

    state = engine.get_state(config)
    assert state.next == ("human_review",)
    assert state.values["confidence"] < 0.8


def test_approved_review_resumes_to_completion(engine):
    config = _config()
    engine.invoke({"workflow_id": "t3", "document": UNCLEAR, "source": "test"}, config)

    engine.update_state(config, {"human_decision": {"approved": True, "notes": "looks fine"}})
    result = engine.invoke(None, config)

    assert result["status"] == "completed"
    agents = [entry["agent"] for entry in result["audit"]]
    assert "human_review" in agents


def test_rejected_review_closes_workflow(engine):
    config = _config()
    engine.invoke({"workflow_id": "t4", "document": UNCLEAR, "source": "test"}, config)

    engine.update_state(config, {"human_decision": {"approved": False, "notes": "bad scan"}})
    result = engine.invoke(None, config)

    assert result["status"] == "rejected"
