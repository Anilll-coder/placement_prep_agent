"""Streamlit web UI for the Placement Prep Agent.

Run with:  streamlit run app.py
"""

import os
import tempfile
from datetime import datetime

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from placement_prep_agent.configuration import Configuration  # noqa: E402
from placement_prep_agent.llm import PROVIDERS, MissingAPIKeyError, get_llm  # noqa: E402

NODE_LABELS = {
    "plan_queries": "Planning search queries",
    "web_research": "Searching the web",
    "summarize_insights": "Summarising company insights",
    "reflect": "Looking for gaps in the research",
    "analyze_profile": "Analysing your profile",
    "build_study_plan": "Building your study plan",
    "generate_practice_questions": "Writing practice questions",
    "compile_report": "Compiling the report",
}

st.set_page_config(page_title="Placement Prep Agent", page_icon="🎯", layout="wide")

# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.header("⚙️ Settings")
    env_cfg = Configuration.from_runnable_config()
    providers = list(PROVIDERS)
    provider = st.selectbox("LLM provider", providers, index=providers.index(env_cfg.llm_provider))
    model = st.text_input("Model", value=env_cfg.llm_model, placeholder=PROVIDERS[provider][1])
    key_env = PROVIDERS[provider][2]
    api_key = ""
    if key_env:
        api_key = st.text_input(
            f"API key ({key_env})",
            type="password",
            help="Leave blank to use the key from your .env file.",
        )
    search_api = st.selectbox(
        "Web search",
        ["duckduckgo", "tavily", "perplexity", "searxng", "none"],
        index=["duckduckgo", "tavily", "perplexity", "searxng", "none"].index(env_cfg.search_api),
    )
    depth = st.slider("Research depth (follow-up rounds)", 0, 4, env_cfg.max_research_loops)
    n_questions = st.slider("Practice questions", 5, 40, env_cfg.num_practice_questions)

configurable = {
    "llm_provider": provider,
    "llm_model": model,
    "llm_api_key": api_key,
    "search_api": search_api,
    "max_research_loops": depth,
    "num_practice_questions": n_questions,
}
# UI choices should win over .env, so clear the env overrides for this process
for name in configurable:
    os.environ.pop(name.upper(), None)
if api_key and key_env:
    os.environ[key_env] = api_key
run_config = {"configurable": configurable}


def llm_ready() -> bool:
    """Show an error and return False if the LLM can't be built."""
    try:
        get_llm(Configuration.from_runnable_config(run_config))
        return True
    except MissingAPIKeyError as e:
        st.error(str(e))
        return False


st.title("🎯 Placement Prep Agent")
st.caption("Company research → skill-gap analysis → day-by-day plan → practice questions → mock interviews")

tab_prep, tab_interview = st.tabs(["📋 Prep Plan", "🎤 Mock Interview"])

