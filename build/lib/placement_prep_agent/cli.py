"""Command-line interface.

Examples:
    placement-prep check
    placement-prep prep --company Amazon --role "SDE-1" --resume my_resume.pdf --days 21
    placement-prep interview --company Google --round technical --questions 3
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from placement_prep_agent.configuration import Configuration
from placement_prep_agent.llm import PROVIDERS, MissingAPIKeyError, get_llm

NODE_LABELS = {
    "plan_queries": "Planning search queries",
    "web_research": "Searching the web",
    "summarize_insights": "Summarising company insights",
    "reflect": "Looking for gaps in the research",
    "analyze_profile": "Analysing your profile vs. requirements",
    "build_study_plan": "Building your study plan",
    "generate_practice_questions": "Writing practice questions",
    "compile_report": "Compiling the final report",
}


def _print(msg: str = "") -> None:
    print(msg, flush=True)  # noqa: T201


def _slug(text: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", text).strip("_").lower() or "report"


def cmd_check(args: argparse.Namespace) -> int:
    """Show the active configuration and whether the LLM can be built."""
    cfg = Configuration.from_runnable_config()
    model = cfg.llm_model or PROVIDERS[cfg.llm_provider][1]
    _print(f"LLM provider : {cfg.llm_provider}")
    _print(f"LLM model    : {model}")
    _print(f"Search API   : {cfg.search_api}")
    _print(f"Research     : {cfg.queries_per_round} queries + {cfg.max_research_loops} follow-up rounds")
    try:
        get_llm(cfg)
    except MissingAPIKeyError as e:
        _print(f"\n[!] {e}")
        return 1
    _print("\nConfiguration OK. (Run `placement-prep check --ping` to make a real API call.)")
    if getattr(args, "ping", False):
        from placement_prep_agent.llm import ask

        reply = ask(cfg, "Reply with exactly: pong", "ping", temperature=0)
        _print(f"Model replied: {reply[:80]}")
    return 0


def cmd_prep(args: argparse.Namespace) -> int:
    """Run the full research + planning pipeline and save a Markdown report."""
    from placement_prep_agent.graph import graph
    from placement_prep_agent.resume import load_resume

    profile = args.profile or ""
    if args.resume:
        profile = (profile + "\n\n" + load_resume(args.resume)).strip()

    inputs = {
        "company": args.company,
        "role": args.role,
        "candidate_profile": profile,
        "prep_days": args.days,
        "focus_areas": args.focus or "",
    }
    _print(f"Preparing a plan for {args.company} - {args.role} ({args.days} days)...\n")

    final: dict = {}
    for update in graph.stream(inputs, stream_mode="updates"):
        for node, values in update.items():
            _print(f"  - {NODE_LABELS.get(node, node)}")
            if node == "web_research" and values:
                n = len(values.get("sources_gathered", []))
                _print(f"      ({n} search(es) returned results)")
            if values:
                final.update(values)

    report = final.get("final_report", "")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_file = out_dir / f"{_slug(args.company)}_{_slug(args.role)}_{stamp}.md"
    out_file.write_text(report, encoding="utf-8")
    _print(f"\nDone. Report saved to: {out_file.resolve()}")
    if args.show:
        _print("\n" + report)
    return 0


def _read_multiline(prompt: str) -> str:
    _print(prompt)
    _print("(finish with an empty line; type 'skip' to skip, 'quit' to stop)")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if not line.strip():
            break
        lines.append(line)
    return "\n".join(lines).strip()


def cmd_interview(args: argparse.Namespace) -> int:
    """Run an interactive mock interview in the terminal."""
    from placement_prep_agent.interview import graph

    base = {
        "company": args.company,
        "role": args.role,
        "round_type": args.round,
        "difficulty": args.difficulty,
    }
    asked, scores = [], []
    _print(f"Mock {args.round} interview - {args.company} / {args.role} ({args.difficulty})\n")
    for i in range(1, args.questions + 1):
        q = graph.invoke({**base, "previous_questions": asked})["question"]
        asked.append(q)
        _print(f"\n{'=' * 70}\nQuestion {i}/{args.questions}\n{'=' * 70}\n{q}\n")
        answer = _read_multiline("Your answer:")
        if answer.lower() == "quit":
            break
        if not answer or answer.lower() == "skip":
            continue
        out = graph.invoke({**base, "question": q, "candidate_answer": answer})
        scores.append(out["score"])
        _print(f"\n--- Feedback ---\n{out['feedback']}\n")
    if scores:
        avg = sum(scores) / len(scores)
        _print(f"\nSession summary: {len(scores)} answered, average score {avg:.1f}/10")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Create the argument parser."""
    p = argparse.ArgumentParser(prog="placement-prep", description="AI placement preparation agent")
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="verify configuration / API key")
    c.add_argument("--ping", action="store_true", help="make one real API call")
    c.set_defaults(func=cmd_check)

    pr = sub.add_parser("prep", help="research a company and build a prep plan")
    pr.add_argument("--company", required=True)
    pr.add_argument("--role", default="Software Development Engineer")
    pr.add_argument("--resume", help="path to resume (.pdf, .txt or .md)")
    pr.add_argument("--profile", help="short skills summary (alternative/addition to --resume)")
    pr.add_argument("--days", type=int, default=14, help="days left to prepare")
    pr.add_argument("--focus", help="extra focus areas, e.g. 'DP, SQL, OOP'")
    pr.add_argument("--out", default="reports", help="output folder")
    pr.add_argument("--show", action="store_true", help="also print the report")
    pr.set_defaults(func=cmd_prep)

    iv = sub.add_parser("interview", help="interactive mock interview")
    iv.add_argument("--company", required=True)
    iv.add_argument("--role", default="Software Development Engineer")
    iv.add_argument(
        "--round", default="technical", choices=["technical", "hr", "aptitude", "system_design"]
    )
    iv.add_argument("--difficulty", default="medium", choices=["easy", "medium", "hard"])
    iv.add_argument("--questions", type=int, default=3)
    iv.set_defaults(func=cmd_interview)
    return p


def main(argv=None) -> int:
    """CLI entry point."""
    load_dotenv()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # Windows consoles
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except MissingAPIKeyError as e:
        _print(f"\n[!] {e}")
        return 1
    except KeyboardInterrupt:
        _print("\nStopped.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
