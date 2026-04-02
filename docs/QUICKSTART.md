# NoUse — 5-minuters guide

> **NoUse** (νοῦς, "nous") — den kognitiva substrat-frameworken som ger din LLM en plastisk hjärna.

## Installation

```bash
pip install nouse
```

## Grundkoncept

NoUse separerar **hjärnan** (persistent kognitiv substrat) från **larynxen** (LLM-runtime). En hjärna — många klienter.

```
Claude / GPT / din agent
         ↓
    nouse.Kernel()           ← Du är här
         ↓
  Residual Streams (w, r, u)
  Minnesnivåer: working → episodic → semantic → procedural
  Evidens-gatad plasticitet
```

## Snabbstart: 5 minuter

### 1. Skapa en hjärna

```python
import nouse

k = nouse.Kernel()
```

### 2. Lägg till noder (hjärnregioner / koncept)

```python
k.add_node(
    "hippocampus",
    node_type="region",
    label="Hippocampus",
    states={"episodic_encoder": 0.7, "spatial_mapper": 0.3},
    uncertainty=0.5,
    evidence_score=0.0,
    goal_weight=0.0,
    attrs={"hemisphere": "bilateral"},
)

k.add_node(
    "prefrontal_cortex",
    node_type="region",
    label="Prefrontal Cortex",
    states={"executive": 0.8, "working_memory": 0.2},
    uncertainty=0.3,
    evidence_score=0.4,
    goal_weight=0.6,
    attrs={},
)
```

### 3. Skapa kanter med Residual Streams

Varje kant har tre kanaler:
- **w** — strukturell synaptisk styrka [0..1], persistent
- **r** — residualsignal [-2..2], ephemeral per cykel
- **u** — osäkerhet [0..1], blockerar konsolidering om hög

```python
k.upsert_edge(
    "hippo_to_pfc",
    src="hippocampus",
    rel_type="consolidated_into",
    tgt="prefrontal_cortex",
    w=0.4,         # Medelstark synaptisk koppling
    r=0.0,         # Ingen aktiv signal just nu
    u=0.6,         # Ganska osäker
    provenance="episodic_learning",
)

edge = k.edges["hippo_to_pfc"]
print(f"path_signal = {edge.path_signal:.3f}")
# → path_signal = w + 0.45*r - 0.25*u = 0.4 + 0 - 0.15 = 0.250
```

### 4. Kör en kognitiv cykel

```python
from nouse import FieldEvent

event = FieldEvent(
    edge_id="hippo_to_pfc",
    src="hippocampus",
    rel_type="consolidated_into",
    tgt="prefrontal_cortex",
    w_delta=0.05,       # Stärk kopplingen
    r_delta=0.8,        # Aktivera residualsignalen
    u_delta=-0.1,       # Minska osäkerheten (nytt bevis)
    evidence_score=0.7,
    provenance="experiment:recall_test",
)

k.step(events=[event])

edge = k.edges["hippo_to_pfc"]
print(f"w={edge.w:.2f}, r={edge.r:.3f}, u={edge.u:.2f}")
print(f"path_signal = {edge.path_signal:.3f}")
```

### 5. Kristallisera starka kanter

Kanter med `w > 0.55` och `u < 0.35` blir permanenta minnesspår:

```python
# Kör flera cykler med bevis...
for _ in range(20):
    k.step(events=[FieldEvent(
        edge_id="hippo_to_pfc",
        src="hippocampus", rel_type="consolidated_into", tgt="prefrontal_cortex",
        w_delta=0.03, u_delta=-0.05, evidence_score=0.85,
        provenance="repeated_activation",
    )])

crystallized = k.crystallize()
print(f"Kristalliserade kanter: {[e.edge_id for e in crystallized]}")
```

### 6. Spara och ladda hjärnan

```python
k.save("~/.local/share/nouse/brain.json")

# Ladda senare:
k2 = nouse.Kernel.load("~/.local/share/nouse/brain.json")
```

---

## Minnesnivåer

| Nivå | Karaktär | Nod-typ | Livslängd |
|------|----------|---------|-----------|
| **working** | Snabb decay, r-tung | Aktiva kanter | Cykler |
| **episodic** | Tidsstämplat | EpisodeNode | Timmar–dagar |
| **semantic** | Konsoliderat, evidens-viktat | ConceptNode | Veckor–månader |
| **procedural** | Handlingsmönster | TaskNode | Permanent |

```python
print(nouse.MEMORY_TIERS)
# ('working', 'episodic', 'semantic', 'procedural')
```

---

## CLI-kommandon

```bash
# Starta Brain Kernel daemon (persistent runtime)
nouse-brain --state-path ~/.local/share/nouse/brain.json --tick-seconds 1.0

# Starta MCP-server (för Claude, VS Code, etc.)
nouse-mcp --tick-seconds 1.0

# Starta REST API (skrivskyddad, för research)
nouse-server

# Kör ett autonomt mission-kontrakt
nouse-mission --mission ops/missions/first_real_ai_v1.json
```

## VS Code MCP-integration

```json
{
  "mcpServers": {
    "nouse": {
      "command": "nouse-mcp",
      "args": ["--tick-seconds", "1.0"],
      "env": {
        "BRAIN_DB_STATE_PATH": "~/.local/share/nouse/brain.json"
      }
    }
  }
}
```

---

## Varför inte en vanlig vektordatabas?

| Funktion | NoUse | Vector DB | LLM Memory |
|----------|-------|-----------|------------|
| Topologisk plasticitet | ✅ | ❌ | ❌ |
| Evidens-gatade skrivningar | ✅ | ❌ | ❌ |
| Minnesnivåer | ✅ | ❌ | ⚠️ |
| Residual streams (w/r/u) | ✅ | ❌ | ❌ |
| Modell-agnostisk | ✅ | ⚠️ | ❌ |
| Full observabilitet | ✅ | ❌ | ❌ |

Residual streams uppnår **100% bridge detection** mot 0.75% för statiska vikter i simulation.

---

*Dokumentation: se `docs/` för fullständig arkitektur, schema och API-kontrakt.*
