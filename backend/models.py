"""Data types shared by the agent team."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

AgentName = Literal["boss", "inventory", "accounting", "facilities", "customer_service"]
TicketStatus = Literal["open", "in_progress", "waiting_approval", "closed"]


class TraceEvent(BaseModel):
    """One step of team activity, streamed to the dashboard."""

    id: int = 0
    at: datetime = Field(default_factory=datetime.now)
    ticket_id: int
    agent: AgentName
    kind: Literal["start", "delegate", "reply", "tool", "tool_result", "error", "done"]
    target: AgentName | None = None
    tool: str | None = None
    text: str


@dataclass
class TeamDeps:
    """Run state shared by every agent working one ticket."""

    ticket_id: int
    depth: int = 0
    max_depth: int = 3
    max_delegations: int = 8
    stack: list[AgentName] = field(default_factory=list)
    workload: dict[str, int] = field(default_factory=dict)
    trace: list[TraceEvent] = field(default_factory=list)

    def log(self, agent: AgentName, kind: str, text: str,
            target: AgentName | None = None, tool: str | None = None) -> None:
        self.trace.append(TraceEvent(id=len(self.trace) + 1, ticket_id=self.ticket_id, agent=agent,
                                     kind=kind, target=target, tool=tool, text=text))


class AgentReply(BaseModel):
    """What a specialist hands back to whoever asked."""

    agent: AgentName
    summary: str = Field(description="Plain-English answer to the task, in 1-3 sentences.")
    facts: list[str] = Field(default_factory=list, description="Numbers and facts read from tools, never invented.")
    actions_taken: list[str] = Field(default_factory=list, description="Drafts, approval requests or ticket updates made.")
    approval_ids: list[int] = Field(default_factory=list, description="Payment approvals now waiting for a human.")
    draft_ids: list[int] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list, description="Risks, blockers or missing information.")


class TicketResolution(BaseModel):
    """The Boss's final call on one ticket."""

    ticket_id: int
    decision: str = Field(description="The final call, in plain English.")
    rationale: str
    delegated_to: list[AgentName] = Field(default_factory=list)
    approval_ids: list[int] = Field(default_factory=list, description="Payments waiting for human approval.")
    draft_ids: list[int] = Field(default_factory=list)
    ticket_status: TicketStatus
    next_steps: list[str] = Field(default_factory=list)
