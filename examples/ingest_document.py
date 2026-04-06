"""Ingest a document into the NoUse knowledge graph.

Shows how to add new knowledge from files or text.
Requires the NoUse daemon to be running: nouse daemon start
"""
import httpx

NOUSE_API = "http://127.0.0.1:8765/api/ingest"

text = """
Quantum tunneling in enzyme catalysis allows protons and hydride ions
to traverse energy barriers that classical mechanics would forbid.
This phenomenon has been observed in alcohol dehydrogenase and
soybean lipoxygenase, where kinetic isotope effects exceed
semiclassical predictions.
"""

response = httpx.post(
    NOUSE_API,
    json={"text": text, "source": "quantum_biology_notes"},
    timeout=90.0,
)

data = response.json()
print(f"Added {data['added']} relations to the knowledge graph")
print(f"Source: {data['source']}")
for rel in data.get("relations", []):
    print(f"  {rel['src']} --[{rel.get('rel', '?')}]--> {rel['tgt']}")
