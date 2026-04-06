"""Using NoUse with Ollama (local models).

Run any local model with epistemic grounding from NoUse.
Requires: ollama running locally with a model pulled.
"""
import nouse
import ollama

brain = nouse.attach()

question = "What is the difference between association and bisociation?"
memory = brain.query(question)

response = ollama.chat(
    model="llama3.1:8b",
    messages=[
        {"role": "system", "content": f"You have access to verified knowledge.\n\n{memory.context_block()}"},
        {"role": "user", "content": question},
    ],
)

print(response["message"]["content"])
print(f"\n--- Grounded with {len(memory.axioms)} axioms (confidence: {memory.confidence:.2f}) ---")
