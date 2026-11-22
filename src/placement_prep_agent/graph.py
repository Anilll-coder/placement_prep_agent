"""Placement prep graph.

Flow:
    plan_queries -> web_research -> summarize_insights -> reflect --(loop)--> web_research
                                                           |
                                                           v
                                                   analyze_profile
                                                    /            \\
                                         build_study_plan   generate_practice_questions
                                                    \\            /
                                                    compile_report -> END
"""

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from typing_extensions import Literal

from placement_prep_agent.configuration import Configuration
from placement_prep_agent.llm import ask, ask_json
from placement_prep_agent.prompts import (
    get_current_date,
    insights_instructions,
    practice_questions_instructions,
    query_planner_instructions,
    reflection_instructions,
    skill_gap_instructions,
    study_plan_instructions,
)
from placement_prep_agent.state import PrepState, PrepStateInput, PrepStateOutput
from placement_prep_agent.utils import (
    deduplicate_and_format_sources,
    duckduckgo_search,
    format_sources,
    perplexity_search,
    searxng_search,
    tavily_search,
)

MAX_CONTEXT_CHARS = 12000  # keep prompts small enough for lightweight / free-tier models


def _cfg(config: RunnableConfig) -> Configuration:
    return Configuration.from_runnable_config(config)


def _company(state: PrepState) -> str:
    return state.company.strip() or "a top product/service company"


# --------------------------------------------------------------------------
# Research nodes
# --------------------------------------------------------------------------
def plan_queries(state: PrepState, config: RunnableConfig):
    """Generate the first round of web search queries."""
    cfg = _cfg(config)
    n = max(1, cfg.queries_per_round)
    prompt = query_planner_instructions.format(
        current_date=get_current_date(), company=_company(state), role=state.role, n=n
    )
    parsed = ask_json(cfg, prompt, "Generate the search queries now.")
    queries = []
    if isinstance(parsed, dict):
        queries = [q for q in parsed.get("queries", []) if isinstance(q, str) and q.strip()]
    if not queries:  # deterministic fallback
        year = get_current_date()[-4:]
        queries = [
            f"{_company(state)} {state.role} interview experience {year}",
            f"{_company(state)} online assessment pattern {year}",
            f"{_company(state)} interview questions {state.role}",
        ]
    return {"search_queries": queries[:n]}


def _run_search(api: str, query: str, cfg: Configuration, loop: int) -> dict:
    if api == "tavily":
        return tavily_search(query, fetch_full_page=cfg.fetch_full_page, max_results=3)
    if api == "perplexity":
        return perplexity_search(query, loop)
    if api == "searxng":
        return searxng_search(query, max_results=3, fetch_full_page=cfg.fetch_full_page)
    return duckduckgo_search(query, max_results=3, fetch_full_page=cfg.fetch_full_page)


def web_research(state: PrepState, config: RunnableConfig):
    """Run every query of the current round; failures are skipped, not fatal."""
    cfg = _cfg(config)
    contexts, sources = [], []
    for query in state.search_queries:
        try:
            results = _run_search(cfg.search_api, query, cfg, state.research_loop_count)
        except Exception as e:  # network / quota errors shouldn't kill the run
            print(f"Search failed for '{query}': {e}")  # noqa: T201
            continue
        if results.get("results"):
            contexts.append(
                deduplicate_and_format_sources(
                    results, max_tokens_per_source=800, fetch_full_page=cfg.fetch_full_page
                )
            )
            sources.append(format_sources(results))
    return {
        "web_research_results": ["\n\n".join(contexts)] if contexts else [],
        "sources_gathered": sources,
        "research_loop_count": state.research_loop_count + 1,
    }


def summarize_insights(state: PrepState, config: RunnableConfig):
    """Create or refine the company brief from the newest research."""
    cfg = _cfg(config)
    new_context = state.web_research_results[-1] if state.web_research_results else ""
    new_context = new_context[:MAX_CONTEXT_CHARS] or "(no web context available)"
    if state.company_insights:
        user = (
            f"<Existing Brief>\n{state.company_insights}\n</Existing Brief>\n\n"
            f"<New Context>\n{new_context}\n</New Context>\n\n"
            "Update the brief: merge in new facts, keep everything still valid, remove duplicates."
        )
    else:
        user = f"<Context>\n{new_context}\n</Context>\n\nWrite the brief."
    system = insights_instructions.format(company=_company(state), role=state.role)
    return {"company_insights": ask(cfg, system, user, temperature=0.1)}


def reflect(state: PrepState, config: RunnableConfig):
    """Find the biggest gap in the brief and plan one follow-up search."""
    cfg = _cfg(config)
    system = reflection_instructions.format(company=_company(state), role=state.role)
    parsed = ask_json(cfg, system, f"<Brief>\n{state.company_insights}\n</Brief>")
    query = parsed.get("follow_up_query") if isinstance(parsed, dict) else None
    if not query:
        query = f"{_company(state)} {state.role} interview rounds and questions"
    return {"search_queries": [query]}


