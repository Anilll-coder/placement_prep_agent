# 🎯 Placement Prep Agent

An AI agent that helps students prepare for campus placements and job interviews.
Give it a **target company**, a **role** and your **resume**. It then:

1. **Researches the company's hiring process** on the web: interview rounds, online assessment pattern, commonly asked questions and HR focus. It loops, finding gaps in what it knows and searching again.
2. **Analyses your profile against those requirements**: a readiness score, your strengths, a prioritised table of skill gaps, and resume suggestions.
3. **Builds a day-by-day study plan** that fits the number of days you have left.
4. **Generates practice questions in the company's style**, each with hints and key points, aimed at your weakest areas.
5. **Runs mock interviews** (technical, HR, aptitude or system design). It scores each answer out of 10 and gives feedback, a model answer and a likely follow-up question.

Everything ends up in one Markdown report you can download.

It is built with **LangGraph** and runs on **lightweight models**: Groq's free `llama-3.1-8b-instant` by default. You can also use OpenAI `gpt-4o-mini`, Gemini Flash, OpenRouter, or a fully local model through Ollama.

---

## Architecture

```
            ┌──────────────┐
 START ───► │ plan_queries │  LLM writes 3 targeted search queries
            └──────┬───────┘
                   ▼
            ┌──────────────┐
      ┌───► │ web_research │  DuckDuckGo / Tavily / Perplexity / SearXNG
      │     └──────┬───────┘
      │            ▼
      │   ┌────────────────────┐
      │   │ summarize_insights │  builds / refines the company brief
      │   └────────┬───────────┘
      │            ▼  (loop N times)
      └──── reflect ── finds the biggest knowledge gap → follow-up query
                   │
                   ▼
           ┌─────────────────┐
           │ analyze_profile │  readiness score, strengths, gap table
           └───┬─────────┬───┘
               ▼         ▼        (run in parallel)
   build_study_plan   generate_practice_questions
               └────┬────┘
                    ▼
             compile_report ──► END
```

A second graph, `mock_interview`, handles a single turn of an interview. It either asks a new question or evaluates an answer.

```
src/placement_prep_agent/
├── graph.py          # prep-plan graph
├── interview.py      # mock-interview graph
├── prompts.py        # all prompt templates
├── llm.py            # provider factory (Groq/OpenAI/Gemini/OpenRouter/Ollama) + JSON parsing
├── configuration.py  # settings (env vars / LangGraph configurable)
├── state.py          # graph state dataclasses
├── resume.py         # PDF / TXT / MD resume loader
├── utils.py          # web search helpers
└── cli.py            # `placement-prep` command
app.py                # Streamlit web UI
tests/                # offline tests (no API key needed)
```

---

## Quick start

### 1. Install

```powershell
python -m venv .venv
```
```powershell
.venv\Scripts\activate
```
```powershell
pip install -e ".[ui,dev]"
```

### 2. Add an API key

Copy `.env.example` to `.env`, then set your provider and key:

```ini
LLM_PROVIDER=groq
GROQ_API_KEY=gsk_...
```

| Provider | Free tier | Get a key | Default model |
|---|---|---|---|
| `groq` *(recommended)* | ✅ | https://console.groq.com/keys | `llama-3.1-8b-instant` |
| `gemini` | ✅ | https://aistudio.google.com/apikey | `gemini-2.5-flash` |
| `openrouter` | some free models | https://openrouter.ai/keys | `meta-llama/llama-3.1-8b-instruct` |
| `openai` | ❌ | https://platform.openai.com/api-keys | `gpt-4o-mini` |
| `ollama` | local, no key | https://ollama.com (`ollama pull llama3.2`) | `llama3.2` |

Set `LLM_MODEL` to override the default model. DuckDuckGo search needs no key.

Check your setup:

```powershell
placement-prep check --ping
```

### 3. Use it

**Web UI**

```powershell
streamlit run app.py
```

**CLI: generate a prep report**

```powershell
placement-prep prep --company "Amazon" --role "SDE-1" --resume .\my_resume.pdf --days 21 --focus "DP, OOP"
```

The report is saved to `reports/amazon_sde_1_<timestamp>.md`.

**CLI: mock interview**

```powershell
placement-prep interview --company "Google" --round technical --difficulty medium --questions 3
```

**LangGraph Studio** (visual graph debugger)

```powershell
pip install "langgraph-cli[inmem]"
```
```powershell
langgraph dev
```

Both graphs, `placement_prep` and `mock_interview`, show up in Studio.

**From Python**

```python
from dotenv import load_dotenv; load_dotenv()
from placement_prep_agent.graph import graph

out = graph.invoke({
    "company": "Microsoft",
    "role": "Software Engineer Intern",
    "candidate_profile": "3rd-year CSE, C++, 300 LeetCode, React project",
    "prep_days": 14,
})
print(out["final_report"])
```

---

## Configuration

Every setting can be set as an environment variable (in `.env`) or passed as `config={"configurable": {...}}`.

| Variable | Default | Meaning |
|---|---|---|
| `LLM_PROVIDER` | `groq` | `groq`, `openai`, `gemini`, `openrouter` or `ollama` |
| `LLM_MODEL` | *(provider default)* | model name |
| `LLM_API_KEY` | | generic key (overrides the provider-specific one) |
| `LLM_TEMPERATURE` | `0.3` | creativity of plan and question generation |
| `SEARCH_API` | `duckduckgo` | `duckduckgo`, `tavily`, `perplexity`, `searxng` or `none` (offline) |
| `MAX_RESEARCH_LOOPS` | `2` | number of follow-up research rounds |
| `QUERIES_PER_ROUND` | `3` | number of searches in the first round |
| `FETCH_FULL_PAGE` | `False` | download full pages (richer results, slower) |
| `NUM_PRACTICE_QUESTIONS` | `15` | number of practice questions to generate |

With `SEARCH_API=none` the agent skips the web entirely and relies on the model's general knowledge. Facts that come from general knowledge are labelled as such in the report.

---

## Tests

```powershell
pytest -q
```

The tests replace the LLM and web search with fakes, so they run offline without an API key.

## Docker

```powershell
docker build -t placement-prep .
```
```powershell
docker run --env-file .env -p 8501:8501 placement-prep
```

Then open http://localhost:8501.

## Ideas for extending

- Store past reports and mock-interview scores to track progress over time
- Fetch a company-specific LeetCode question list and link problems directly in the plan
- Multi-turn interview that adapts its difficulty to your answers
- Export the study plan as a calendar (`.ics`)

## Credits

Started from LangChain's MIT-licensed [local-deep-researcher](https://github.com/langchain-ai/local-deep-researcher) template. Its web-search utilities are reused here.
