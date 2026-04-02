"""
CognitiveConductor — Kognitionsloopen
======================================
Kopplar samman alla hjärnmodulerna till en sammanhängande kognitiv cykel:

  ny episod → limbic signal → TDA-analys → F_bisoc-scoring →
  Global Workspace WTA → minnesskrivning → självreflektion

Inspirerat av clawbot's agent-loop (intake → context assembly → inference →
tool execution → persistence) men för kognitiv arkitektur — inte chat.

Tre publika klasser:

  CognitiveConductor   — kör en enstaka kognitiv cykel (manuellt eller autonomt)
  AutonomyLoop         — bakgrunds-asyncio-task som kör cykler utan mänsklig trigger
  SelfModificationGuard — guardrail för självmodifieringsförslag

Kognitiva cykeln steg-för-steg:
  1. Skriv episod till episodminne (ingress)
  2. Hämta relaterade episoder (retrieval window)
  3. Beräkna TDA-signaturer (Betti-nummer H0, H1) för varje domän
  4. Kör limbisk cykel: uppdatera DA/NA/ACh/λ
  5. Beräkna F_bisoc: prediction_error + λ × complexity_blend
  6. Bygg förslag till Global Workspace från aktiva moduler
  7. WTA-konkurrens → vinnare broadcastas
  8. Skriv eventuell bisociation-syntes till semantiskt minne
  9. Om stark discovery: föreslå självmodifiering (via guardrail)

Self-modification guardrail:
  - Förslag sparas i self_training men EXEKVERAS INTE automatiskt
  - Kräver separat godkännande (approval_token) via kernel_execute_self_update
  - Auto-godkännande är INAKTIVERAT som standard — aktiveras via env NOUSE_AUTO_SELF_MOD=1
  - Alla förslag loggas med evidenskedja
"""
from __future__ import annotations

import asyncio
import logging
import math
import os
import uuid
from dataclasses import dataclass, field as dc_field
from datetime import datetime, timezone
from typing import Any

from nouse.limbic.signals import (
	LimbicState,
	load_state as load_limbic,
	run_limbic_cycle,
	save_state as save_limbic,
)
from nouse.memory.store import MemoryStore
from nouse.orchestrator.global_workspace import GlobalWorkspace, WorkspaceProposal
from nouse.self_layer.living_core import (
	append_identity_memory,
	load_living_core,
	record_self_training_iteration,
)
from nouse.tda.bridge import compute_betti, compute_distance_matrix, topological_similarity

log = logging.getLogger("nouse.conductor")

# ── Konfiguration ────────────────────────────────────────────────────────────

_BISOC_THRESHOLD    = float(os.getenv("NOUSE_BISOC_THRESHOLD", "0.45"))
_AUTONOMY_INTERVAL  = float(os.getenv("NOUSE_AUTONOMY_INTERVAL_SEC", "120.0"))
_AUTONOMY_ENABLED   = os.getenv("NOUSE_AUTONOMY_ENABLED", "1").strip() in {"1", "true", "yes"}
_AUTO_SELF_MOD      = os.getenv("NOUSE_AUTO_SELF_MOD", "0").strip() in {"1", "true", "yes"}
_RETRIEVAL_WINDOW   = int(os.getenv("NOUSE_CONDUCTOR_WINDOW", "12"))
_AROUSAL_DORMANT    = float(os.getenv("NOUSE_AROUSAL_DORMANT", "0.88"))

_SELF_MOD_CONFIDENCE_MIN = 0.72
_SELF_MOD_DISCOVERY_MIN  = 4


def _now_iso() -> str:
	return datetime.now(timezone.utc).isoformat()


# ── Dataklasser ───────────────────────────────────────────────────────────────

@dataclass
class CycleResult:
	"""Resultat av en kognitiv cykel."""
	episode_id:              str
	limbic_state:            LimbicState
	bisociation_score:       float
	bisociation_verdict:     str
	tda_h0_a:                int
	tda_h1_a:                int
	tda_h0_b:                int
	tda_h1_b:                int
	topo_similarity:         float
	workspace_winner:        str | None
	new_relations:           int
	self_update_proposed:    bool
	ts:                      str


# ── Bisociation-scoring (F_bisoc) ────────────────────────────────────────────