def route_start(
    state: PrepState, config: RunnableConfig
) -> Literal["plan_queries", "summarize_insights"]:
    """Skip web research entirely when search_api == 'none'."""
    return "summarize_insights" if _cfg(config).search_api == "none" else "plan_queries"


def route_after_insights(
    state: PrepState, config: RunnableConfig
) -> Literal["reflect", "analyze_profile"]:
    """Loop research until max_research_loops follow-up rounds have run."""
    cfg = _cfg(config)
    if cfg.search_api != "none" and state.research_loop_count <= cfg.max_research_loops:
        return "reflect"
    return "analyze_profile"


# --------------------------------------------------------------------------
# Planning nodes
# --------------------------------------------------------------------------
def _profile(state: PrepState) -> str:
    return state.candidate_profile.strip()[:MAX_CONTEXT_CHARS] or "(no profile provided)"


def analyze_profile(state: PrepState, config: RunnableConfig):
    """Compare the candidate's profile with the company's expectations."""
    cfg = _cfg(config)
    system = skill_gap_instructions.format(company=_company(state), role=state.role)
    user = (
        f"<Company Brief>\n{state.company_insights}\n</Company Brief>\n\n"
        f"<Candidate Profile>\n{_profile(state)}\n</Candidate Profile>\n\n"
        f"Candidate's own focus areas: {state.focus_areas or 'none given'}"
    )
    return {"skill_gap_analysis": ask(cfg, system, user)}


def build_study_plan(state: PrepState, config: RunnableConfig):
    """Write a day-by-day preparation plan."""
    cfg = _cfg(config)
    system = study_plan_instructions.format(
        company=_company(state),
        role=state.role,
        prep_days=max(1, int(state.prep_days or 14)),
        focus_areas=state.focus_areas or "none",
    )
    user = (
        f"<Company Brief>\n{state.company_insights}\n</Company Brief>\n\n"
        f"<Skill Gap Analysis>\n{state.skill_gap_analysis}\n</Skill Gap Analysis>"
    )
    return {"study_plan": ask(cfg, system, user)}


def generate_practice_questions(state: PrepState, config: RunnableConfig):
    """Generate company-style practice questions aimed at the candidate's gaps."""
    cfg = _cfg(config)
    system = practice_questions_instructions.format(
        company=_company(state), role=state.role, n=max(1, cfg.num_practice_questions)
    )
    user = (
        f"<Company Brief>\n{state.company_insights}\n</Company Brief>\n\n"
        f"<Skill Gap Analysis>\n{state.skill_gap_analysis}\n</Skill Gap Analysis>"
    )
    return {"practice_questions": ask(cfg, system, user, temperature=0.5)}


def compile_report(state: PrepState):
    """Assemble everything into one Markdown report with deduplicated sources."""
    seen, unique = set(), []
    for block in state.sources_gathered:
        for line in block.split("\n"):
            if line.strip() and line not in seen:
                seen.add(line)
                unique.append(line)
    sources = "\n".join(unique) or "_No web sources (offline / general-knowledge mode)._"

    report = f"""# Placement Prep Report: {_company(state)} - {state.role}
_Generated on {get_current_date()} | Prep window: {state.prep_days} days_

## 1. Company Hiring Insights
{state.company_insights}

## 2. Skill Gap Analysis
{state.skill_gap_analysis}

## 3. Study Plan
{state.study_plan}

## 4. Practice Questions
{state.practice_questions}

## Sources
{sources}
"""
    return {"final_report": report}


# --------------------------------------------------------------------------
# Graph
# --------------------------------------------------------------------------
builder = StateGraph(
    PrepState,
    input_schema=PrepStateInput,
    output_schema=PrepStateOutput,
)

builder.add_node("plan_queries", plan_queries)
builder.add_node("web_research", web_research)
builder.add_node("summarize_insights", summarize_insights)
builder.add_node("reflect", reflect)
builder.add_node("analyze_profile", analyze_profile)
builder.add_node("build_study_plan", build_study_plan)
builder.add_node("generate_practice_questions", generate_practice_questions)
builder.add_node("compile_report", compile_report)

builder.add_conditional_edges(START, route_start)
builder.add_edge("plan_queries", "web_research")
builder.add_edge("web_research", "summarize_insights")
builder.add_conditional_edges("summarize_insights", route_after_insights)
builder.add_edge("reflect", "web_research")
builder.add_edge("analyze_profile", "build_study_plan")
builder.add_edge("analyze_profile", "generate_practice_questions")
builder.add_edge(["build_study_plan", "generate_practice_questions"], "compile_report")
builder.add_edge("compile_report", END)

graph = builder.compile()
