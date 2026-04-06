"""Basic NoUse query example.

Shows how to attach to NoUse and query the knowledge graph.
"""
import nouse

brain = nouse.attach()
result = brain.query("What is epistemic grounding?")

print("=== Context Block ===")
print(result.context_block())
print(f"\nConfidence: {result.confidence:.2f}")
print(f"Has knowledge: {result.has_knowledge}")
print(f"Domains: {result.domains}")
