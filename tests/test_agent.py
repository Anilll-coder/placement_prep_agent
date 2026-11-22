"""Offline tests: the LLM and web search are replaced with fakes, so no API key or network is needed."""

import json

import pytest

import placement_prep_agent.graph as prep_mod
import placement_prep_agent.interview as iv_mod
from placement_prep_agent.configuration import Configuration
from placement_prep_agent.llm import MissingAPIKeyError, extract_json, get_llm


def fake_ask(cfg, system, user, temperature=None):
    """Return canned text depending on which prompt is being answered."""
    if "search queries" in system:
        return json.dumps({"queries": ["q1", "q2", "q3"]})
    if "follow_up_query" in system:
        return json.dumps({"knowledge_gap": "OA details", "follow_up_query": "q-followup"})
    if "Hiring Process & Rounds" in system:
        return "### Hiring Process & Rounds\n- OA, 2 technical, 1 HR"
    if "Readiness Score" in system:
        return "### Readiness Score\n62/100"
    if "Day-by-Day Plan" in system:
        return "### Day-by-Day Plan\n| Day | Focus |"
    if "practice questions" in system:
        return "### Coding / DSA\n**Q1. Two sum**"
    if '"score"' in system:
        return '```json\n{"score": 7, "verdict": "Hire", "what_went_well": ["clear"], ' \
               '"what_to_improve": ["edge cases"], "model_answer": "use a hashmap", ' \
               '"follow_up_question": "what if sorted?"}\n```'
    if "interviewer" in system:
        return "Reverse a linked list."
    return "ok"


def fake_search(query, max_results=3, fetch_full_page=False):
    return {"results": [{"title": f"T-{query}", "url": f"https://ex.com/{query}",
                         "content": "snippet", "raw_content": "snippet"}]}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    for mod in (prep_mod, iv_mod):
        monkeypatch.setattr(mod, "ask", fake_ask)
        monkeypatch.setattr(mod, "ask_json", lambda c, s, u: extract_json(fake_ask(c, s, u)))
    monkeypatch.setattr(prep_mod, "duckduckgo_search", fake_search)
    for var in ("SEARCH_API", "MAX_RESEARCH_LOOPS", "LLM_PROVIDER", "QUERIES_PER_ROUND"):
        monkeypatch.delenv(var, raising=False)


def test_prep_graph_end_to_end():
    out = prep_mod.graph.invoke(
        {"company": "Amazon", "role": "SDE-1", "candidate_profile": "Java, DSA", "prep_days": 10},
        config={"configurable": {"max_research_loops": 1}},
    )
    report = out["final_report"]
    assert "Placement Prep Report: Amazon - SDE-1" in report
    for section in ("Hiring Process", "Readiness Score", "Day-by-Day Plan", "Two sum"):
        assert section in report
    # 3 initial queries + 1 follow-up -> 4 distinct sources
    assert report.count("https://ex.com/") == 4


def test_prep_graph_offline_mode_skips_search(monkeypatch):
    called = []
    monkeypatch.setattr(prep_mod, "duckduckgo_search", lambda *a, **k: called.append(1))
    out = prep_mod.graph.invoke(
        {"company": "TCS", "role": "Ninja"}, config={"configurable": {"search_api": "none"}}
    )
    assert not called
    assert "No web sources" in out["final_report"]


def test_interview_ask_then_evaluate():
    q = iv_mod.graph.invoke({"company": "Google", "round_type": "technical"})["question"]
    assert q == "Reverse a linked list."
    out = iv_mod.graph.invoke({"company": "Google", "question": q, "candidate_answer": "iterate"})
    assert out["score"] == 7
    assert "use a hashmap" in out["feedback"]


def test_extract_json_variants():
    assert extract_json('{"a": 1}') == {"a": 1}
    assert extract_json('noise ```json\n{"a": 2}\n``` tail') == {"a": 2}
    assert extract_json("<think>hmm</think> {\"a\": 3}") == {"a": 3}
    assert extract_json("not json") is None


def test_missing_key_is_reported(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(MissingAPIKeyError):
        get_llm(Configuration(llm_provider="groq"))


def test_provider_defaults(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    llm = get_llm(Configuration(llm_provider="groq"))
    assert llm.model_name == "llama-3.1-8b-instant"
    assert "groq.com" in str(llm.openai_api_base)
