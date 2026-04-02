"""
eval/generate_questions.py
==========================
Genererar ett frågebank (eval/questions.json) automatiskt från Nouses kunskapsgraf.

Strategi:
  - Väljer koncept med hög Hebbian strength (mest validerade)
  - Genererar 4 frågetyper per relation:
      1. Faktafråga ("Vad är X?")
      2. Relationsfråga ("Vad kopplar X till Y?")
      3. Jämförelsefråga ("Vad skiljer X från Y?")  
      4. Implikationsfråga ("Vad innebär att X påverkar Y?")
  - Balanserar domäner
  - Sparar med expected_concepts + expected_relations för scoring

Kör:
    python eval/generate_questions.py          # 50 frågor (default)
    python eval/generate_questions.py --n 100  # anpassat antal
"""
from __future__ import annotations
import json
import argparse
import random
import sys
from pathlib import Path
from collections import defaultdict

# Lägg till src i path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

QUESTION_TEMPLATES = {
    "vad_ar": [
        "Vad är {src} och hur relaterar det till {tgt}?",
        "Förklara vad {src} är i relation till {tgt}.",
        "Vad är {src}?",
    ],
    "relation": [
        "Hur relaterar {src} till {tgt}?",
        "Vad är kopplingen mellan {src} och {tgt}?",
        "Beskriv relationen mellan {src} och {tgt}.",
        "På vilket sätt {rel} {src} {tgt}?",
    ],
    "mekanisk": [
        "Varför {rel} {src} {tgt}?",
        "Hur fungerar kopplingen där {src} {rel} {tgt}?",
    ],
    "implikation": [
        "Vad innebär det att {src} {rel} {tgt}?",
        "Vilka konsekvenser har det att {src} påverkar {tgt}?",
    ],
}

RELATION_VERBS = {
    "är_del_av": "är en del av",
    "använder": "använder",
    "producerar": "producerar",
    "modulerar": "modulerar",
    "stärker": "stärker",
    "reglerar": "reglerar",
    "konsoliderar": "konsoliderar",
    "synkroniserar": "synkroniserar",
    "är_analogt_med": "är analogt med",
    "beskriver": "beskriver",
    "kombineras_med": "kombineras med",
    "påverkar": "påverkar",
    "inspirerar": "inspirerar",
    "kräver": "kräver",
    "licensieras_under": "licensieras under",
    "verifierar": "verifierar",
    "oscillerar": "oscillerar med",
}


def _rel_verb(rel_type: str) -> str:
    return RELATION_VERBS.get(rel_type, rel_type.replace("_", " "))


def _difficulty(strength: float) -> str:
    if strength >= 5.0:
        return "easy"
    if strength >= 2.5:
        return "medium"
    return "hard"


def _make_question(q_id: int, src: str, rel: str, tgt: str,
                   why: str, strength: float, domain: str,
                   q_type: str) -> dict:
    verb = _rel_verb(rel)
    templates = QUESTION_TEMPLATES.get(q_type, QUESTION_TEMPLATES["relation"])
    template = random.choice(templates)

    try:
        question = template.format(src=src, rel=verb, tgt=tgt)
    except KeyError:
        question = f"Beskriv relationen mellan {src} och {tgt}."

    return {
        "id": f"q{q_id:03d}",
        "domain": domain or "okänd",
        "question": question,
        "question_type": q_type,
        "expected_concepts": [src, tgt],
        "expected_relations": [[src, rel, tgt]],
        "why_hint": why[:200] if why else "",
        "strength": round(strength, 2),
        "difficulty": _difficulty(strength),
    }


def generate(n_questions: int = 50, min_strength: float = 1.5,
             seed: int = 42) -> list[dict]:
    random.seed(seed)

    from nouse.field.surface import FieldSurface
    field = FieldSurface(read_only=True)

    # Hämta relationer med styrka
    r = field._conn.execute("""
        MATCH (a:Concept)-[r:Relation]->(b:Concept)
        WHERE r.strength >= $min_s
          AND a.name IS NOT NULL AND b.name IS NOT NULL
        RETURN a.name AS src, r.type AS rel, b.name AS tgt,
               r.why AS why, r.strength AS strength, a.domain AS domain
        ORDER BY r.strength DESC
        LIMIT 2000
    """, {"min_s": min_strength}).get_as_df()

    # Filtrera bort nonsens-koncept i Python
    r = r[r["src"].str.len() > 2]
    r = r[r["tgt"].str.len() > 2]

    print(f"Hämtade {len(r)} kandidatrelationer (strength≥{min_strength})")

    # Gruppa per domän för balans
    by_domain: dict[str, list] = defaultdict(list)
    for _, row in r.iterrows():
        domain = str(row.get("domain") or "okänd")
        by_domain[domain].append(row)

    # Välj representativa relationer — max 5 per domän
    selected = []
    q_types = ["vad_ar", "relation", "relation", "mekanisk", "implikation"]

    domains_sorted = sorted(by_domain.items(), key=lambda x: -len(x[1]))
    per_domain = max(1, n_questions // max(1, len(domains_sorted[:20])))

    for domain, rows in domains_sorted[:30]:
        # Sortera: starka och med why-text prioriteras
        good = sorted(
            [row for row in rows if row.get("why") and len(str(row["why"])) > 20],
            key=lambda x: -x["strength"]
        )
        picks = good[:per_domain] if good else rows[:per_domain]
        selected.extend(picks[:per_domain])

    # Fyll upp till n_questions om det behövs
    if len(selected) < n_questions:
        extras = [row for _, rows in domains_sorted for row in rows
                  if row not in selected]
        selected.extend(extras[:n_questions - len(selected)])

    # Slumpa och trimma
    random.shuffle(selected)
    selected = selected[:n_questions]

    questions = []
    for i, row in enumerate(selected, 1):
        q_type = q_types[i % len(q_types)]
        q = _make_question(
            q_id=i,
            src=str(row["src"]),
            rel=str(row["rel"]),
            tgt=str(row["tgt"]),
            why=str(row.get("why") or ""),
            strength=float(row["strength"]),
            domain=str(row.get("domain") or "okänd"),
            q_type=q_type,
        )
        questions.append(q)

    return questions


def main():
    parser = argparse.ArgumentParser(description="Generera Nouse eval-frågebank")
    parser.add_argument("--n", type=int, default=50, help="Antal frågor")
    parser.add_argument("--min-strength", type=float, default=1.5,
                        help="Minsta Hebbian strength för inkludering")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out", default="eval/questions.json")
    args = parser.parse_args()

    out_path = Path(__file__).parent.parent / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"Genererar {args.n} frågor (seed={args.seed})...")
    questions = generate(args.n, args.min_strength, args.seed)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(questions, f, ensure_ascii=False, indent=2)

    # Statistik
    from collections import Counter
    diff = Counter(q["difficulty"] for q in questions)
    dom = Counter(q["domain"] for q in questions)
    qtype = Counter(q["question_type"] for q in questions)

    print(f"\n✅ {len(questions)} frågor sparade → {out_path}")
    print(f"\nSvårighetsgrad: {dict(diff)}")
    print(f"Frågetyper:     {dict(qtype)}")
    print(f"Domäner (top 8):")
    for d, n in dom.most_common(8):
        print(f"  {n:3d}  {d}")

    print("\nExempel:")
    for q in questions[:3]:
        print(f"  [{q['id']}][{q['difficulty']}] {q['question']}")


if __name__ == "__main__":
    main()
