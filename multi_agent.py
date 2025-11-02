import json
import asyncio
import sys
import os
import re
from urllib.parse import quote_plus, urlparse
from dotenv import load_dotenv
import yaml
import requests

from strands import Agent, tool
from strands.models.openai import OpenAIModel

# ---------------------------------------------------------------------
# ENV / PATH SETUP
# ---------------------------------------------------------------------

load_dotenv()

# make sure backend modules can be imported
# (adjust this if your repo layout is different)
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# backend logic
from graph_rag import rag_query            # semantic retrieval over KB
import backend.scrapers.scraper_agent as WebScraper  # scrape_and_generate_ideas()

# clustering / graph builder logic
from clustering import cluster_and_summarize          # clusters raw ideas
from graph_builder import build_cluster_graph         # builds higher-level communities

# personas
# these come from personas/ (the new folder you created)
from personas import (
    build_marketing_persona_agent,
    make_marketing_persona_tool,
    build_finance_persona_agent,
    make_finance_persona_tool,
)

# ---------------------------------------------------------------------
# GLOBAL STATE
# ---------------------------------------------------------------------

# persistent knowledge base for this process.
# keys: tuple(float, float, ...)
# values: text summary / theme / explanation for that embedding
knowledge_base = {}

# ---------------------------------------------------------------------
# OPENAI MODEL
# ---------------------------------------------------------------------

openai_model = OpenAIModel(
    model_id="gpt-4o-mini",  # shared across all agents
)

# ---------------------------------------------------------------------
# LOAD PROMPTS
# ---------------------------------------------------------------------

with open("agent_prompts.yaml", "r") as f:
    _prompt_yaml = yaml.safe_load(f)
    SOURCE_SELECTOR_PROMPT = _prompt_yaml["source_selector"]
    SCRAPER_PROMPT = _prompt_yaml["scraper"]
    GRAPH_RAG_PROMPT = _prompt_yaml["graph_rag"]

with open("marketing_strategist.yaml", "r") as f:
    _orchestrator_yaml = yaml.safe_load(f)
    BASE_ORCHESTRATOR_PROMPT = _orchestrator_yaml["orchestrator"]
    # we won't use it verbatim anymore, but we keep it in case you want
    # tone/style to influence SUPERVISOR_PROMPT

# ---------------------------------------------------------------------
# HELPER: classify source type for scraper
# ---------------------------------------------------------------------

def infer_source_type(url: str, title: str = "", snippet: str = "") -> str:
    """
    Map a URL to a scraping mode expected by scrape_source():
    "reddit_post", "reddit_sub", "twitter", "news", "general".
    """

    if not url:
        return "general"

    parsed = urlparse(url)
    netloc = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    title = (title or "").lower()
    snippet = (snippet or "").lower()

    # Reddit
    if "reddit.com" in netloc or "redd.it" in netloc:
        if "/comments/" in path or re.search(r"/comments/[a-z0-9]+", path):
            return "reddit_post"
        if re.search(r"^/r/[^/]+/?", path) or re.search(r"^/r/[^/]+/(hot|new|top)", path):
            return "reddit_sub"
        return "reddit_sub"

    # Twitter / X
    if "twitter.com" in netloc or "x.com" in netloc:
        return "twitter"

    # Wikipedia etc → news/article-like
    if "wikipedia.org" in netloc:
        return "news"

    # generic "news" heuristics
    news_indicators = ["news", "article", "/articles/", "/202", "/story", "press", "opinion"]
    if any(ind in path for ind in news_indicators) or any(ind in title or ind in snippet for ind in news_indicators):
        return "news"

    known_news_domains = {
        "nytimes.com",
        "theguardian.com",
        "bbc.co.uk",
        "cnn.com",
        "washingtonpost.com"
    }
    if any(d in netloc for d in known_news_domains):
        return "news"

    return "general"

# ---------------------------------------------------------------------
# GOOGLE SEARCH HELPER
# ---------------------------------------------------------------------

