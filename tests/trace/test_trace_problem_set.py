from __future__ import annotations

from pathlib import Path

from ruamel.yaml import YAML

from nouse.trace.output_trace import build_attack_plan


def test_trace_problem_set_meets_expected_minimum_classification():
    pset = Path("results/eval_set_trace_observability.yaml")
    assert pset.exists()

    yaml = YAML(typ="safe")
    data = yaml.load(pset.read_text(encoding="utf-8", errors="ignore")) or {}
    cases = data.get("cases") or []
    assert cases, "Problemsetet maste innehalla minst ett case."

    for case in cases:
        prompt = str(case.get("prompt") or "").strip()
        assert prompt, f"Tom prompt i case: {case.get('id')}"
        expect = case.get("expect") or {}
        min_q = int(expect.get("min_questions", 0) or 0)
        min_c = int(expect.get("min_claims", 0) or 0)
        min_a = int(expect.get("min_assumptions", 0) or 0)

        plan = build_attack_plan(prompt)
        qn = len(plan.get("questions") or [])
        cn = len(plan.get("claims") or [])
        an = len(plan.get("assumptions") or [])

        assert qn >= min_q, f"{case.get('id')} expected questions>={min_q}, got {qn}"
        assert cn >= min_c, f"{case.get('id')} expected claims>={min_c}, got {cn}"
        assert an >= min_a, f"{case.get('id')} expected assumptions>={min_a}, got {an}"
