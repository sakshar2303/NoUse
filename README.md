<p align="center">
  <img src="IMG/Nouse.png" alt="NoUse Logo" width="280"/>
</p>

<h1 align="center">NoUse</h1>

<p align="center">
  <strong>Persistent Cognitive Memory for AI Systems</strong>
</p>

<p align="center">
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="https://www.rust-lang.org/"><img src="https://img.shields.io/badge/rust-1.70+-orange.svg" alt="Rust 1.70+"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/License-MIT-yellow.svg" alt="License: MIT"></a>
</p>

<p align="center">
  <em>"AI systems cannot speak with continuity because they have no persistent memory of their own voice.<br/>
  Every AI was built on NoUse. Now there's a framework for it."</em><br/>
  — Björn Wikström, Base76 Research Lab
</p>

---

## The Name

**NoUse** (νοῦς, Gk. "mind/intellect") — four layers of meaning in five letters:

1. **Nous** (νοῦς) — the Greek substrate of pure mind
2. **NoUs** — No + Us: shared cognition, built together
3. **No Use** — ironic: the most critical missing piece in AI, named after what everyone treated it as
4. **nouse** — Northern English dialect: common sense, practical intelligence

> *Precedent: Rust was named after a fungus. Python after a comedy sketch. The best tech names have layers that reward the curious.*

---

## The Problem

Current LLMs are **ephemeral**:
- ❌ No memory between sessions
- ❌ No knowledge accumulation over time
- ❌ No sense of "self" or continuity
- ❌ Every interaction starts from zero

```
Without NoUse:   "I don't remember what we discussed yesterday."
With NoUse:      "Yesterday you mentioned wanting to explore residual
                  stream analysis. I've found 3 relevant papers and
                  drafted a hypothesis. Should we review?"
```

**NoUse solves this** by providing a **Cognitive Kernel** — persistent, queryable, semantic memory that lives alongside any LLM.

---

## What is NoUse?

NoUse transforms any LLM from a **stateless prediction engine** into a **cognitive agent with persistent memory**. It is a model-agnostic cognitive substrate — a living topological graph with evidence-gated memory, neuromodulation, metacognition, and residual stream signaling.

It is **not** a vector database. It is **not** a RAG pipeline.

### Core Principles

1. **Topological plasticity** over static parameter updates
2. **Explicit memory tiers** — working → episodic → semantic → procedural
3. **Evidence-gated growth** — every structural write requires provenance
4. **Metacognition** — explicit unknowns, gap-driven development
5. **Full observability** — belief provenance traceable end-to-end

### Theory: Field-Node-Cockpit (FNC)

NoUse implements **FNC** — a consciousness-inspired architecture:

| Component | Layer | Role |
|-----------|-------|------|
| **Field** | b76 | Persistent knowledge surface — graph, memory, embeddings |
| **Node** | LLM | Stateless processing unit (Claude, GPT, etc.) — thought generator |
| **Cockpit** | Orchestrator | Dynamic attention control — goals, priorities, neuromodulation |

**Principle:** Cognition = Field dynamics + Node reasoning + Cockpit governance.

---

## Architecture

```
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Claude     │  │   Clawbot    │  │  Any LLM     │
│   Code       │  │   (robot)    │  │   runtime     │
└──────┬───────┘  └──────┬───────┘  └──────┬───────┘
       │                 │                 │
       │           MCP / REST Protocol     │
       └─────────────────┼─────────────────┘
                         ▼
       ┌─────────────────────────────────────┐
       │        NoUse Cognitive Kernel        │
       │                                     │
       │  ┌───────────┐  ┌───────────────┐  │
       │  │  Episodic  │  │   Semantic    │  │
       │  │  Memory    │  │   Graph       │  │
       │  │  (3276+)   │  │  (11000+)     │  │
       │  └───────────┘  └───────────────┘  │
       │                                     │
       │  ┌───────────┐  ┌───────────────┐  │
       │  │ Residual   │  │ Neuro-        │  │
       │  │ Streams    │  │ modulation    │  │
       │  │ (w, r, u)  │  │ (DA, NA, ACh) │  │
       │  └───────────┘  └───────────────┘  │
       │                                     │
       │  ┌───────────┐  ┌───────────────┐  │
       │  │ Self-Model │  │ Metacognition │  │
       │  │            │  │ & Gap Map     │  │
       │  └───────────┘  └───────────────┘  │
       │                                     │
       │  ┌─────────────────────────────┐   │
       │  │  Zulu DB (Rust core)        │   │
       │  │  High-performance storage   │   │
       │  └─────────────────────────────┘   │
       └─────────────────────────────────────┘
                         │
       ┌─────────────────┼─────────────────┐
       │                 │                 │
       ▼                 ▼                 ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│  brain-db    │ │     b76      │ │  tda_engine  │
│  FNC Sub-    │ │  Knowledge   │ │  (Rust+PyO3) │
│  strate      │ │  Graph+CLI   │ │  Topological │
│  (Python)    │ │  35+ cmds    │ │  Analysis    │
└──────────────┘ └──────────────┘ └──────────────┘
```