def google_search(query: str, num_results: int = 3) -> list:
    """
    Google Custom Search API helper. Falls back to mock if creds missing.
    """

    api_key = os.environ.get("GOOGLE_API_KEY")
    cse_id = os.environ.get("GOOGLE_CSE_ID")

    if not api_key or not cse_id:
        # fallback mock mode
        return [
            {
                "title": f"Result 1 for '{query}'",
                "url": f"https://example.com/result1?q={quote_plus(query)}",
                "snippet": f"Mock search result about {query}...",
                "type": "general"
            },
            {
                "title": f"Result 2 for '{query}'",
                "url": f"https://example.com/result2?q={quote_plus(query)}",
                "snippet": f"Additional information about {query}...",
                "type": "general"
            },
            {
                "title": f"Result 3 for '{query}'",
                "url": f"https://example.com/result3?q={quote_plus(query)}",
                "snippet": f"More details about {query}...",
                "type": "general"
            }
        ][:num_results]

    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": api_key,
            "cx": cse_id,
            "q": query,
            "num": num_results
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("items", [])[:num_results]:
            title = item.get("title", "")
            link = item.get("link", "")
            snippet = item.get("snippet", "")
            results.append({
                "title": title,
                "url": link,
                "snippet": snippet,
                "type": infer_source_type(link, title, snippet),
            })
        return results

    except Exception:
        # fallback again if API fails
        return google_search(query, num_results)

# ---------------------------------------------------------------------
# SPECIALIST AGENTS
# ---------------------------------------------------------------------

_source_selector_agent_instance = Agent(
    model=openai_model,
    name="Source Selector",
    description="Generates targeted search queries for multiple source types.",
    system_prompt=SOURCE_SELECTOR_PROMPT,
    callback_handler=None,
)

_scraper_agent_instance = Agent(
    model=openai_model,
    name="Web Scraper",
    description="Extracts atomic ideas from raw sources.",
    system_prompt=SCRAPER_PROMPT,
    callback_handler=None,
)

_graph_rag_agent_instance = Agent(
    model=openai_model,
    name="Graph RAG Synthesizer",
    description="Synthesizes an answer from retrieved graph/cluster contexts.",
    system_prompt=GRAPH_RAG_PROMPT,
    callback_handler=None,
)

# personas: build persona agents from shared model
_marketing_persona_agent_instance = build_marketing_persona_agent(openai_model)
_investment_banking_persona_agent_instance = build_finance_persona_agent(openai_model)

# wrap them in tool functions Supervisor can call
marketing_persona_agent = make_marketing_persona_tool(_marketing_persona_agent_instance)
ib_persona_agent = make_finance_persona_tool(_investment_banking_persona_agent_instance)

# ---------------------------------------------------------------------
# TOOL WRAPPERS (non-persona)
# ---------------------------------------------------------------------

@tool(description="Generate 3 diverse Google queries, then gather top sources for each.")
def source_selector_agent(user_query: str) -> str:
    """
    1. Ask the Source Selector agent to generate EXACTLY 3 search queries as a JSON array.
    2. google_search each query (top 3 results).
    3. Return: { "sources": [ { "url": ..., "type": ...}, ... ] }
    """
    try:
        raw = _source_selector_agent_instance(user_query)
        # we expect a pure JSON array like ["query1", "query2", "query3"]
        queries = json.loads(str(raw).strip())
    except Exception:
        # fallback if the agent didn't give valid JSON
        queries = [
            user_query,
            f"{user_query} latest discussion",
            f"{user_query} controversy reddit",
        ]

    all_sources = []
    for q in queries[:3]:
        for r in google_search(q, num_results=3):
            all_sources.append({
                "url": r["url"],
                "type": r["type"],
            })

    return json.dumps({"sources": all_sources})


