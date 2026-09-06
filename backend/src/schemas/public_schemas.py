from pydantic import BaseModel
from datetime import datetime


class ScoreSummary(BaseModel):
    total_issues: int
    critical_issues: int
    high_issues: int
    medium_issues: int
    low_issues: int
    total_strengths: int


class Highlight(BaseModel):
    quote: str
    comment: str


class RoastAnalysisResponse(BaseModel):
    slug: str
    composite_score: int
    stamp: str
    created_at: datetime

    rank: int
    total_ranked: int

    summary: ScoreSummary
    metrics: dict
    subscores: dict[str, int]

    verdict: str
    roast: str
    fixes: list[str]
    highlights: list[Highlight]
