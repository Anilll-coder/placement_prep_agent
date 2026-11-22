"""Graph state definitions."""

import operator
from dataclasses import dataclass, field

from typing_extensions import Annotated


# --------------------------------------------------------------------------
# Prep-plan graph
# --------------------------------------------------------------------------
@dataclass(kw_only=True)
class PrepStateInput:
    """What the user provides."""

    company: str = field(default="")  # e.g. "Amazon"
    role: str = field(default="Software Development Engineer")  # e.g. "SDE-1", "Data Analyst"
    candidate_profile: str = field(default="")  # resume text or a short skills summary
    prep_days: int = field(default=14)  # days left before the interview / drive
    focus_areas: str = field(default="")  # optional, e.g. "DSA, system design basics"


@dataclass(kw_only=True)
class PrepState(PrepStateInput):
    """Full working state of the prep-plan graph."""

    search_queries: list = field(default_factory=list)  # queries for the current round
    web_research_results: Annotated[list, operator.add] = field(default_factory=list)
    sources_gathered: Annotated[list, operator.add] = field(default_factory=list)
    research_loop_count: int = field(default=0)
    company_insights: str = field(default="")
    skill_gap_analysis: str = field(default="")
    study_plan: str = field(default="")
    practice_questions: str = field(default="")
    final_report: str = field(default="")


@dataclass(kw_only=True)
class PrepStateOutput:
    """What the graph returns."""

    final_report: str = field(default="")
    company_insights: str = field(default="")
    skill_gap_analysis: str = field(default="")
    study_plan: str = field(default="")
    practice_questions: str = field(default="")


# --------------------------------------------------------------------------
# Mock-interview graph (single turn: ask a question OR evaluate an answer)
# --------------------------------------------------------------------------
@dataclass(kw_only=True)
class InterviewStateInput:
    """Input for one mock-interview turn."""

    company: str = field(default="")
    role: str = field(default="Software Development Engineer")
    round_type: str = field(default="technical")  # technical | hr | aptitude | system_design
    difficulty: str = field(default="medium")  # easy | medium | hard
    previous_questions: list = field(default_factory=list)  # avoid repeats
    question: str = field(default="")  # leave empty to get a new question
    candidate_answer: str = field(default="")  # fill to get feedback on `question`


@dataclass(kw_only=True)
class InterviewState(InterviewStateInput):
    """Full working state of the interview graph."""

    feedback: str = field(default="")
    score: int = field(default=0)


@dataclass(kw_only=True)
class InterviewStateOutput:
    """Output of one mock-interview turn."""

    question: str = field(default="")
    feedback: str = field(default="")
    score: int = field(default=0)