@tool(description="Scrape provided sources and extract atomic 'ideas' statements for clustering.")
async def scraper_agent(sources_json: str) -> str:
    """
    Input:
        sources_json: '{"sources":[{"url":"...","type":"reddit_post"}, ...]}'
    Output:
        {"ideas": ["idea1", "idea2", ...]}

    Uses backend.scrapers.scraper_agent.scrape_and_generate_ideas()
    to crawl each source and LLM-extract granular ideas.
    """
    try:
        payload = json.loads(sources_json)
        sources = payload.get("sources", [])
    except Exception:
        sources = []

    loop = asyncio.get_running_loop()
    ideas_list = await loop.run_in_executor(
        None,
        WebScraper.scrape_and_generate_ideas,
        sources
    )

    return json.dumps({"ideas": ideas_list})


@tool(description="Cluster ideas, build/expand the global knowledge graph, and update the shared knowledge base.")
def graph_builder_agent(ideas_json: str) -> str:
    """
    Input:
        ideas_json: '{"ideas":["...", "...", ...]}'

    Steps:
      1. cluster_and_summarize(ideas) → list of cluster dicts
      2. build_cluster_graph(clustered_data) →
         (embedding_to_explanation, group_to_explanation, sim_matrix)
      3. Merge embedding_to_explanation into global knowledge_base.

    Output:
        {
          "kb_size": <int>,
          "clusters_added": <int>,
          "status": "ok" | "no_ideas"
        }
    """
    global knowledge_base

    try:
        payload = json.loads(ideas_json)
        ideas = payload.get("ideas", [])
    except Exception:
        ideas = []

    if not ideas:
        return json.dumps({
            "kb_size": len(knowledge_base),
            "clusters_added": 0,
            "status": "no_ideas",
        })

    # 1: cluster and summarize thematic groups
    clustered_data = cluster_and_summarize(ideas)

    # 2: build_cluster_graph -> returns (dict, dict, matrix)
    embedding_to_explanation, group_to_explanation, _sim = build_cluster_graph(
        clustered_data
    )

    # 3: merge into global KB
    added = 0
    for emb_tuple, text_block in embedding_to_explanation.items():
        if emb_tuple not in knowledge_base:
            added += 1
        knowledge_base[emb_tuple] = text_block

    return json.dumps({
        "kb_size": len(knowledge_base),
        "clusters_added": added,
        "status": "ok",
    })


@tool(description="Query the global knowledge base using Graph RAG and synthesize an answer.")
def graph_rag_agent(user_query: str) -> str:
    """
    Input:
        user_query: plain text question from Supervisor.

    Behavior:
      1. rag_query(knowledge_base, user_query, top_k=3) → list of {text, score, ...}
      2. Ask _graph_rag_agent_instance to synthesize an answer using ONLY those contexts.
         That agent is prompted with GRAPH_RAG_PROMPT from agent_prompts.yaml.

    Output JSON:
        {
            "answer": "...",
            "sources_used": n,
            "confidence": "high|medium|low",
            "contexts": [...]
        }
    """
    global knowledge_base

    if not knowledge_base:
        return json.dumps({
            "answer": "No knowledge available yet.",
            "sources_used": 0,
            "confidence": "low",
            "contexts": []
        })

    contexts = rag_query(knowledge_base, user_query, top_k=3)

    context_texts = [ctx["text"] for ctx in contexts]
    synthesis_prompt = f"""
You are the Graph RAG synthesis specialist.

User Query: {user_query}

Retrieved Contexts:
{json.dumps(context_texts, indent=2)}

Follow your system instructions. Return ONLY a JSON object with:
{{
    "answer": "your comprehensive answer here",
    "sources_used": <number of contexts used>,
    "confidence": "high/medium/low"
}}
    """.strip()

    llm_raw = _graph_rag_agent_instance(synthesis_prompt)
    llm_text = str(llm_raw).strip()

    # try parse the agent's JSON
    try:
        parsed = json.loads(llm_text)
    except Exception:
        parsed = {
            "answer": llm_text,
            "sources_used": len(contexts),
            "confidence": "medium",
        }

    parsed["contexts"] = contexts
    return json.dumps(parsed)

