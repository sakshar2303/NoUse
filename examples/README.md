# NoUse Examples

Runnable examples showing how to use NoUse.

| Example | Description | Requirements |
|---------|-------------|-------------|
| [basic_query.py](basic_query.py) | Query the knowledge graph | `pip install nouse` |
| [with_openai.py](with_openai.py) | Use with OpenAI models | `pip install nouse openai` |
| [with_ollama.py](with_ollama.py) | Use with local Ollama models | `pip install nouse ollama` |
| [ingest_document.py](ingest_document.py) | Add knowledge from text | NoUse daemon running |

## Quick Start

```bash
pip install nouse
python basic_query.py
```

For daemon-dependent examples, start the daemon first:

```bash
nouse daemon start
```
