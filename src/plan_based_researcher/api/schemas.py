from pydantic import BaseModel, Field


class ResearchRequest(BaseModel):
    query: str
    thread_id: str = Field(min_length=1)


class Citation(BaseModel):
    n: int
    arxiv_id: str
    title: str
    year: int
    url: str
    excerpt: str
    chunk_id: str


class PlanStep(BaseModel):
    agent: str  # REGISTRY key; validated later after parse, not here
    task: str = Field(
        description="English research or writing goal, even if the student query is not English."
    )
    reasoning: str = Field(description="English rationale for this step.")
    historical: bool = False


class ResearchPlan(BaseModel):
    steps: list[PlanStep]


class GateDecision(BaseModel):
    in_domain: bool
    language: str
    reason: str = Field(
        description="Student-facing; match the query language (BCP-47 from language)."
    )