# ---------------------------------------------------------------------
# SUPERVISOR PROMPT
# ---------------------------------------------------------------------

SUPERVISOR_PROMPT = """
You are the Supervisor Orchestrator.

Your job is to coordinate all other tools to answer the user's request
with stakeholder-ready output.

High-level responsibilities:

1. Persona routing
   - Determine who should speak to the user:
     - marketing_persona_agent
       Use this if the request is about campaigns, messaging, channels,
       growth strategy, brand positioning, comms risk, creator/influencer strategy.
     - ib_persona_agent
       Use this if the request is about investor viewpoint, executive/board risk,
       market perception, competitive posture, regulatory/reputational exposure,
       or "what sectors/startups look promising".

   Also decide which TASK that persona should run:
     For marketing_persona_agent:
       - "summarize_findings_for_stakeholder"
       - "draft_marketing_strategy"
       - "risk_scan"
     For ib_persona_agent:
       - "summarize_findings_for_stakeholder"
       - "investor_opportunity_scan"
       - "risk_scan"

   Pick ONE persona and ONE task that best match the request.

2. Grounding in our knowledge
   You must try to answer using the internal knowledge base / graph.

   Process:
   a) Call graph_rag_agent(user_query) to get an answer JSON.
   b) Inspect its fields:
      - "answer"
      - "confidence" ("high", "medium", or "low")
      - "contexts"
   c) If confidence is "high", continue.
   d) If confidence is "medium" or "low", or if the analysis is clearly missing
      obvious, current context, then you MUST enrich our knowledge:
        i.   Call source_selector_agent(user_query) to get candidate sources.
        ii.  Call scraper_agent(...) on that result to get atomic ideas.
        iii. Call graph_builder_agent(...) on those ideas to update the global KB.
        iv.  Call graph_rag_agent(user_query) AGAIN to get an updated answer JSON.

   The final graph_rag_agent output after this loop is the "final answer JSON".

3. Persona formatting
   You NEVER answer the user yourself.
   Instead:
   - Call the chosen persona tool:
        marketing_persona_agent(task=<task>, answer_json=<final answer JSON string>)
        OR
        ib_persona_agent(task=<task>, answer_json=<final answer JSON string>)
   - The persona returns stakeholder-facing text.
   - You MUST return ONLY that text to the user.

Rules:
- Do NOT expose tool names, embeddings, raw contexts, or internal chains of thought.
  The persona output should talk about "our analysis" or "the analysis".
- Do NOT invent numeric performance metrics, financials, user counts, budgets,
  valuations, unless we were explicitly given them.
- Do NOT output the word "confidence", unless the persona naturally frames uncertainty.

Your available tools:
- source_selector_agent(user_query: str) -> {"sources":[{"url": "...", "type": "..."}]}
- scraper_agent(sources_json: str) -> {"ideas":[...]}      (async)
- graph_builder_agent(ideas_json: str) -> {"kb_size":int,"clusters_added":int,...}
- graph_rag_agent(user_query: str) -> {"answer": "...","confidence":"...","contexts":[...]}
- marketing_persona_agent(task: str, answer_json: str) -> str
- ib_persona_agent(task: str, answer_json: str) -> str

Return policy:
- After calling the correct persona tool with (task, answer_json),
  return ONLY that tool's string output to the user.
""".strip()

# ---------------------------------------------------------------------
# ORCHESTRATOR BUILDER
# ---------------------------------------------------------------------

def _build_orchestrator() -> Agent:
    """
    Build the Supervisor agent with access to:
    - retrieval/graph tools
    - scraping / enrichment tools
    - persona formatting tools
    """
    orchestrator = Agent(
        model=openai_model,
        system_prompt=SUPERVISOR_PROMPT,
        tools=[
            source_selector_agent,
            scraper_agent,
            graph_builder_agent,
            graph_rag_agent,
            marketing_persona_agent,
            ib_persona_agent,
        ],
        callback_handler=None,
    )
    return orchestrator
