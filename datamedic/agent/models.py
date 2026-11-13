from datetime import date
from typing import Literal, TypedDict
from pydantic import BaseModel, ConfigDict, Field

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Alert(StrictModel):
    text: str = Field(min_length=1, max_length=4000)
    purchase_date: date = date(2018,8,15)
    budget: int = Field(default=12, ge=0, le=100)

class Hypothesis(StrictModel):
    category: str
    description: str
    status: Literal['SUPPORTED','WEAKENED','FALSIFIED','UNRESOLVED'] = 'UNRESOLVED'
    rationale: str = 'Awaiting evidence.'
    evidence: list[str] = Field(default_factory=list)

class ToolRequest(StrictModel):
    tool: str
    arguments: dict = Field(default_factory=dict)

class Report(StrictModel):
    verdict: Literal['MISSING_INGESTION','ESCALATE_AMBIGUOUS']
    reason: str
    evidence: list[str]
    next_manual_check: str
    points_spent: int
    points_remaining: int
    planner: str = 'deterministic-olist-v1'
    model_tokens: int = 0

class State(TypedDict):
    alert: dict
    remaining: int
    hypotheses: list[dict]
    history: list[dict]
    request: dict | None
    stop: str
    report: dict
