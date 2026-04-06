"""Using NoUse with OpenAI.

NoUse provides the epistemic memory; OpenAI provides the language model.
"""
import nouse
from openai import OpenAI

brain = nouse.attach()
client = OpenAI()

question = "How does Hebbian plasticity work in knowledge graphs?"
memory = brain.query(question)

response = client.chat.completions.create(
    model="gpt-4o-mini",
    messages=[
        {"role": "system", "content": f"You have access to a verified knowledge base.\n\n{memory.context_block()}"},
        {"role": "user", "content": question},
    ],
)

print(response.choices[0].message.content)
print(f"\n--- Grounded with {len(memory.axioms)} axioms (confidence: {memory.confidence:.2f}) ---")
