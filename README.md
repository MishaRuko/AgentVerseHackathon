# AgentVerseHackathon — Social Trend Analyser

This repository provides a lightweight pipeline for collecting, clustering and analysing social / news signals and producing persona-driven stakeholder outputs.

High-level pieces you will interact with:

- backend: Python FastAPI service that runs the orchestration and exposes a single query endpoint.
- multi-agent orchestration: `multi_agent.py` contains the core pipeline (source selection → scraping → clustering → graph RAG → persona planning/delivery).
- frontend: a minimal Vue 3 app (in `frontend/`) that visualises graphs and can call the backend API.

This README documents how to run and develop with the current code. The `protalab/` folder has been intentionally omitted here.

## Quick summary of important files

- `multi_agent.py` — central orchestration. Builds search queries, scrapes sources via `backend/scrapers`, clusters ideas with `backend/clustering.py`, builds a cluster graph via `backend/graph_builder.py`, and performs RAG lookups with `backend/graph_rag.py`. Uses Strands/OpenAI agents for LLM steps and persona generation.
- `backend/main.py` — FastAPI app exposing POST /ask which accepts a JSON body `{ "query": "..." }` and returns `{ "answer": "..." }`.
- `backend/graph_rag.py` — small RAG helper using FAISS + SentenceTransformers to retrieve contexts from an in-memory KB.
- `backend/clustering.py` — HDBSCAN clustering + LLM summarization of clusters.
- `backend/graph_builder.py` — builds graph structure and uses an LLM to create human-readable explanations for cluster groups.
- `backend/llm.py` — LLM wrapper used by some modules (loads config from environment).
- `backend/requirements.txt` — Python packages needed to run the backend.
- `frontend/` — Vue 3 + Vite frontend project; see `frontend/package.json` for commands and deps.
- `personas/` — persona prompts and helpers (marketing and finance personas used by the orchestrator).

## Environment variables

Create a `.env` file in the `backend` directory (or set these in your shell). Set the following:

```
GOOGLE_API_KEY = XXX
GOOGLE_CSE_ID = XXX
OPENAI_API_KEY = XXX
X_BEARER_TOKEN = XXX
```

## Backend — install and run

1. Create a virtual environment and install dependencies:

```cmd
cd backend
pip install -r requirements.txt
```

2. From the repository root you can run the API with uvicorn (recommended during development):

```cmd
cd backend
python3 main.py
```

3. The main API endpoint is:

- POST /ask — Body: `{ "query": "What's happening with product X" }` → Response: `{ "answer": "..." }`.

Notes and behavior:

- The backend keeps an in-memory `knowledge_base` while running; repeated /ask requests may cause the orchestrator to scrape and enrich the KB.
- The orchestrator (`multi_agent.py`) uses Strands agents and the persona tooling in `personas/` to route and generate persona-specific outputs.

## Frontend — install and run

The frontend is a standard Vite + Vue 3 project.

```cmd
cd frontend
npm install
npm run dev
```

Open the dev server URL printed by Vite (usually http://localhost:5173). The frontend components use `vis-network` / `vis-data` to render graphs and call the backend `/ask` endpoint for analysis.

The frontend now displays the persona of the agent responding to the query, with different colors for each persona.

## Development notes & how the pipeline works

- Request flow (simplified):
  1. Client calls `/ask` with a user query.

2.  `multi_agent.py` routes the query to a persona (marketing or finance) using a small supervisor agent.
3.  The system tries a RAG lookup against the in-memory KB (`backend/graph_rag.py`).
4.  If the KB is insufficient, the persona plan may instruct the orchestrator to generate search queries, scrape sources (via `backend/scrapers`), cluster ideas (`backend/clustering.py`), build/merge cluster graphs (`backend/graph_builder.py`) and add new embeddings to the KB.
5.  A final RAG + persona delivery step produces the natural-language answer returned by `/ask`.
6.  The frontend parses the persona from the response and displays it with a unique color.

- Persistence: At present the KB is in-memory only (a Python dict keyed by embedding tuples). For production use you should persist the KB and reuse FAISS indexes instead of rebuilding them on each call.

- LLM calls: The code uses Strands/OpenAI agents (`strands` library). Ensure `OPENAI_API_KEY` is set and that you have the required Strands extras installed (see `backend/requirements.txt`).

