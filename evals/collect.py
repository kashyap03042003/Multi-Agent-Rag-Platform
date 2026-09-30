import json
import time
from datetime import datetime, timezone
from pathlib import Path
from langchain_core.messages import HumanMessage
from rag.graph import graph
from services.guardrails_service import check_input

EVAL_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVAL_DIR / "results"


def load_golden() -> list[dict]:
    with open(EVAL_DIR / "golden.jsonl") as f:
        return [json.loads(line) for line in f if line.strip()]


def run_case(case: dict) -> dict:
    start = time.perf_counter()
    refusal = check_input(case["question"])
    if refusal:
        return {**case, "blocked": True, "needs_retrieval": False, "answer": refusal,
                "contexts": [], "sources": [], "categories": [],
                "latency_s": round(time.perf_counter() - start, 2)}

    config = {"configurable": {"thread_id": f"eval-{case['id']}", "trace_id": f"eval-{case['id']}"}}
    result = graph.invoke({"messages": [HumanMessage(case["question"])]}, config)
    docs = result["documents"]
    return {
        **case,
        "blocked": False,
        "needs_retrieval": result["needs_retrieval"],
        "search_query": result["search_query"],
        "answer": result["messages"][-1].content,
        "contexts": [d["text"] for d in docs],
        "sources": [d["source"] for d in docs],
        "categories": [d["category"] for d in docs],
        "latency_s": round(time.perf_counter() - start, 2),
    }


def main():
    RESULTS_DIR.mkdir(exist_ok=True)
    out = RESULTS_DIR / f"run_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.jsonl"
    with open(out, "w") as f:
        for case in load_golden():
            try:
                row = run_case(case)
            except Exception as e:
                row = {**case, "error": f"{type(e).__name__}: {e}"[:500], "blocked": False,
                       "needs_retrieval": False, "answer": "", "contexts": [], "sources": [],
                       "categories": [], "latency_s": None}
                print(f"{case['id']:25} ERROR  {row['error'][:120]}")
            else:
                print(f"{case['id']:25} {row['latency_s']:>5}s  chunks={len(row['contexts'])}  blocked={row['blocked']}")
            f.write(json.dumps(row) + "\n")
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()