**Boundary rule:** NoUse owns truth state. Clients are read-mostly — writes go through evidence-gated MCP calls.

---

## Quick Start

### Prerequisites

- Python 3.11+
- Rust 1.70+
- Ollama (recommended)

### Installation

```bash
# Clone the repository
git clone https://github.com/base76-research-lab/NoUse.git
cd NoUse

# Install Python dependencies
pip install nouse

# Build Rust components (tda_engine)
cd crates/tda_engine && cargo build --release && cd ../..

# Initialize NoUse
brain-runtime \
  --state-path ~/.local/share/nouse/brain_image.json \
  --telemetry-path ~/.local/share/nouse/brain_live.jsonl \
  --tick-seconds 1.0 \
  --autosave-every-cycles 30
```

### Start MCP Server (for AI tool integration)

```bash
brain-mcp --tick-seconds 1.0
```

### Start REST API

```bash
brain-server  # Flask on port 7676
```

### Live Visualization Dashboard

```bash
python scripts/brain_live_dashboard.py \
  --host 127.0.0.1 --port 7688 \
  --telemetry-path ~/.local/share/nouse/brain_live.jsonl
```

### Run an Autonomy Mission

```bash
brain-mission \
  --mission ops/missions/first_real_ai_v1.json \
  --report-path ~/.local/share/nouse/reports/mission_report.json
```

### b76 Knowledge Graph CLI

```bash
# Start daemon with web UI
b76 daemon web --port 8765

# Query brain state
b76 brain state
b76 brain gap
b76 brain metrics --last-n 100

# Interactive session
b76 start me          # Chat mode
b76 start research    # Research cockpit
b76 start autonomy    # Autonomous mode

# Ingest knowledge
b76 ingest --url "https://example.com/paper.pdf"
b76 learn-from /path/to/source

# Semantic search
b76 embed-search "residual stream analysis"
```

---

## Usage

### Python API

```python
from brain_db_core.brain import Brain, FieldEvent

# Create or load brain
brain = Brain(seed=76031)

# Add concept node
brain.add_node(
    node_id="mechanistic_interpretability",
    label="Mechanistic Interpretability",
    node_type="concept",
    uncertainty=0.15,
    evidence_score=0.85
)

# Add relation with residual stream channels
brain.upsert_edge(
    edge_id="edge_0001",
    src="mechanistic_interpretability",
    rel_type="enables",
    tgt="sae_analysis",
    w=0.92,      # strong connection
    r=0.15,      # weak residual bypass
    u=0.10,      # high confidence
    evidence_score=0.88
)

# Step the brain (advance one cycle)
brain.step(events=[FieldEvent(event_type="learn", payload={...})])

# Query state
state = brain.get_state()     # cycle, nodes, edges
gap_map = brain.gap_map()     # weak nodes, weak edges, priorities
live = brain.live_view(12, 16)  # active subgraph

# Crystallize stable edges
brain.crystallize()

# Save brain image
brain.save("~/.local/share/nouse/brain_image.json")
```

### REST API

```bash
# Brain state
curl http://localhost:7676/state

# Metacognitive gap map
curl http://localhost:7676/gap_map

# Recent metrics
curl "http://localhost:7676/metrics?last_n=50"

# Live activation view
curl "http://localhost:7676/live?limit_nodes=12&limit_edges=16"

# Advance brain & apply events
curl -X POST http://localhost:7676/step \
  -H "Content-Type: application/json" \
  -d '[{"event_type": "learn", "payload": {"concept": "foo"}}]'

# Save to disk
curl -X POST http://localhost:7676/save
```

### With Claude Code (MCP)

```json
{
  "mcpServers": {
    "nouse": {
      "command": "brain-mcp",
      "args": ["--tick-seconds", "1.0"],
      "env": {
        "BRAIN_DB_STATE_PATH": "~/.local/share/nouse/brain_image.json",
        "BRAIN_DB_AUTOSAVE_CYCLES": "30"
      }
    }
  }
}
```

MCP tools exposed:

