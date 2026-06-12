import operator
from typing import Annotated, TypedDict


class WorkflowState(TypedDict, total=False):
    """Shared state threaded through every agent in the graph.

    `audit` uses an additive reducer so each agent appends its own entry
    without clobbering the trail — the full history is reconstructable
    from checkpoints.
    """

    workflow_id: str
    source: str
    document: str

    category: str
    confidence: float
    extraction: dict
    validation: dict

    # received -> classified -> extracted -> validated
    #   -> completed | needs_review -> approved/rejected -> completed
    status: str

    # set by the API when a reviewer resolves an interrupted workflow
    human_decision: dict

    audit: Annotated[list[dict], operator.add]
