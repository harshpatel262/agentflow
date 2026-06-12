"""Graph assembly.

    intake -> classify -> extract -> validate
                                        |-- straight-through --> finalize
                                        '-- low confidence / invalid
                                              --> [interrupt] human_review
                                                    |-- approved --> finalize
                                                    '-- rejected --> rejected

The interrupt before `human_review` is what makes the engine safe to run
against real business processes: anything the agents are not confident
about stops and waits for a person.
"""

from functools import partial

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from agentflow.config import Settings
from agentflow.graph import nodes
from agentflow.graph.state import WorkflowState
from agentflow.llm import LLMClient


def route_after_validation(state: WorkflowState, threshold: float) -> str:
    valid = bool(state.get("validation", {}).get("valid"))
    confident = state.get("confidence", 0.0) >= threshold
    return "finalize" if valid and confident else "human_review"


def route_after_review(state: WorkflowState) -> str:
    return "finalize" if state.get("status") == "approved" else "rejected"


def build_graph(llm: LLMClient, settings: Settings, checkpointer=None):
    graph = StateGraph(WorkflowState)

    graph.add_node("intake", nodes.intake)
    graph.add_node("classify", partial(nodes.classify, llm=llm))
    graph.add_node("extract", partial(nodes.extract, llm=llm))
    graph.add_node("validate", partial(nodes.validate, llm=llm))
    graph.add_node("human_review", nodes.human_review)
    graph.add_node("finalize", nodes.finalize)
    graph.add_node("rejected", nodes.rejected)

    graph.set_entry_point("intake")
    graph.add_edge("intake", "classify")
    graph.add_edge("classify", "extract")
    graph.add_edge("extract", "validate")
    graph.add_conditional_edges(
        "validate",
        partial(route_after_validation, threshold=settings.review_confidence_threshold),
        {"finalize": "finalize", "human_review": "human_review"},
    )
    graph.add_conditional_edges(
        "human_review",
        route_after_review,
        {"finalize": "finalize", "rejected": "rejected"},
    )
    graph.add_edge("finalize", END)
    graph.add_edge("rejected", END)

    return graph.compile(
        checkpointer=checkpointer or MemorySaver(),
        interrupt_before=["human_review"],
    )