# ---------------------------------------------------------------- prep tab
with tab_prep:
    c1, c2, c3 = st.columns([2, 2, 1])
    company = c1.text_input("Target company", placeholder="e.g. Amazon, TCS, Microsoft")
    role = c2.text_input("Role", value="Software Development Engineer")
    days = c3.number_input("Days to prepare", 1, 180, 14)
    focus = st.text_input("Extra focus areas (optional)", placeholder="e.g. DP, SQL, OOP, system design basics")
    resume = st.file_uploader("Resume (PDF / TXT / MD)", type=["pdf", "txt", "md"])
    profile_text = st.text_area(
        "…or paste a short profile",
        placeholder="B.Tech CSE 2026, CGPA 8.1. Java, Python, SQL. 250 LeetCode problems. Internship at …",
        height=110,
    )

    if st.button("Generate prep plan", type="primary", disabled=not company.strip()):
        if llm_ready():
            profile = profile_text
            if resume is not None:
                from placement_prep_agent.resume import load_resume

                suffix = os.path.splitext(resume.name)[1]
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(resume.getvalue())
                try:
                    profile = (profile + "\n\n" + load_resume(tmp.name)).strip()
                except Exception as e:
                    st.warning(f"Couldn't read resume: {e}")
                finally:
                    os.unlink(tmp.name)

            from placement_prep_agent.graph import graph

            inputs = {
                "company": company,
                "role": role,
                "candidate_profile": profile,
                "prep_days": int(days),
                "focus_areas": focus,
            }
            result: dict = {}
            try:
                with st.status("Working on your plan…", expanded=True) as status:
                    for update in graph.stream(inputs, config=run_config, stream_mode="updates"):
                        for node, values in update.items():
                            st.write("✅ " + NODE_LABELS.get(node, node))
                            if values:
                                result.update(values)
                    status.update(label="Plan ready!", state="complete")
                st.session_state["prep_result"] = result
                st.session_state["prep_name"] = f"{company}_{role}".replace(" ", "_")
            except Exception as e:
                st.error(f"Run failed: {e}")

    result = st.session_state.get("prep_result")
    if result:
        st.download_button(
            "⬇️ Download full report (.md)",
            result.get("final_report", ""),
            file_name=f"{st.session_state['prep_name']}_{datetime.now():%Y%m%d}.md",
        )
        t1, t2, t3, t4 = st.tabs(["🏢 Company insights", "📊 Skill gaps", "🗓️ Study plan", "❓ Practice questions"])
        t1.markdown(result.get("company_insights", ""))
        t2.markdown(result.get("skill_gap_analysis", ""))
        t3.markdown(result.get("study_plan", ""))
        t4.markdown(result.get("practice_questions", ""))

# ---------------------------------------------------------------- interview tab
with tab_interview:
    st.session_state.setdefault("iv_history", [])
    st.session_state.setdefault("iv_question", "")
    c1, c2, c3, c4 = st.columns(4)
    iv_company = c1.text_input("Company", key="iv_company", placeholder="e.g. Google")
    iv_role = c2.text_input("Role", key="iv_role", value="Software Development Engineer")
    iv_round = c3.selectbox("Round", ["technical", "hr", "aptitude", "system_design"])
    iv_diff = c4.selectbox("Difficulty", ["easy", "medium", "hard"], index=1)
    base = {"company": iv_company, "role": iv_role, "round_type": iv_round, "difficulty": iv_diff}

    if st.button("🎲 Ask me a question", disabled=not iv_company.strip()) and llm_ready():
        from placement_prep_agent.interview import graph as iv_graph

        asked = [h["question"] for h in st.session_state["iv_history"]]
        with st.spinner("Thinking of a question…"):
            out = iv_graph.invoke({**base, "previous_questions": asked}, config=run_config)
        st.session_state["iv_question"] = out["question"]

    if st.session_state["iv_question"]:
        st.markdown("#### Question")
        st.info(st.session_state["iv_question"])
        answer = st.text_area("Your answer", height=200, key="iv_answer")
        if st.button("Submit answer", type="primary", disabled=not answer.strip()) and llm_ready():
            from placement_prep_agent.interview import graph as iv_graph

            with st.spinner("Evaluating…"):
                out = iv_graph.invoke(
                    {**base, "question": st.session_state["iv_question"], "candidate_answer": answer},
                    config=run_config,
                )
            st.session_state["iv_history"].append(
                {"question": st.session_state["iv_question"], "score": out["score"], "feedback": out["feedback"]}
            )
            st.markdown(out["feedback"])

    history = st.session_state["iv_history"]
    if history:
        avg = sum(h["score"] for h in history) / len(history)
        st.divider()
        st.metric("Average score", f"{avg:.1f} / 10", help=f"{len(history)} answered")
        for i, h in enumerate(reversed(history), 1):
            with st.expander(f"{h['score']}/10 — {h['question'][:90]}"):
                st.markdown(h["feedback"])
