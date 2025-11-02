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

# -----------------------------------------
# ENV / PATH / IMPORTS
# -----------------------------------------

load_dotenv()

sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

from graph_rag import rag_query
import backend.scrapers.scraper_agent as WebScraper
from clustering import cluster_and_summarize
from graph_builder import build_cluster_graph

from personas import (
    build_marketing_persona_agent,
    make_marketing_persona_tool,
    build_finance_persona_agent,
    make_finance_persona_tool,
)

# -----------------------------------------
# GLOBAL KB
# -----------------------------------------

knowledge_base = {}

# -----------------------------------------
# MODEL
# -----------------------------------------

openai_model = OpenAIModel(
    model_id="gpt-4o-mini",
)

# -----------------------------------------
# LOAD PROMPTS
# -----------------------------------------

with open("agent_prompts.yaml", "r") as f:
    _p = yaml.safe_load(f)
    SOURCE_SELECTOR_PROMPT = _p["source_selector"]
    SCRAPER_PROMPT = _p["scraper"]
    GRAPH_RAG_PROMPT = _p["graph_rag"]

with open("marketing_strategist.yaml", "r") as f:
    _o = yaml.safe_load(f)
    BASE_ORCHESTRATOR_PROMPT = _o["orchestrator"]

# -----------------------------------------
# HELPERS
# -----------------------------------------

def infer_source_type(url: str, title: str = "", snippet: str = "") -> str:
    if not url:
        return "general"

    from urllib.parse import urlparse
    parsed = urlparse(url)
    netloc = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    title = (title or "").lower()
    snippet = (snippet or "").lower()

    if "reddit.com" in netloc or "redd.it" in netloc:
        if "/comments/" in path or re.search(r"/comments/[a-z0-9]+", path):
            return "reddit_post"
        if re.search(r"^/r/[^/]+/?", path) or re.search(r"^/r/[^/]+/(hot|new|top)", path):
            return "reddit_sub"
        return "reddit_sub"

    if "twitter.com" in netloc or "x.com" in netloc:
        return "twitter"

    if "wikipedia.org" in netloc:
        return "news"

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


def google_search(query: str, num_results: int = 3) -> list:
    api_key = os.environ.get("GOOGLE_API_KEY")
    cse_id = os.environ.get("GOOGLE_CSE_ID")

    if not api_key or not cse_id:
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

        out = []
        for item in data.get("items", [])[:num_results]:
            t = item.get("title", "")
            link = item.get("link", "")
            sn = item.get("snippet", "")
            out.append({
                "title": t,
                "url": link,
                "snippet": sn,
                "type": infer_source_type(link, t, sn),
            })
        return out

    except Exception:
        return google_search(query, num_results)

# -----------------------------------------
# CREATE LOW-LEVEL AGENTS
# -----------------------------------------

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

# personas
_marketing_persona_agent_instance = build_marketing_persona_agent(openai_model)
_investment_banking_persona_agent_instance = build_finance_persona_agent(openai_model)

marketing_persona_agent = make_marketing_persona_tool(_marketing_persona_agent_instance)
ib_persona_agent = make_finance_persona_tool(_investment_banking_persona_agent_instance)

# -----------------------------------------
# TOOL WRAPPERS
# -----------------------------------------

@tool(description="Generate 3 diverse Google queries, then gather top sources for each.")
def source_selector_agent(user_query: str) -> str:
    """
    Returns:
      { "sources": [ { "url": ..., "type": ...}, ... ] }
    """
    try:
        raw = _source_selector_agent_instance(user_query)
        queries = json.loads(str(raw).strip())
    except Exception:
        queries = [
            user_query,
            f"{user_query} latest discussion",
            f"{user_query} controversy reddit"
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
    Input:  {"sources":[{"url":"...","type":"reddit_post"}, ...]}
    Output: {"ideas": ["idea1", "idea2", ...]}
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
    Input: {"ideas":["...", "...", ...]}

    Updates global knowledge_base using cluster_and_summarize + build_cluster_graph.
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
            "status": "no_ideas"
        })

    clustered_data = cluster_and_summarize(ideas)
    embedding_to_explanation, group_to_explanation, _sim = build_cluster_graph(
        clustered_data
    )

    added = 0
    for emb_tuple, text_block in embedding_to_explanation.items():
        if emb_tuple not in knowledge_base:
            added += 1
        knowledge_base[emb_tuple] = text_block

    return json.dumps({
        "kb_size": len(knowledge_base),
        "clusters_added": added,
        "status": "ok"
    })


@tool(description="Query the global knowledge base using Graph RAG and synthesize an answer.")
def graph_rag_agent(user_query: str) -> str:
    """
    Output:
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
    context_texts = [c["text"] for c in contexts]

    synthesis_prompt = f"""