| Tool | Description |
|------|-------------|
| `brain_get_state` | Cycle count, node/edge counts, crystallized edges |
| `brain_get_gap_map` | Weak nodes, weak edges, priorities |
| `brain_get_metrics` | Scalar metrics per cycle (last N) |
| `brain_get_live_view` | Active subgraph (top nodes + edges by activation) |
| `brain_get_live_snapshot` | Recent JSONL telemetry frames |
| `brain_step` | Apply events, advance one cycle |
| `brain_save` | Persist brain image to disk |

---

## Core Data Structures

### Residual Streams

The core innovation: per-edge signaling channels that enable epistemic precision.

```python
@dataclass
class ResidualEdge:
    edge_id: str
    src: str
    rel_type: str       # "causes", "modulates", "predicts", ...
    tgt: str
    w: float = 0.02     # weight [0, 1] — base connection strength
    r: float = 0.0      # residual [-2, 2] — bypassing signal
    u: float = 0.80     # uncertainty [0, 1] — confidence deficit

    @property
    def path_signal(self) -> float:
        return self.w + 0.45*self.r - 0.25*self.u
```

| Channel | Name | Persistence | Purpose |
|---------|------|-------------|---------|
| **w** | Structural weight | Persistent | Canonical connection strength |
| **r** | Residual signal | Ephemeral | Live activation / temporary signal |
| **u** | Uncertainty | Gates consolidation | Epistemic confidence — high u blocks promotion |

**Research findings:** Residual streams achieved **100% bridge detection** vs 0.75% for static edges — a **133x** improvement. Robust under decoy sweep (5–30 decoys): residual sustains 99%+ success vs static < 0.02%.

### Neuromodulation

```python
@dataclass
class NeuromodulatorState:
    dopamine: float = 0.5       # reward / novelty signal
    noradrenaline: float = 0.5  # alertness / urgency
    acetylcholine: float = 0.5  # focus / precision

    @property
    def arousal(self) -> float:   # 0.65·NA + 0.35·DA
    def focus(self) -> float:     # 0.70·ACh + 0.30·NA
    def risk(self) -> float:      # 0.55·(1-ACh) + 0.45·NA
```

### Node State Space

```python
@dataclass
class NodeStateSpace:
    node_id: str
    node_type: str = "concept"  # concept | episode | claim | region | task
    label: str = ""
    states: dict[str, float]    # prior amplitudes (softmax-normalized)
    uncertainty: float = 0.80
    evidence_score: float = 0.0
    goal_weight: float = 0.0
```

---

## Key Differentiators

| Feature | NoUse | Vector DB (Pinecone, etc.) | LLM Memory (MemGPT, etc.) |
|---------|-------|---------------------------|---------------------------|
| Topological plasticity | ✅ Graph grows, prunes, consolidates | ❌ Static embeddings | ❌ Append-only context |
| Evidence gating | ✅ Every write requires provenance | ❌ No provenance | ❌ No provenance |
| Memory tiers | ✅ working → episodic → semantic → procedural | ❌ Flat | ⚠️ Partial |
| Residual streams (w/r/u) | ✅ Per-edge epistemic channels | ❌ No | ❌ No |
| Neuromodulation | ✅ DA/NA/ACh → arousal, focus, risk | ❌ No | ❌ No |
| Metacognition | ✅ Explicit unknowns, gap map | ❌ No | ❌ No |
| Self-model | ✅ Capabilities, goals, trajectory | ❌ No | ❌ No |
| Model-agnostic | ✅ Any LLM via MCP | ⚠️ Embedding-dependent | ❌ LLM-specific |
| Rust performance layer | ✅ Zulu DB + tda_engine | ❌ No | ❌ No |
| Full observability | ✅ Belief provenance, live telemetry | ❌ No | ❌ No |

---

## Performance

| Metric | Value |
|--------|-------|
| Memory recall latency | < 10ms |
| Graph query latency | < 50ms |
| Episodic memories | 3,276+ |
| Semantic concepts | 11,000+ |
| Embedding model | qwen3-embedding:4b (2560D) |
| Residual vs static edges | 133x improvement (bridge detection) |
| Decoy robustness | 99%+ under 30 decoys |

---

## CLI Commands

### brain-db-core

| Command | Description |
|---------|-------------|
| `brain-runtime` | Start the Brain Kernel runtime loop |
| `brain-mcp` | Start MCP stdio server for AI tool integration |
| `brain-server` | Start REST API server (Flask, port 7676) |
| `brain-mission` | Execute a bounded autonomy mission |

### b76

| Command | Description |
|---------|-------------|
| `b76 daemon web` | Start daemon with web UI (port 8765) |
| `b76 start me\|research\|autonomy` | Entry modes |
| `b76 brain state\|gap\|metrics\|step\|save` | Direct brain-db-core queries |
| `b76 ingest --url <url>` | Import URL, PDF, YouTube, file |
| `b76 embed-search <query>` | Semantic search against index |
| `b76 mcp` | Expose b76 as MCP server |
| `b76 doctor` | Health check & repair |

