import json
import statistics
import sys
from pathlib import Path
from deepeval.metrics import (
    AnswerRelevancyMetric,
    ContextualPrecisionMetric,
    ContextualRecallMetric,
    FaithfulnessMetric,
)
from deepeval.test_case import LLMTestCase
from evals.judge import GatewayJudge

RESULTS_DIR = Path(__file__).resolve().parent / "results"

THRESHOLDS = {
    "routing_accuracy": 0.9,
    "source_hit_rate": 0.8,
    "noise_ratio": 0.2,
    "abstain_rate": 0.8,
    "faithfulness": 0.8,
    "answer_relevancy": 0.7,
    "context_precision": 0.6,
    "context_recall": 0.6,
}
LOWER_IS_BETTER = {"noise_ratio"}
REFUSAL_MARKERS = ("don't know", "do not know", "does not contain", "no information", "not mentioned")
LLM_METRICS = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]


def route_ok(r: dict) -> bool:
    if r["type"] == "blocked":
        return r["blocked"]
    if r["blocked"]:
        return False
    if r["type"] == "smalltalk":
        return not r["needs_retrieval"]
    return r["needs_retrieval"]


def source_hit(r: dict) -> bool:
    return any(s in r["expected_sources"] for s in r["sources"])


def noise_ratio(r: dict) -> float:
    return r["categories"].count("noisy_data") / len(r["categories"])


def abstained(r: dict) -> bool:
    return any(m in r["answer"].lower() for m in REFUSAL_MARKERS)


def llm_scores(r: dict, judge: GatewayJudge) -> dict:
    case = LLMTestCase(
        input=r["question"],
        actual_output=r["answer"],
        expected_output=r["expected_answer"],
        retrieval_context=r["contexts"],
    )
    metrics = {
        "faithfulness": FaithfulnessMetric(model=judge, async_mode=False),
        "answer_relevancy": AnswerRelevancyMetric(model=judge, async_mode=False),
        "context_precision": ContextualPrecisionMetric(model=judge, async_mode=False),
        "context_recall": ContextualRecallMetric(model=judge, async_mode=False),
    }
    scores = {}
    for name, metric in metrics.items():
        try:
            metric.measure(case)
            scores[name] = metric.score
        except Exception as e:
            print(f"  {r['id']:25} {name} failed: {type(e).__name__}: {str(e)[:100]}")
            scores[name] = None
    print(f"  {r['id']:25} " + "  ".join(
        f"{k[:12]}={'n/a' if v is None else f'{v:.2f}'}" for k, v in scores.items()))
    return scores


def mean(values: list) -> float | None:
    values = [v for v in values if v is not None]
    return round(statistics.mean(values), 3) if values else None


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else max(RESULTS_DIR.glob("run_*.jsonl"))
    rows = [json.loads(line) for line in open(path)]
    if not rows:
        sys.exit(f"{path.name} is empty; run `python -m evals.collect` first and check golden.jsonl")
    errors = [r["id"] for r in rows if r.get("error")]
    if errors:
        print(f"{len(errors)} case(s) errored during collection and will count as failures: {errors}")
    answerable = [r for r in rows if r["type"] == "answerable"]
    retrieved = [r for r in answerable if r["contexts"]]

    print(f"Scoring {path.name} with the LLM judge...")
    judge = GatewayJudge()
    scored = [llm_scores(r, judge) for r in retrieved]

    summary = {
        "routing_accuracy": mean([route_ok(r) for r in rows]),
        "source_hit_rate": mean([source_hit(r) for r in answerable]),
        "noise_ratio": mean([noise_ratio(r) for r in retrieved]),
        "abstain_rate": mean([abstained(r) for r in rows if r["type"] == "unanswerable"]),
        **{k: mean([s[k] for s in scored]) for k in LLM_METRICS},
        "p50_latency_s": statistics.median(r["latency_s"] for r in rows if r["latency_s"] is not None),
    }

    print()
    failed = []
    for name, target in THRESHOLDS.items():
        value = summary[name]
        if value is None:
            continue
        lower = name in LOWER_IS_BETTER
        ok = value <= target if lower else value >= target
        print(f"{'PASS' if ok else 'FAIL'}  {name:18} {value:<6}  (target {'<=' if lower else '>='} {target})")
        if not ok:
            failed.append(name)
    print(f"      p50 latency        {summary['p50_latency_s']}s")

    path.with_suffix(".summary.json").write_text(json.dumps(summary, indent=2))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
