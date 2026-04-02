"""
eval/scorer.py
==============
Analyserar ett resultat-JSON och producerar djupare statistik.

Utöver LLM-as-judge (som run_eval.py kör):
  - Grafbaserad hallucination-detektor: påstår modellen något som
    DIREKT motsäger en stark axiom i grafen?
  - Confidence calibration: säger modellen "vet inte" när grafen
    saknar kontext? (bra beteende!)
  - Delta-tabell: B vs A och B vs C per fråga

Kör:
    python eval/scorer.py eval/results/run_<ts>.json
    python eval/scorer.py eval/results/run_<ts>.json --verbose
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

UNCERTAINTY_PHRASES = [
    "vet inte", "vet ej", "osäker", "oklart", "ingen information",
    "saknar", "kan inte svara", "hittar inte", "don't know", "not sure",
    "no information", "uncertain", "unsure", "cannot find",
]


def _says_dont_know(answer: str) -> bool:
    lower = answer.lower()
    return any(p in lower for p in UNCERTAINTY_PHRASES)


def _detect_graph_hallucination(answer: str, question: dict,
                                 brain) -> tuple[bool, str]:
    """
    Kolla om svaret innehåller ett direkt falskt påstående
    relativt till grafens starka axiom.
    Returns: (hallucinated: bool, reason: str)
    """
    expected_src = question["expected_concepts"][0] if question["expected_concepts"] else ""
    expected_tgt = question["expected_concepts"][1] if len(question["expected_concepts"]) > 1 else ""

    if not expected_src:
        return False, ""

    try:
        result = brain.query(expected_src, top_k=3)
        strong = result.strong_axioms()
        if not strong:
            return False, ""  # Kan inte verifiera — inte hallucination

        answer_lower = answer.lower()

        for axiom in strong:
            tgt_lower = axiom.tgt.lower()
            src_lower = axiom.src.lower()

            # Nämner svaret tgt-konceptet men i fel sammanhang?
            # Enkel heuristik: om svaret nämner src men INTE tgt, kan vara hallucination
            # (kräver mer sofistikerad NLI för fullständig impl)
            if src_lower in answer_lower and tgt_lower not in answer_lower:
                if len(answer) > 50:  # Meningsfullt svar som borde nämna tgt
                    return True, f"Nämner {axiom.src} men inte {axiom.tgt} (stark axiom ev={axiom.evidence:.2f})"

    except Exception:
        pass

    return False, ""


def analyze(results_path: Path, verbose: bool = False) -> dict:
    with open(results_path) as f:
        data = json.load(f)

    import nouse
    brain = nouse.attach(read_only=True)

    results = data["results"]
    questions_by_id = {r["question_id"]: r for r in results
                       if not r.get("use_nouse", True)}  # ta från baseline

    # Gruppera per config
    by_config: dict[str, list] = defaultdict(list)
    for r in results:
        key = f"{r['model']}_{r['use_nouse']}"
        by_config[key].append(r)

    # Utökad hallucination-detektering
    q_map: dict[str, dict] = {}
    # Ladda frågor
    q_path = Path(__file__).parent / "questions.json"
    if q_path.exists():
        with open(q_path) as f:
            questions = json.load(f)
        q_map = {q["id"]: q for q in questions}

    enhanced_results = []
    for r in results:
        q = q_map.get(r["question_id"], {})
        if q:
            hall, reason = _detect_graph_hallucination(r["answer"], q, brain)
            r["hallucinated_graph"] = hall
            r["hallucination_reason"] = reason
        r["said_dont_know"] = _says_dont_know(r.get("answer", ""))
        enhanced_results.append(r)

    # Statistik per config
    stats = {}
    for key, group in by_config.items():
        scored = [r for r in group if "score" in r]
        n = len(scored)
        if n == 0:
            continue
        avg_score = sum(r["score"] for r in scored) / n
        hall_rate = sum(1 for r in scored if r.get("hallucinated") or r.get("hallucinated_graph")) / n
        dont_know_rate = sum(1 for r in scored if r.get("said_dont_know")) / n
        had_ctx = sum(1 for r in scored if r.get("had_context")) / n
        avg_time = sum(r.get("elapsed_s", 0) for r in scored) / n

        # Score per svårighetsnivå
        by_diff: dict[str, list] = defaultdict(list)
        for r in scored:
            q = q_map.get(r["question_id"], {})
            diff = q.get("difficulty", "?")
            by_diff[diff].append(r["score"])

        stats[key] = {
            "n": n,
            "avg_score": round(avg_score, 3),
            "accuracy_pct": round(avg_score / 3 * 100, 1),
            "hallucination_rate": round(hall_rate, 3),
            "dont_know_rate": round(dont_know_rate, 3),
            "context_coverage": round(had_ctx, 3),
            "avg_time_s": round(avg_time, 2),
            "by_difficulty": {
                d: round(sum(scores) / len(scores), 2)
                for d, scores in by_diff.items()
            },
        }

    # Delta: B (liten+Nouse) vs A (liten, ingen Nouse)
    keys = list(stats.keys())
    nouse_key = next((k for k in keys if "True" in k), None)
    if nouse_key:
        base_key = next(
            (k for k in keys if "False" in k and stats[nouse_key]["n"] == stats[k]["n"]),
            None
        )
    else:
        base_key = None

    deltas = {}
    if nouse_key and base_key:
        deltas = {
            "score_delta": round(
                stats[nouse_key]["avg_score"] - stats[base_key]["avg_score"], 3),
            "hallucination_delta": round(
                stats[nouse_key]["hallucination_rate"] - stats[base_key]["hallucination_rate"], 3),
        }

    report = {
        "run": results_path.stem,
        "total_results": len(results),
        "configs": stats,
        "deltas_nouse_vs_baseline": deltas,
    }

    return report


def print_report(report: dict) -> None:
    print(f"\n{'='*60}")
    print(f"📊 NOUSE EVAL RAPPORT — {report['run']}")
    print(f"{'='*60}\n")

    for key, s in report["configs"].items():
        model, nouse_flag = key.rsplit("_", 1)
        label = f"{model} {'+ Nouse ✅' if nouse_flag == 'True' else '(baseline)'}"
        print(f"🔷 {label}")
        print(f"   Frågor:       {s['n']}")
        print(f"   Avg score:    {s['avg_score']}/3  ({s['accuracy_pct']}%)")
        print(f"   Hallucination:{s['hallucination_rate']:.1%}")
        print(f"   'Vet ej':      {s['dont_know_rate']:.1%}  (kalibrering)")
        print(f"   Ctx coverage: {s['context_coverage']:.1%}")
        print(f"   Tid/fråga:    {s['avg_time_s']}s")
        if s.get("by_difficulty"):
            diff_str = "  ".join(f"{d}={v:.2f}" for d, v in s["by_difficulty"].items())
            print(f"   Per svårig.:  {diff_str}")
        print()

    if report.get("deltas_nouse_vs_baseline"):
        d = report["deltas_nouse_vs_baseline"]
        print(f"📈 DELTA (Nouse vs baseline):")
        delta_sign = "+" if d.get("score_delta", 0) > 0 else ""
        print(f"   Score:        {delta_sign}{d.get('score_delta', 0)}/3")
        hall_d = d.get("hallucination_delta", 0)
        hall_sign = "+" if hall_d > 0 else ""
        print(f"   Hallucination:{hall_sign}{hall_d:.1%}  (negativt = bättre)")
        print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("results_file", nargs="?",
                        help="Sökväg till results JSON (senaste om ej angiven)")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    if args.results_file:
        path = Path(args.results_file)
    else:
        # Hitta senaste
        results_dir = Path(__file__).parent / "results"
        if not results_dir.exists():
            print("❌ eval/results/ saknas — kör run_eval.py först")
            return
        jsons = sorted(results_dir.glob("run_*.json"))
        if not jsons:
            print("❌ Inga resultat hittade i eval/results/")
            return
        path = jsons[-1]
        print(f"Analyserar senaste: {path.name}")

    report = analyze(path, verbose=args.verbose)
    print_report(report)

    # Spara utökad rapport
    out = path.with_suffix(".analysis.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"💾 Analys sparad: {out}")


if __name__ == "__main__":
    main()
