"""
nouse.inject — One-line cognitive substrate for any LLM.

Basic usage:
    brain = nouse.attach()
    context = brain.context_block(user_input)   # formatted for LLM prompt
    brain.learn(user_input, llm_response)

Eval usage:
    axioms = brain.recall_axioms("mesoscale eddies")
    # → [Axiom(src=..., rel=..., tgt=..., evidence=0.82, flagged=False), ...]

    result = brain.query("What causes ocean heat transport?")
    # → QueryResult(axioms=[...], concepts=[...], confidence=0.81, domains=[...])
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Any


# ── Structured types ──────────────────────────────────────────────────────────

@dataclass
class Axiom:
    """A single relation in the knowledge graph with full metadata."""
    src: str
    rel: str
    tgt: str
    evidence: float          # 0.0–1.0, from evidence_score
    flagged: bool            # assumption_flag — pending deep review
    why: str = ""            # motivation / provenance
    strength: float = 0.5   # Hebbian strength

    @property
    def is_strong(self) -> bool:
        return self.evidence >= 0.75 and not self.flagged

    @property
    def is_uncertain(self) -> bool:
        return self.evidence < 0.45 or self.flagged

    def as_text(self) -> str:
        flag = " ⚑" if self.flagged else ""
        return f"{self.src} —[{self.rel}]→ {self.tgt}  [ev={self.evidence:.2f}]{flag}"


@dataclass
class ConceptProfile:
    """What the graph knows about a single concept."""
    name: str
    summary: str
    claims: list[str]
    evidence_refs: list[str]
    related_terms: list[str]
    uncertainty: float | None
    revision_count: int
    axioms: list[Axiom] = field(default_factory=list)


@dataclass
class QueryResult:
    """Full structured response from brain.query() — for eval harness."""
    query: str
    concepts: list[ConceptProfile]
    axioms: list[Axiom]
    confidence: float          # mean evidence of strong axioms, or 0.0
    domains: list[str]
    has_knowledge: bool

    def context_block(self, max_axioms: int = 15) -> str:
        """Format as LLM-ready context string."""
        return _format_context_block(self.concepts, self.axioms, max_axioms)

    def strong_axioms(self) -> list[Axiom]:
        return [a for a in self.axioms if a.is_strong]

    def flagged_axioms(self) -> list[Axiom]:
        return [a for a in self.axioms if a.flagged]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _format_context_block(
    concepts: list[ConceptProfile],
    axioms: list[Axiom],
    max_axioms: int = 15,
) -> str:
    if not concepts and not axioms:
        return ""

    parts: list[str] = ["[Nouse memory]"]

    # Concept summaries
    for c in concepts[:5]:
        if c.summary:
            flag = f"  (uncertainty={c.uncertainty:.2f})" if c.uncertainty else ""
            parts.append(f"• {c.name}: {c.summary[:200]}{flag}")
        if c.claims:
            for claim in c.claims[:2]:
                parts.append(f"  claim: {claim[:150]}")

    # Strong axioms first, then uncertain
    strong = [a for a in axioms if a.is_strong][:max_axioms]
    uncertain = [a for a in axioms if not a.is_strong][:max(0, max_axioms - len(strong))]

    if strong:
        parts.append("\nValidated relations:")
        for a in strong:
            parts.append(f"  {a.as_text()}")
    if uncertain:
        parts.append("\nUncertain / under review:")
        for a in uncertain:
            parts.append(f"  {a.as_text()}")

    return "\n".join(parts)


def _rows_to_axioms(src_name: str, rows: list[dict]) -> list[Axiom]:
    out = []
    for r in rows:
        raw_ev = r.get("evidence_score")
        strength = float(r.get("strength") or 1.0)
        flagged = bool(r.get("assumption_flag") or False)

        if raw_ev is not None:
            ev = float(raw_ev)
        else:
            # Normalisera Hebbian strength → [0.45, 0.95]
            # strength 1.0 = aldrig traverserat extra = 0.45
            # strength 2.0 = ~20 traversals = 0.72
            # strength 3.0+ = mycket traverserat = 0.90+
            ev = min(0.95, 0.45 + (strength - 1.0) * 0.25)

        out.append(Axiom(
            src=src_name,
            rel=str(r.get("type") or "related_to"),
            tgt=str(r.get("target") or ""),
            evidence=ev,
            flagged=flagged,
            why=str(r.get("why") or ""),
            strength=strength,
        ))
    return out


# ── NouseBrain ────────────────────────────────────────────────────────────────

class NouseBrain:
    """
    Cognitive substrate facade — inject into any LLM pipeline.

    Quick start:
        brain = nouse.attach()
        ctx   = brain.context_block("mesoscale eddies")
        # inject ctx into system prompt, then call your LLM

    Eval:
        result = brain.query("What causes X?")
        print(result.confidence, result.strong_axioms())
    """

    def __init__(self, db_path: str | Path | None = None, read_only: bool = False):
        from nouse.field.surface import FieldSurface
        self._field = FieldSurface(db_path=db_path, read_only=read_only)
        self._read_only = read_only
        self._input_hooks: list[Callable] = []
        self._output_hooks: list[Callable] = []

    # ── Primary query API ─────────────────────────────────────────────────────

    def recall_axioms(self, concept_or_query: str, top_k: int = 8) -> list[Axiom]:
        """
        Return structured Axiom objects for a concept or free-text query.
        Sorted by evidence score descending.
        """
        axioms: list[Axiom] = []
        nodes = self._field.node_context_for_query(concept_or_query, limit=top_k)
        for node in nodes:
            name = node.get("name", "")
            if not name:
                continue
            try:
                rows = self._field.out_relations(name)
                axioms.extend(_rows_to_axioms(name, rows))
            except Exception:
                pass
        axioms.sort(key=lambda a: -a.evidence)
        return axioms

    def query(self, question: str, top_k: int = 6) -> QueryResult:
        """
        Full structured query — for eval harness.
        Returns concepts + axioms + confidence score + domains.
        """
        nodes = self._field.node_context_for_query(question, limit=top_k)
        profiles: list[ConceptProfile] = []
        all_axioms: list[Axiom] = []
        domains: set[str] = set()

        for node in nodes:
            name = node.get("name", "")
            if not name:
                continue
            k = self._field.concept_knowledge(name)
            try:
                rel_rows = self._field.out_relations(name)
                node_axioms = _rows_to_axioms(name, rel_rows)
            except Exception:
                node_axioms = []

            # domain from concept
            try:
                concepts = self._field.concepts()
                for c in concepts:
                    if c.get("name") == name and c.get("domain"):
                        domains.add(c["domain"])
            except Exception:
                pass

            profiles.append(ConceptProfile(
                name=name,
                summary=k.get("summary", "") or node.get("summary", ""),
                claims=k.get("claims", []),
                evidence_refs=k.get("evidence_refs", []),
                related_terms=k.get("related_terms", []),
                uncertainty=k.get("uncertainty"),
                revision_count=k.get("revision_count", 0),
                axioms=node_axioms,
            ))
            all_axioms.extend(node_axioms)

        all_axioms.sort(key=lambda a: -a.evidence)
        strong = [a for a in all_axioms if a.is_strong]
        confidence = (sum(a.evidence for a in strong) / len(strong)) if strong else 0.0

        return QueryResult(
            query=question,
            concepts=profiles,
            axioms=all_axioms,
            confidence=confidence,
            domains=sorted(domains),
            has_knowledge=bool(profiles),
        )

    def context_block(self, query: str, top_k: int = 6, max_axioms: int = 15) -> str:
        """
        Return a formatted context string ready to inject into an LLM system prompt.
        Empty string if nothing relevant found.
        """
        result = self.query(query, top_k=top_k)
        return result.context_block(max_axioms=max_axioms)

    # ── Legacy / convenience API ──────────────────────────────────────────────

    def recall(self, query: str, top_k: int = 5) -> str:
        """Backwards-compatible: return context as plain text."""
        return self.context_block(query, top_k=top_k)

    def recall_relations(self, concept: str) -> list[dict]:
        """Return raw graph relations for a concept (dict format)."""
        try:
            return self._field.out_relations(concept)
        except Exception:
            return []

    def learn(self, prompt: str, response: str, source: str = "conversation") -> None:
        """Extract and store knowledge from a prompt/response pair."""
        import asyncio
        from nouse.daemon.extractor import extract_relations
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                    ex.submit(asyncio.run, extract_relations(
                        prompt + "\n" + response, self._field, source_tag=source
                    )).result(timeout=30)
            else:
                loop.run_until_complete(extract_relations(
                    prompt + "\n" + response, self._field, source_tag=source
                ))
        except Exception:
            pass

    def add(
        self,
        src: str,
        rel_type: str,
        tgt: str,
        *,
        why: str = "",
        evidence_score: float = 0.6,
    ) -> None:
        """Directly add a relation to the knowledge graph."""
        self._field.add_relation(src, rel_type, tgt, why=why, evidence_score=evidence_score)

    def on_input(self, fn: Callable) -> Callable:
        """Decorator: enrich prompt before it reaches the LLM."""
        self._input_hooks.append(fn)
        return fn

    def on_output(self, fn: Callable) -> Callable:
        """Decorator: process response after LLM returns."""
        self._output_hooks.append(fn)
        return fn

    def process_input(self, prompt: str) -> str:
        for hook in self._input_hooks:
            try:
                prompt = hook(prompt)
            except Exception:
                pass
        return prompt

    def process_output(self, prompt: str, response: str) -> None:
        for hook in self._output_hooks:
            try:
                hook(prompt, response)
            except Exception:
                pass

    def stats(self) -> dict:
        return self._field.stats()

    @property
    def field(self):
        return self._field


# ── Entry point ───────────────────────────────────────────────────────────────

def attach(db_path: str | Path | None = None, read_only: bool = False) -> NouseBrain:
    """
    One-line entry point:
        brain = nouse.attach()               # read+write
        brain = nouse.attach(read_only=True) # eval / parallel reads
    """
    return NouseBrain(db_path=db_path, read_only=read_only)
