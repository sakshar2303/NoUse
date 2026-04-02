"""
Global Workspace — Hopfield WTA med lateral inhibition
======================================================
Implementerar Global Workspace Theory (Baars 1988):

  1. Moduler tävlar med salience-värden
  2. Lateral inhibition: moduler hämmar varandra
  3. Hopfield-steget: konvergerar mot en attraktör (WTA)
  4. Softmax-selektion med β = acetylcholin (limbic state)
  5. Vinnaren "broadcastas" — väljs ut av medvetandets spotlight

Portat och anpassat från Ai_ideas/src/workspace/global_workspace.py
till b76's LimbicState och asynkrona arkitektur.

   β hög (fokuserat ACh) → vinnaren dominerar klart
   β låg (brett ACh)     → fler moduler konkurrerar
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field as dc_field
from typing import Any

from nouse.limbic.signals import LimbicState

log = logging.getLogger("nouse.workspace")

# Lateral inhibition vikt — uniform (alla moduler hämmar varandra lika)
_W_INHIBIT = 0.3

# Hopfield time-step
_DT = 0.1

# Antal Hopfield-steg innan convergence
_HOPFIELD_STEPS = 8


@dataclass
class WorkspaceProposal:
    """En moduls förslag till Global Workspace."""
    module: str          # modulnamn, t.ex. "tda_bisociation", "memory_retrieval"
    content: Any         # payload — fri form
    salience: float      # [0.0, 1.0] — hur viktigt är förslaget?
    domain: str = ""     # kunskapsdomän


@dataclass
class WorkspaceResult:
    """Resultatet av ett WTA-steg."""
    winner: WorkspaceProposal | None
    all_proposals: list[WorkspaceProposal]
    hopfield_states: dict[str, float]   # x_i per modul
    broadcast_content: Any              # vad som "broadcastas"
    beta: float                         # β som användes


class GlobalWorkspace:
    """
    WTA-konkurrens mellan kognitiva moduler.

    Stateful: Hopfield-tillståndet x_i per modul persisteras
    mellan competition_step()-anrop, vilket ger minnesinertia —
    moduler som vann senast har ett litet försprång.
    """

    def __init__(self) -> None:
        # Hopfield-tillstånd per modul
        self._x: dict[str, float] = {}

    def reset(self) -> None:
        """Återställ Hopfield-tillståndet (ny session)."""
        self._x.clear()

    def _hopfield_step(
        self,
        proposals: list[WorkspaceProposal],
        steps: int = _HOPFIELD_STEPS,
    ) -> list[WorkspaceProposal]:
        """
        dx_i/dt = -x_i + tanh(salience_i - Σ_{j≠i} w_ij * x_j)

        Lateral inhibition + Hopfield-avveckling:
        konvergerar mot attraktör där en modul dominerar.
        """
        # Initiera tillstånd för nya moduler
        for p in proposals:
            if p.module not in self._x:
                self._x[p.module] = 0.0

        for _ in range(steps):
            new_x: dict[str, float] = {}
            for p in proposals:
                i = p.module
                inhibition = sum(
                    _W_INHIBIT * self._x.get(p2.module, 0.0)
                    for p2 in proposals
                    if p2.module != i
                )
                net_input = p.salience - inhibition
                dx = -self._x[i] + math.tanh(net_input)
                new_x[i] = self._x[i] + dx * _DT

            self._x.update(new_x)

        return [
            WorkspaceProposal(
                module=p.module,
                content=p.content,
                salience=max(0.0, round(self._x.get(p.module, 0.0), 4)),
                domain=p.domain,
            )
            for p in proposals
        ]

    def _softmax_wta(
        self,
        proposals: list[WorkspaceProposal],
        beta: float,
    ) -> WorkspaceProposal | None:
        """Softmax WTA på Hopfield-justerade salience-värden."""
        if not proposals:
            return None

        beta = max(0.1, beta)
        scores = [math.exp(beta * p.salience) for p in proposals]
        total = sum(scores)
        if total <= 0:
            return proposals[0]

        # Deterministiskt: välj max (inte sampling)
        max_idx = max(range(len(proposals)), key=lambda i: scores[i])
        return proposals[max_idx]

    async def competition_step(
        self,
        proposals: list[WorkspaceProposal],
        limbic: LimbicState,
    ) -> WorkspaceResult:
        """
        Kör ett WTA-steg.

        Args:
            proposals: Modulernas förslag med salience-värden.
            limbic: Aktuellt limbiskt tillstånd (ger β).

        Returns:
            WorkspaceResult med vinnare och hopfield-tillstånd.
        """
        if not proposals:
            return WorkspaceResult(
                winner=None,
                all_proposals=[],
                hopfield_states={},
                broadcast_content=None,
                beta=limbic.wta_beta,
            )

        beta = limbic.wta_beta
        log.debug(f"Workspace WTA: {len(proposals)} moduler, β={beta:.2f}")

        # Hopfield-konvergens
        converged = self._hopfield_step(proposals)

        # WTA via softmax
        winner = self._softmax_wta(converged, beta)

        log.info(
            f"Workspace vinnare: {winner.module if winner else 'ingen'} "
            f"(salience={winner.salience:.3f})" if winner else "Workspace: ingen vinnare"
        )

        return WorkspaceResult(
            winner=winner,
            all_proposals=converged,
            hopfield_states=dict(self._x),
            broadcast_content=winner.content if winner else None,
            beta=beta,
        )
