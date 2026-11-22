"""Mock-interview graph.

One invocation = one turn:
- leave ``candidate_answer`` empty  -> the agent asks a new question
- fill ``question`` + ``candidate_answer`` -> the agent scores the answer and gives feedback
"""

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from typing_extensions import Literal

from placement_prep_agent.configuration import Configuration
from placement_prep_agent.llm import ask, ask_json
from placement_prep_agent.prompts import (
    interview_eval_instructions,
    interview_question_instructions,
)
from placement_prep_agent.state import InterviewState, InterviewStateInput, InterviewStateOutput


def _fmt(state: InterviewState) -> dict:
    return {
        "company": state.company.strip() or "a top tech company",
        "role": state.role,
        "round_type": state.round_type,
        "difficulty": state.difficulty,
    }


def ask_question(state: InterviewState, config: RunnableConfig):
    """Generate one new interview question."""
    cfg = Configuration.from_runnable_config(config)
    previous = "; ".join(state.previous_questions[-10:]) or "none"
    system = interview_question_instructions.format(**_fmt(state), previous_questions=previous)
    question = ask(cfg, system, "Ask the question now.", temperature=0.8)
    return {"question": question, "feedback": "", "score": 0}


def format_feedback(data: dict) -> str:
    """Render the evaluation JSON as readable Markdown."""

    def bullets(items) -> str:
        if isinstance(items, str):
            items = [items]
        return "\n".join(f"- {i}" for i in items or []) or "- -"

    return (
        f"**Score:** {data.get('score', '?')}/10 | **Verdict:** {data.get('verdict', 'n/a')}\n\n"
        f"**What went well**\n{bullets(data.get('what_went_well'))}\n\n"
        f"**What to improve**\n{bullets(data.get('what_to_improve'))}\n\n"
        f"**Model answer**\n{data.get('model_answer', '')}\n\n"
        f"**Likely follow-up:** {data.get('follow_up_question', '')}"
    )


def evaluate_answer(state: InterviewState, config: RunnableConfig):
    """Score the candidate's answer and give structured feedback."""
    cfg = Configuration.from_runnable_config(config)
    system = interview_eval_instructions.format(**_fmt(state))
    user = f"<Question>\n{state.question}\n</Question>\n\n<Answer>\n{state.candidate_answer}\n</Answer>"
    data = ask_json(cfg, system, user)
    if not isinstance(data, dict):
        # model didn't return JSON - fall back to free-text feedback
        text = ask(cfg, "You are an interviewer. Give concise feedback and a score out of 10.", user)
        return {"feedback": text, "score": 0}
    try:
        score = max(0, min(10, int(data.get("score", 0))))
    except (TypeError, ValueError):
        score = 0
    data["score"] = score
    return {"feedback": format_feedback(data), "score": score}


def route(state: InterviewState) -> Literal["ask_question", "evaluate_answer"]:
    """Evaluate if there is an answer to a question, otherwise ask a new one."""
    if state.question.strip() and state.candidate_answer.strip():
        return "evaluate_answer"
    return "ask_question"


builder = StateGraph(
    InterviewState,
    input_schema=InterviewStateInput,
    output_schema=InterviewStateOutput,
)
builder.add_node("ask_question", ask_question)
builder.add_node("evaluate_answer", evaluate_answer)
builder.add_conditional_edges(START, route)
builder.add_edge("ask_question", END)
builder.add_edge("evaluate_answer", END)

graph = builder.compile()