You are the Graph RAG synthesis specialist.

User Query: {user_query}

Retrieved Contexts:
{json.dumps(context_texts, indent=2)}

Return ONLY a JSON object:
{{
    "answer": "your comprehensive answer here",
    "sources_used": <number>,
    "confidence": "high/medium/low"
}}
""".strip()

    llm_raw = _graph_rag_agent_instance(synthesis_prompt)
    llm_text = str(llm_raw).strip()

    try:
        parsed = json.loads(llm_text)
    except Exception:
        parsed = {
            "answer": llm_text,
            "sources_used": len(contexts),
            "confidence": "medium"
        }

    parsed["contexts"] = contexts
    return json.dumps(parsed)

# NOTE:
# marketing_persona_agent and ib_persona_agent are both @tool from the factories.
# Their signature now is:
#   persona_tool(
#       mode: str,               # "plan" or "deliver"
#       persona_task: str,       # ex. "draft_marketing_strategy"
#       kb_size: int,            # len(knowledge_base)
#       graph_answer_json: str   # output from graph_rag_agent(...)
#   ) -> str

# -----------------------------------------
# SUPERVISOR PROMPT WITH LOOPS
# -----------------------------------------

SUPERVISOR_PROMPT = """
You are the Supervisor Orchestrator.

You coordinate personas and data gathering. You NEVER speak directly to the user. You only return what the persona returns at the end.

Follow this exact control loop:

Step 1. Understand the user request.
Decide:
  a) which persona should ultimately answer:
     - marketing_persona_agent
       Use this for questions about marketing strategy, messaging, channels, audience sentiment,
       brand risk, campaign planning, positioning, go-to-market.
     - ib_persona_agent
       Use this for questions about investor viewpoint, market sentiment, competitive posture,
       reputational/regulatory risk, "which areas look investable", etc.

  b) what persona_task that persona should ultimately perform.
     For marketing_persona_agent you may choose:
       - "summarize_findings_for_stakeholder"
       - "draft_marketing_strategy"
       - "risk_scan"
     For ib_persona_agent you may choose:
       - "summarize_findings_for_stakeholder"
       - "investor_opportunity_scan"
       - "risk_scan"

Keep track of: persona_name and persona_task.

Step 2. Query current knowledge.
Call graph_rag_agent(user_query) to get current analysis JSON. Call this CURRENT_ANALYSIS.
Also note KB_SIZE = length of the internal knowledge base.

Step 3. Ask the persona to PLAN.
Call the chosen persona tool in PLAN mode:
   persona_tool(
      mode="plan",
      persona_task=<persona_task>,
      kb_size=KB_SIZE,
      graph_answer_json=CURRENT_ANALYSIS
   )

The persona_tool will return a JSON string that looks like:
  {
    "need_more_info": true/false,
    "persona_task": "...",
    "search_hints": "..."     # only if need_more_info is true
  }

Parse that JSON.

Step 4. Branch:
  If need_more_info is false:
      We already have enough knowledge.
      Set FINAL_ANALYSIS = CURRENT_ANALYSIS.
  If need_more_info is true:
      We must enrich the knowledge base BEFORE answering.

      To enrich:
        4.a Call source_selector_agent(search_hints) to get { "sources": [...] }.
        4.b Call scraper_agent(...) with that sources JSON to get { "ideas": [...] }.
        4.c Call graph_builder_agent(...) with that ideas JSON.
            This updates the global knowledge base internally.
        4.d Call graph_rag_agent(user_query) AGAIN.
            Call this UPDATED_ANALYSIS.
            Set FINAL_ANALYSIS = UPDATED_ANALYSIS.

Step 5. Ask the persona to DELIVER.
Now call the same persona_tool again, but in DELIVER mode:
   persona_tool(
      mode="deliver",
      persona_task=<persona_task>,
      kb_size=KB_SIZE (use the most recent KB size after enrichment if we enriched),
      graph_answer_json=FINAL_ANALYSIS
   )

In DELIVER mode, the persona returns FINAL STAKEHOLDER-FACING TEXT.

Step 6. Return ONLY that stakeholder-facing text to the user.
Do NOT wrap it.
Do NOT mention tool names.
Do NOT mention "plan" or "deliver".
Do NOT mention confidence scores explicitly unless the persona naturally frames uncertainty.
Do NOT mention embeddings or internal retrieval.

You MUST follow this loop every time.
""".strip()

# -----------------------------------------
# BUILD ORCHESTRATOR
# -----------------------------------------

def _build_orchestrator() -> Agent:
    """
    The Supervisor agent that:
    - picks persona + persona_task
    - asks persona in 'plan' mode if KB is enough
    - maybe enriches KB via source_selector -> scraper -> graph_builder
    - asks persona in 'deliver' mode for final answer
    - returns ONLY persona output
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
