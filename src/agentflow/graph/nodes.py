"""Agent node implementations.

Each agent is a pure function over WorkflowState: it reads context, calls
the LLM through the injected client, and returns a partial state update
plus an audit entry. No agent touches the API layer or storage directly.
"""

from __future__ import annotations

from datetime import datetime, timezone

from agentflow.llm import LLMClient, parse_json_response
from agentflow.graph.state import WorkflowState

CLASSIFIER_SYSTEM = """You are a document classification agent in a business process \
automation pipeline. Classify the document into one of: invoice, purchase_order, \
contract, expense_report, support_request, other. Respond with JSON only: \
{"category": str, "confidence": float between 0 and 1, "reasoning": str}."""

EXTRACTOR_SYSTEM = """You are a structured data extraction agent. Given a document and \
its category, extract the key fields a downstream system of record needs (for an \
invoice: vendor, invoice_number, amount, currency, due_date). Respond with a flat \
JSON object only. Use null for fields you cannot find — never guess values."""

VALIDATOR_SYSTEM = """You are a validation agent. Given extracted fields, check internal \
consistency (amounts are positive numbers, dates are plausible, required fields are \
present). Respond with JSON only: {"valid": bool, "issues": [str]}."""


def _audit(agent: str, summary: str) -> dict:
    return {
        "agent": agent,
        "summary": summary,
        "at": datetime.now(timezone.utc).isoformat(),
    }


def intake(state: WorkflowState) -> dict:
    return {
        "status": "received",
        "audit": [_audit("intake", f"received document from {state.get('source', 'api')}")],
    }


def classify(state: WorkflowState, llm: LLMClient) -> dict:
    raw = llm.complete(CLASSIFIER_SYSTEM, state["document"])
    result = parse_json_response(raw)
    category = result.get("category", "other")
    confidence = float(result.get("confidence", 0.0))
    return {
        "category": category,
        "confidence": confidence,
        "status": "classified",
        "audit": [_audit("classifier", f"category={category} confidence={confidence:.2f}")],
    }


def extract(state: WorkflowState, llm: LLMClient) -> dict:
    prompt = f"Category: {state['category']}\n\nDocument:\n{state['document']}"
    extraction = parse_json_response(llm.complete(EXTRACTOR_SYSTEM, prompt))
    return {
        "extraction": extraction,
        "status": "extracted",
        "audit": [_audit("extractor", f"extracted {len(extraction)} fields")],
    }


def validate(state: WorkflowState, llm: LLMClient) -> dict:
    prompt = f"Extracted fields:\n{state['extraction']}"
    validation = parse_json_response(llm.complete(VALIDATOR_SYSTEM, prompt))
    issues = validation.get("issues", [])
    return {
        "validation": validation,
        "status": "validated",
        "audit": [_audit("validator", f"valid={validation.get('valid')} issues={len(issues)}")],
    }


def human_review(state: WorkflowState) -> dict:
    """Resolution node for workflows paused for a human decision.

    The graph interrupts *before* this node; by the time it runs, the API
    has written `human_decision` into state and resumed execution.
    """
    decision = state.get("human_decision", {})
    approved = bool(decision.get("approved"))
    return {
        "status": "approved" if approved else "rejected",
        "audit": [
            _audit(
                "human_review",
                f"reviewer {'approved' if approved else 'rejected'}: "
                f"{decision.get('notes', 'no notes')}",
            )
        ],
    }


def finalize(state: WorkflowState) -> dict:
    return {
        "status": "completed",
        "audit": [_audit("finalizer", "workflow completed, results published")],
    }


def rejected(state: WorkflowState) -> dict:
    return {
        "status": "rejected",
        "audit": [_audit("finalizer", "workflow closed as rejected")],
    }