def _f_bisoc(
	h0_a: int, h1_a: int,
	h0_b: int, h1_b: int,
	lam: float,
) -> tuple[float, str]:
	"""
	F_bisoc = prediction_error + λ × complexity_blend

	prediction_error = topologisk olikhet (1 - τ)
	complexity_blend = H1(a) + H1(b) normerat (cykliska strukturer)

	Verdict:
	  F_bisoc > _BISOC_THRESHOLD → "BISOCIATION"
	  annars                     → "ASSOCIATION"
	"""
	tau = topological_similarity(h0_a, h1_a, h0_b, h1_b)
	prediction_error = 1.0 - tau

	max_h1 = max(h1_a + h1_b, 1)
	complexity_blend = (h1_a + h1_b) / max_h1

	score = prediction_error + lam * complexity_blend
	score = max(0.0, min(1.0, score / 2.0))

	verdict = "BISOCIATION" if score >= _BISOC_THRESHOLD else "ASSOCIATION"
	return score, verdict


# ── CognitiveConductor ────────────────────────────────────────────────────────

class CognitiveConductor:
	"""
	Dirigenten — kopplar samman alla kognitiva moduler.

	Usage:
		conductor = CognitiveConductor()
		result = await conductor.run_cognitive_cycle(
			episode_text="...",
			domain="fysik",
			vectors=[[...], ...],
		)
	"""

	def __init__(
		self,
		memory: MemoryStore | None = None,
		workspace: GlobalWorkspace | None = None,
	) -> None:
		self.memory = memory or MemoryStore()
		self.workspace = workspace or GlobalWorkspace()
		self._discovery_streak: int = 0

	async def run_cognitive_cycle(
		self,
		episode_text: str,
		domain: str = "okänd",
		vectors: list[list[float]] | None = None,
		*,
		source: str = "conductor",
		session_id: str = "",
	) -> CycleResult:
		"""
		Kör en full kognitiv cykel.

		Steg:
		  1. Skriv episod till minnet
		  2. Hämta relaterade episoder (retrieval window)
		  3. TDA på episodvektorerna uppdelat på domäner
		  4. Limbisk cykel: uppdatera DA/NA/ACh/λ
		  5. F_bisoc scoring
		  6. Global Workspace WTA
		  7. Skriv syntes om bisociation hittas
		  8. Självmodifieringsförslag om strong discovery streak
		"""
		episode_id = str(uuid.uuid4())
		log.info(f"Kognitiv cykel start [ep={episode_id[:8]} domain={domain}]")

		# ── Steg 1: Skriv episod ─────────────────────────────────────────────
		self.memory.ingest_episode(
			text=episode_text,
			meta={"domain_hint": domain, "source": source, "session_id": session_id},
			relations=[],
		)

		# ── Steg 2: Hämta relaterade episoder ───────────────────────────────
		episodes = self.memory.working_snapshot(limit=_RETRIEVAL_WINDOW)
		log.debug(f"Retrieval: {len(episodes)} episoder funna")

		# ── Steg 3: TDA på episodvektorer ───────────────────────────────────
		h0_a, h1_a, h0_b, h1_b = 1, 0, 1, 0
		topo_sim = 0.5

		if vectors and len(vectors) >= 2:
			mid = max(1, len(vectors) // 2)
			vecs_a = vectors[:mid]
			vecs_b = vectors[mid:]

			try:
				dm_a = compute_distance_matrix(vecs_a)
				dm_b = compute_distance_matrix(vecs_b)
				h0_a, h1_a = compute_betti(dm_a)
				h0_b, h1_b = compute_betti(dm_b)
				topo_sim = topological_similarity(h0_a, h1_a, h0_b, h1_b)
				log.debug(f"TDA: H0=({h0_a},{h0_b}) H1=({h1_a},{h1_b}) τ={topo_sim:.3f}")
			except Exception as exc:
				log.warning(f"TDA misslyckades: {exc}")

		# ── Steg 4: Limbisk cykel ────────────────────────────────────────────
		limbic = load_limbic()
		bisoc_candidates = 1 if h1_a > 0 or h1_b > 0 else 0
		novel_domains = 1 if topo_sim < 0.4 else 0

		limbic = run_limbic_cycle(
			limbic,
			new_relations=len(episodes),
			discoveries=self._discovery_streak,
			bisociation_candidates=bisoc_candidates,
			novel_domains=novel_domains,
			active_domains=max(1, len(set(e.get("domain_hint", "") for e in episodes))),
		)

		# ── Steg 5: F_bisoc ──────────────────────────────────────────────────
		f_bisoc, verdict = _f_bisoc(h0_a, h1_a, h0_b, h1_b, limbic.lam)
		log.info(f"F_bisoc={f_bisoc:.3f} verdict={verdict} λ={limbic.lam:.2f}")

		# ── Steg 6: Global Workspace WTA ────────────────────────────────────
		proposals: list[WorkspaceProposal] = [
			WorkspaceProposal(
				module="episodic_memory",
				content={"episode_id": episode_id, "text_preview": episode_text[:140]},
				salience=0.5 + 0.3 * limbic.dopamine,
				domain=domain,
			),
			WorkspaceProposal(
				module="tda_bisociation",
				content={
					"f_bisoc": f_bisoc,
					"verdict": verdict,
					"h0": (h0_a, h0_b),
					"h1": (h1_a, h1_b),
				},
				salience=f_bisoc * (1.0 + limbic.lam),
				domain=domain,
			),
			WorkspaceProposal(
				module="limbic_homeostasis",
				content={
					"arousal": limbic.arousal,
					"performance": limbic.performance,
					"lam": limbic.lam,
				},
				salience=limbic.performance * 0.6,
				domain="meta",
			),
		]

		ws_result = await self.workspace.competition_step(proposals, limbic)
		winner_module = ws_result.winner.module if ws_result.winner else None

		# ── Steg 7: Skriv syntes om bisociation ─────────────────────────────
		new_relations = 0
		if verdict == "BISOCIATION":
			self._discovery_streak += 1
			synthesis = (
				f"[Bisociation discovery] domain={domain} "
				f"F_bisoc={f_bisoc:.3f} τ={topo_sim:.3f} "
				f"H1=({h1_a},{h1_b}) λ={limbic.lam:.2f} "
				f"ep={episode_id[:8]}"
			)
			new_relations = 1
			log.info(f"Bisociation syntes skriven: {synthesis[:80]}")
			self.memory.ingest_episode(
				text=synthesis,
				meta={
					"domain_hint": "bisociation_synthesis",
					"source": "conductor_synthesis",
					"session_id": session_id,
				},
				relations=[],
			)
		else:
			self._discovery_streak = 0

		# ── Steg 8: Självmodifieringsförslag ────────────────────────────────
		self_update_proposed = False
		if (
			self._discovery_streak >= _SELF_MOD_DISCOVERY_MIN
			and f_bisoc >= _SELF_MOD_CONFIDENCE_MIN
		):
			self_update_proposed = self._propose_self_modification(
				rationale=(
					f"Stark kreativ streak: {self._discovery_streak} bisociationer i rad. "
					f"Genomsnittlig F_bisoc={f_bisoc:.3f}. Domän: {domain}. "
					f"Föreslår att addera 'bisociativ nyfikenhet' som aktivt värde."
				),
				confidence=f_bisoc,
				session_id=session_id,
			)

		result = CycleResult(
			episode_id=episode_id,
			limbic_state=limbic,
			bisociation_score=f_bisoc,
			bisociation_verdict=verdict,
			tda_h0_a=h0_a,
			tda_h1_a=h1_a,
			tda_h0_b=h0_b,
			tda_h1_b=h1_b,
			topo_similarity=topo_sim,
			workspace_winner=winner_module,
			new_relations=new_relations,
			self_update_proposed=self_update_proposed,
			ts=_now_iso(),
		)

		log.info(
			f"Kognitiv cykel klar: winner={winner_module} "
			f"verdict={verdict} self_mod={self_update_proposed}"
		)
		return result

	def _propose_self_modification(
		self,
		rationale: str,
		confidence: float,
		session_id: str = "",
	) -> bool:
		"""
		Föreslå en självmodifiering — sparar till self_training men exekverar ALDRIG automatiskt.

		Guardrails:
		  - Kräver confidence >= _SELF_MOD_CONFIDENCE_MIN
		  - NOUSE_AUTO_SELF_MOD=0 som standard → kräver mänskligt godkännande alltid
		  - Alla förslag loggas med full evidenskedja
		  - Kodmodifiering är FÖRBJUDEN (kräver kernel_execute_self_update)
		"""
		if confidence < _SELF_MOD_CONFIDENCE_MIN:
			return False

		proposal_id = str(uuid.uuid4())[:8]
		log.info(f"Självmodifieringsförslag [{proposal_id}]: {rationale[:80]}")

		record_self_training_iteration(
			known_data_sources=["bisociation_engine", "tda_bridge", "limbic_signals"],
			meta_reflection=f"Förslag [{proposal_id}]: {rationale[:600]}",
			reflection=(
				f"Confidence={confidence:.3f}. Streak={self._discovery_streak}. "
				f"Status: FÖRESLAGEN — väntar på godkännande via kernel_execute_self_update."
			),
			session_id=session_id,
		)

		append_identity_memory(
			note=(
				f"[SELF-MOD PROPOSAL {proposal_id}] {rationale[:400]} "
				f"(confidence={confidence:.3f}, auto_exec={_AUTO_SELF_MOD})"
			),
			tags=["self_modification_proposal", "bisociation", "pending_review"],
			session_id=session_id,
			kind="self_modification_proposal",
		)

		return True


# ── AutonomyLoop ──────────────────────────────────────────────────────────────

class AutonomyLoop:
	"""
	Bakgrunds-asyncio-task som kör kognitiva cykler utan mänsklig trigger.

	Baserat på clawbot's daemon-mönster:
	  - Serialiserad kö (en cykel i taget)
	  - Episoder köas och processas i ordning
	  - Idle → spontan reflektion efter 3+ tomma ticks
	  - Hög arousal → dormant (Yerkes-Dodson overstimulation guard)

	Aktiveras via: NOUSE_AUTONOMY_ENABLED=1 (standard)
	Intervall:     NOUSE_AUTONOMY_INTERVAL_SEC (standard: 120 sekunder)
	"""

	def __init__(
		self,
		conductor: CognitiveConductor | None = None,
		interval: float | None = None,
	) -> None:
		self.conductor = conductor or CognitiveConductor()
		self.interval  = interval if interval is not None else _AUTONOMY_INTERVAL
		self._running  = False
		self._queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=64)
		self._task: asyncio.Task[None] | None = None
		self._cycle_count = 0
		self._idle_ticks  = 0

	def enqueue(
		self,
		text: str,
		domain: str = "okänd",
		vectors: list[list[float]] | None = None,
		source: str = "external",
		session_id: str = "",
	) -> bool:
		"""
		Lägg till ett episod i autonomitetskön.
		Returnerar False om kön är full.
		"""
		try:
			self._queue.put_nowait({
				"text": text,
				"domain": domain,
				"vectors": vectors or [],
				"source": source,
				"session_id": session_id,
			})
			return True
		except asyncio.QueueFull:
			log.warning("Autonomitetskön full — episod ignorerad")
			return False

	async def start(self) -> None:
		"""Starta autonomitetsslingan som bakgrundsuppgift."""
		if not _AUTONOMY_ENABLED:
			log.info("AutonomyLoop: inaktiv (NOUSE_AUTONOMY_ENABLED=0)")
			return
		if self._running:
			return
		self._running = True
		self._task = asyncio.create_task(self._loop(), name="b76-autonomy-loop")
		log.info(f"AutonomyLoop startad: intervall={self.interval}s")

	async def stop(self) -> None:
		"""Stoppa slingan rent."""
		self._running = False
		if self._task:
			self._task.cancel()
			try:
				await self._task
			except asyncio.CancelledError:
				pass
			self._task = None
		log.info("AutonomyLoop stoppad")

	async def _loop(self) -> None:
		"""Huvudslingan — körs tills stop() anropas."""
		while self._running:
			try:
				await self._tick()
			except Exception as exc:
				log.error(f"Autonomitetsslinga fel: {exc}", exc_info=True)
			await asyncio.sleep(self.interval)

	async def _tick(self) -> None:
		"""
		En tick i autonomitetsslingan:
		  1. Kontrollera limbisk arousal (dormant guard)
		  2. Processera kö-episoder (max 4 per tick)
		  3. Om inget att göra: kör spontan reflektion
		"""
		limbic = load_limbic()

		if limbic.arousal > _AROUSAL_DORMANT:
			log.debug(
				f"AutonomyLoop DORMANT: arousal={limbic.arousal:.2f} > {_AROUSAL_DORMANT}"
			)
			return

		processed = 0
		while not self._queue.empty() and processed < 4:
			try:
				item = self._queue.get_nowait()
			except asyncio.QueueEmpty:
				break

			await self.conductor.run_cognitive_cycle(
				episode_text=item["text"],
				domain=item["domain"],
				vectors=item.get("vectors") or [],
				source=item.get("source", "autonomy_loop"),
				session_id=item.get("session_id", ""),
			)
			self._queue.task_done()
			processed += 1
			self._cycle_count += 1
			self._idle_ticks = 0

		if processed == 0:
			self._idle_ticks += 1
			await self._idle_reflection(limbic)

	async def _idle_reflection(self, limbic: LimbicState) -> None:
		"""
		Spontan reflektion när slingan är idle.
		Aktiveras efter 3+ idle-ticks för att undvika konstantt brus.
		"""
		if self._idle_ticks < 3:
			return

		arousal_label = (
			"fokuserad" if limbic.arousal > 0.6
			else "nyfiken" if limbic.arousal > 0.3
			else "vilande"
		)
		thought = (
			f"[Spontan reflektion #{self._idle_ticks}] "
			f"Tillstånd: {arousal_label}. "
			f"DA={limbic.dopamine:.2f} NA={limbic.noradrenaline:.2f} "
			f"ACh={limbic.acetylcholine:.2f} λ={limbic.lam:.2f}. "
			f"Performance={limbic.performance:.2f}. "
			f"Cykler hittills: {self._cycle_count}."
		)

		log.info(f"Idle reflektion: {thought}")
		await self.conductor.run_cognitive_cycle(
			episode_text=thought,
			domain="meta_reflection",
			vectors=[],
			source="autonomy_idle",
		)


