"""HTTP surface for the workflow engine.

The API owns workflow identity and human-in-the-loop resolution; all
process logic lives in the graph. Checkpointing is per-workflow via
LangGraph thread configs, so paused workflows survive across requests.
"""

from __future__ import annotations

import json
import uuid

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from agentflow import __version__
from agentflow.config import get_settings
from agentflow.graph.builder import build_graph
from agentflow.llm import get_llm


class StartWorkflowRequest(BaseModel):
    document: str = Field(min_length=1, description="Raw document text to process")
    source: str = "api"


class ReviewDecision(BaseModel):
    approved: bool
    notes: str = ""


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AgentFlow", version=__version__)
    engine = build_graph(get_llm(settings), settings)

    # Ordered registry of workflow ids, so the review queue can be listed.
    # The checkpointer stores state per thread but does not enumerate threads;
    # a durable deployment would back this with the checkpointer's store.
    workflow_ids: list[str] = []

    def _config(workflow_id: str) -> dict:
        return {"configurable": {"thread_id": workflow_id}}

    def _snapshot(workflow_id: str) -> dict:
        state = engine.get_state(_config(workflow_id))
        if not state.values:
            raise HTTPException(status_code=404, detail="workflow not found")
        paused = bool(state.next)
        values = state.values
        return {
            "workflow_id": workflow_id,
            "status": "needs_review" if paused else values.get("status"),
            "awaiting_human_review": paused,
            "category": values.get("category"),
            "confidence": values.get("confidence"),
            "extraction": values.get("extraction"),
            "validation": values.get("validation"),
            "audit": values.get("audit", []),
        }

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.post("/workflows", status_code=201)
    def start_workflow(request: StartWorkflowRequest) -> dict:
        workflow_id = str(uuid.uuid4())
        workflow_ids.append(workflow_id)
        engine.invoke(
            {"workflow_id": workflow_id, "document": request.document, "source": request.source},
            _config(workflow_id),
        )
        return _snapshot(workflow_id)

    @app.get("/workflows")
    def list_workflows(
        awaiting_review: bool | None = Query(
            default=None, description="filter to workflows paused for human review"
        ),
    ) -> dict:
        """List workflows, newest first — the backing query for a review queue."""
        items = []
        for wid in reversed(workflow_ids):
            state = engine.get_state(_config(wid))
            if not state.values:
                continue
            paused = bool(state.next)
            if awaiting_review is not None and paused != awaiting_review:
                continue
            values = state.values
            items.append(
                {
                    "workflow_id": wid,
                    "status": "needs_review" if paused else values.get("status"),
                    "awaiting_human_review": paused,
                    "category": values.get("category"),
                    "confidence": values.get("confidence"),
                }
            )
        return {"count": len(items), "workflows": items}

    @app.post("/workflows/stream")
    def stream_workflow(request: StartWorkflowRequest) -> StreamingResponse:
        """Run a workflow, streaming each agent's update as a Server-Sent Event."""
        workflow_id = str(uuid.uuid4())
        workflow_ids.append(workflow_id)

        def event_stream():
            yield f"event: started\ndata: {json.dumps({'workflow_id': workflow_id})}\n\n"
            updates = engine.stream(
                {
                    "workflow_id": workflow_id,
                    "document": request.document,
                    "source": request.source,
                },
                _config(workflow_id),
                stream_mode="updates",
            )
            for update in updates:
                for agent, delta in update.items():
                    payload = {"agent": agent, "status": delta.get("status")}
                    yield f"event: agent_update\ndata: {json.dumps(payload)}\n\n"
            yield f"event: done\ndata: {json.dumps(_snapshot(workflow_id))}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    @app.get("/workflows/{workflow_id}")
    def get_workflow(workflow_id: str) -> dict:
        return _snapshot(workflow_id)

    @app.post("/workflows/{workflow_id}/decision")
    def resolve_workflow(workflow_id: str, decision: ReviewDecision) -> dict:
        state = engine.get_state(_config(workflow_id))
        if not state.values:
            raise HTTPException(status_code=404, detail="workflow not found")
        if not state.next:
            raise HTTPException(status_code=409, detail="workflow is not awaiting review")
        engine.update_state(
            _config(workflow_id),
            {"human_decision": {"approved": decision.approved, "notes": decision.notes}},
        )
        engine.invoke(None, _config(workflow_id))
        return _snapshot(workflow_id)

    return app


app = create_app()
