from typing import Annotated, Literal

from pydantic import BaseModel, Field

from plan_based_researcher.policy import Policy

HitIndex = Annotated[int, Field(ge=0, le=Policy.search_max_results - 1)]


class EvalResult(BaseModel):
    status: Literal["pass", "retry", "fail"]
    reasoning: str = Field(default="", description="English evaluator reasoning.")
    likely_in_paper: str = Field(
        default="",
        description=(
            "Retrieve T3: na, yes, no, or unknown. Empty is resolved from status."
        ),
    )
    feedback: str = Field(description="English evaluator feedback.")
    plan_inadequate: bool = False


class RetrieveJudgeVerdict(BaseModel):
    reasoning: str = Field(description="English reasoning.")
    likely_in_paper: Literal["na", "yes", "no", "unknown"] = Field(
        description="na, yes, no, or unknown."
    )
    feedback: str = Field(description="English evaluator feedback.")


class PaperKey(BaseModel):
    arxiv_id: str
    version: str = ""


class SearchStepVerdict(BaseModel):
    step_index: int
    passed: bool
    plan_inadequate: bool = False
    feedback: str = Field(description="English evaluator feedback for this search step.")
    ranked_hit_indices: list[HitIndex] = Field(default_factory=list)


class SearchWaveJudgement(BaseModel):
    verdicts: list[SearchStepVerdict]
    reasoning: str = Field(description="English overall reasoning for the search wave.")
