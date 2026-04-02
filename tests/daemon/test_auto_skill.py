from __future__ import annotations

from nouse.daemon.auto_skill import AutoSkillPolicy, evaluate_claim, relation_fingerprint


def _relation(**kwargs):  # type: ignore[no-untyped-def]
    base = {
        "src": "A",
        "domain_src": "x",
        "type": "orsakar",
        "tgt": "B",
        "domain_tgt": "y",
        "why": "Tydlig mekanism med 12% signal och domankorsning i texten.",
    }
    base.update(kwargs)
    return base


def test_relation_fingerprint_is_stable_for_case_and_whitespace():
    a = _relation(src=" A ", type=" ORSAKAR ", tgt="b")
    b = _relation(src="a", type="orsakar", tgt=" B ")
    assert relation_fingerprint(a) == relation_fingerprint(b)


def test_evaluate_claim_marks_duplicate_in_same_batch():
    policy = AutoSkillPolicy(mode="shadow", prod_threshold=0.75, sandbox_threshold=0.55, enforce_writes=False)
    seen: set[str] = set()
    first = evaluate_claim(_relation(), policy=policy, seen_fingerprints=seen)
    second = evaluate_claim(_relation(), policy=policy, seen_fingerprints=seen)
    assert second.auto_score < first.auto_score


def test_observe_mode_never_routes_to_drop_even_low_score():
    policy = AutoSkillPolicy(mode="observe", prod_threshold=0.75, sandbox_threshold=0.55, enforce_writes=True)
    low = evaluate_claim(_relation(why="", src="A", tgt="A"), policy=policy, seen_fingerprints=set())
    assert low.route == "prod"


def test_production_mode_can_route_to_drop_for_very_low_score():
    policy = AutoSkillPolicy(mode="production", prod_threshold=0.75, sandbox_threshold=0.55, enforce_writes=True)
    low = evaluate_claim(_relation(why="", src="A", tgt="A"), policy=policy, seen_fingerprints=set())
    assert low.route == "drop"
