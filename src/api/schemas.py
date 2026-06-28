
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class InvestigationRequest(BaseModel):
    node_name: str = Field(..., min_length=1)
    namespace: str = Field(..., min_length=1)
    scenario_name: Optional[str] = None
    apply_scenario: bool = False
    reset_namespace: bool = False
    demo_seed_metrics: bool = False
    wait_seconds: int = Field(default=45, ge=0, le=180)


class StageStatus(BaseModel):
    key: str
    label: str
    status: str = "pending"


class InvestigationJobResponse(BaseModel):
    job_id: str
    status: str
    stages: List[StageStatus]
    request: Dict[str, Any]
    report: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class FeedbackRequest(BaseModel):
    name: str = "Anonymous"
    email: Optional[str] = None
    feedback_type: str = "general"
    rating: Optional[int] = None
    message: str = Field(..., min_length=2)