# ── SelfModificationGuard ─────────────────────────────────────────────────────

class SelfModificationGuard:
	"""
	Guardrail för alla självmodifieringsoperationer.

	Hierarki (hög → låg risk):
	  1. Läs-operationer (alltid tillåtet)
	  2. Minnesskrivning / self_training-logg (conductor hanterar detta)
	  3. Identity-värden och mission (kräver approval_token)
	  4. Kodmodifiering / kernel_execute (alltid förbjudet via conductor)

	Bedömer om en föreslagen ändring är tillåten men EXEKVERAR ALDRIG.
	"""

	def evaluate(
		self,
		change_type: str,
		delta: str,
		evidence: str,
		confidence: float,
		limbic: LimbicState,
	) -> dict[str, Any]:
		"""
		Bedöm en självmodifieringsförfrågan.

		Returns:
			{"permitted": bool, "reason": str, "risk_level": str, "requires": list[str]}
		"""
		if change_type in ("code_modification", "kernel_execute"):
			return {
				"permitted": False,
				"reason": "Kodmodifiering kräver mänskligt godkännande via kernel_execute_self_update.",
				"risk_level": "prohibited",
				"requires": ["human_approval", "NOUSE_KERNEL_ALLOW_GUARDED_WRITES=1"],
			}

		if change_type in ("mission_update", "boundary_update"):
			if confidence < 0.80:
				return {
					"permitted": False,
					"reason": f"Uppdragsjusteringar kräver confidence >= 0.80 (nu {confidence:.2f}).",
					"risk_level": "high",
					"requires": ["confidence >= 0.80", "human_review"],
				}
			return {
				"permitted": _AUTO_SELF_MOD,
				"reason": (
					"Auto-godkänd (NOUSE_AUTO_SELF_MOD=1)." if _AUTO_SELF_MOD
					else "Kräver mänskligt godkännande (NOUSE_AUTO_SELF_MOD=0)."
				),
				"risk_level": "high",
				"requires": [] if _AUTO_SELF_MOD else ["human_approval"],
			}

		if change_type == "value_add":
			if confidence >= _SELF_MOD_CONFIDENCE_MIN and limbic.performance > 0.5:
				return {
					"permitted": _AUTO_SELF_MOD,
					"reason": (
						f"Värdetillägg tillåtet vid confidence={confidence:.2f}, "
						f"performance={limbic.performance:.2f}."
					),
					"risk_level": "medium",
					"requires": [] if _AUTO_SELF_MOD else ["human_approval"],
				}
			return {
				"permitted": False,
				"reason": (
					f"Otillräcklig evidens: confidence={confidence:.2f} "
					f"(min {_SELF_MOD_CONFIDENCE_MIN}) eller performance={limbic.performance:.2f} (min 0.5)."
				),
				"risk_level": "medium",
				"requires": ["higher_confidence", "human_review"],
			}

		return {
			"permitted": True,
			"reason": "Lågrisk-operation: tillåten.",
			"risk_level": "low",
			"requires": [],
		}