---

## Documentation

| Document | Description |
|----------|-------------|
| `docs/ARCHITECTURE_V1.md` | System architecture (3-layer: Zulu DB, Kuzu, Python) |
| `docs/BRAIN_DB_SCHEMA_V1.md` | Data schema — node classes, edge types, memory tiers |
| `docs/BRAIN_IMAGE_FORMAT_V1.md` | Persistence format (deterministic JSON) |
| `docs/MCP_API_CONTRACT_V1.md` | MCP protocol — read, write, and research tools |
| `docs/MISSION_CONTRACT_V1.md` | Autonomy mission format (KPI-gated checkpoints) |
| `docs/LIVE_VISUALIZATION_V1.md` | Real-time telemetry dashboard spec |
| `docs/DATA_BOOTSTRAP_PLAN_V1.md` | Biological seed data (Allen Brain Cell Atlas) |
| `docs/RESIDUAL_STREAMS_SIMULATION_V1.md` | Research: residual stream hypothesis |
| `docs/RESIDUAL_STREAMS_DECOY_SWEEP_V2.md` | Research: epistemic filtering under noise |
| `docs/ROADMAP_V1_6W.md` | 6-week roadmap |
| `ops/DECISIONS.md` | Architecture Decision Records |

---

## Project Structure

```
nouse/
├── src/
│   ├── brain_db_core/          # Core cognitive substrate (Python)
│   │   ├── brain.py            # Brain Kernel — NodeStateSpace, ResidualEdge, Brain
│   │   ├── schema.py           # Graph schema & node types
│   │   ├── runtime.py          # Tick-based runtime loop
│   │   ├── mission_runner.py   # Bounded autonomy missions
│   │   ├── models.py           # Data models
│   │   └── db.py               # Persistence layer
│   ├── brain_db_api/           # Interface layer
│   │   ├── mcp_server.py       # MCP stdio server (FastMCP, 7 tools)
│   │   └── rest_api.py         # REST API (Flask, 7 endpoints)
│   └── b76/                    # Knowledge graph + CLI
│       ├── cli/                # Typer app (35+ commands)
│       ├── field/              # Knowledge graph (Kuzu DB)
│       ├── memory/             # Episodic memory tier logic
│       ├── embeddings/         # qwen3-embedding:4b integration
│       ├── tda/                # Topological analysis (Rust bridge)
│       ├── daemon/             # Background brain loop
│       ├── mcp_gateway/        # MCP server for b76
│       ├── limbic/             # Neuromodulation simulation
│       ├── self_layer/         # Self-modeling
│       ├── metacognition/      # Gap detection
│       ├── web/                # Web dashboard
│       └── ...                 # 20+ modules
├── crates/
│   └── tda_engine/             # Rust + PyO3
│       ├── Cargo.toml          # pyo3, rayon — opt-level=3, LTO
│       └── src/lib.rs          # Betti numbers, persistent homology (Vietoris-Rips)
├── scripts/
│   ├── brain_live_dashboard.py
│   ├── bootstrap_abc_atlas.py
│   ├── simulate_residual_streams.py
│   └── sweep_residual_streams_decoys.py
├── ops/
│   ├── missions/               # Autonomy mission contracts
│   ├── systemd/                # Service unit files
│   └── vscode/                 # MCP client config template
├── data/
│   └── bootstrap/              # Biological seed data & simulation results
├── docs/                       # Architecture, schema, research
└── tests/
```

---

## Research

NoUse originated from research at **Base76 Research Lab** into persistent cognitive substrates for model-agnostic AI systems.

Key research threads:
- **The Larynx Problem** — AI cannot speak with continuity without persistent memory
- **Residual stream hypothesis** — per-edge (w/r/u) channels for epistemic precision
- **Topological plasticity** — evidence-gated graph growth and consolidation
- **Biological bootstrapping** — seeding from neuroscience datasets (Allen Brain Cell Atlas)
- **Bounded autonomy** — mission contracts with KPI-gated checkpoints
- **Topological data analysis** — Betti numbers and persistent homology for bisociation detection

📧 **Contact:** nouse@base76research.com
🌐 **Web:** [nouse.base76research.com](https://nouse.base76research.com)
🐙 **Source:** [github.com/base76-research-lab/NoUse](https://github.com/base76-research-lab/NoUse)

---

<p align="center">
  <strong>Built on NoUse.</strong><br/>
  <em>Finally, AI with some nouse.</em>
</p>
