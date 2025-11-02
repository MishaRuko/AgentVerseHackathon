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

# -------------------------------------------------
# setup imports / globals same as before
# -------------------------------------------------

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

knowledge_base = {}

openai_model = OpenAIModel(
    model_id="gpt-4o-mini",
)

with open("agent_prompts.yaml", "r") as f:
    _p = yaml.safe_load(f)
    SOURCE_SELECTOR_PROMPT = _p["source_selector"]
    SCRAPER_PROMPT = _p["scraper"]
    GRAPH_RAG_PROMPT = _p["graph_rag"]

with open("marketing_strategist.yaml", "r") as f:
    _o = yaml.safe_load(f)
    ORCHESTRATOR_PROMPT = _o["orchestrator"]


# -------------------------------------------------
# util functions same as before (infer_source_type, google_search)
# -------------------------------------------------

def infer_source_type(url: str, title: str = "", snippet: str = "") -> str:
    if not url:
        return "general"
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
                "snippet": f"More info about {query}...",
                "type": "general"
            },
            {
                "title": f"Result 3 for '{query}'",
                "url": f"https://example.com/result3?q={quote_plus(query)}",
                "snippet": f"Extra details about {query}...",
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
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

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


# -------------------------------------------------
# Create all agents
# -------------------------------------------------

# 1. low-level workers
_source_selector_agent_instance = Agent(
    model=openai_model,
    name="Source Selector",
    description="Generate 3 smart queries to find relevant sources.",
    system_prompt=SOURCE_SELECTOR_PROMPT,
    callback_handler=None,
)

_scraper_agent_instance = Agent(
    model=openai_model,
    name="Web Scraper",
    description="Extract atomic ideas from provided sources.",
    system_prompt=SCRAPER_PROMPT,
    callback_handler=None,
)

_graph_rag_agent_instance = Agent(
    model=openai_model,
    name="Graph RAG Synthesizer",
    description="Synthesize an answer from graph KB contexts.",
    system_prompt=GRAPH_RAG_PROMPT,
    callback_handler=None,
)

# 2. personas
_marketing_persona_agent_instance = build_marketing_persona_agent(openai_model)
_finance_persona_agent_instance = build_finance_persona_agent(openai_model)

marketing_persona_tool = make_marketing_persona_tool(_marketing_persona_agent_instance)
finance_persona_tool   = make_finance_persona_tool(_finance_persona_agent_instance)

# 3. tiny router LLM for persona selection
_supervisor_router_agent_instance = Agent(
    model=openai_model,
    name="Supervisor Router",
    description="Classifies which persona should answer and what task it should perform.",
    system_prompt=(
        "You are a routing assistant.\n"
        "Input: a user query.\n"
        "Output: STRICT JSON with keys:\n"
        "{\n"
        '  "persona_name": "marketing" | "finance",\n'
        '  "persona_task": string   // e.g. "draft_marketing_strategy", "risk_scan", "investor_opportunity_scan"\n'
        "}\n\n"
        "Rules:\n"
        "- Use persona_name='marketing' for marketing/branding/growth/messaging/comms questions.\n"
        "- Use persona_name='finance' for investor/market-sentiment/risk/opportunity/competitive questions.\n"
        "- persona_task should be one of:\n"
        "   marketing: 'summarize_findings_for_stakeholder', 'draft_marketing_strategy', 'risk_scan'\n"
        "   finance:   'summarize_findings_for_stakeholder', 'investor_opportunity_scan', 'risk_scan'\n"
        "Return ONLY JSON. No commentary."
    ),
    callback_handler=None,
)


# -------------------------------------------------
# Wrappers around tool-like behaviors
# -------------------------------------------------

def run_source_selector(user_query: str) -> dict:
    raw = _source_selector_agent_instance(user_query)
    try:
        queries = json.loads(str(raw).strip())
    except Exception:
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

    return {"sources": all_sources}


async def run_scraper(sources: dict) -> dict:
    # sources is {"sources":[{"url":...,"type":...}, ...]}
    loop = asyncio.get_running_loop()
    ideas_list = await loop.run_in_executor(
        None,
        WebScraper.scrape_and_generate_ideas,
        sources.get("sources", [])
    )
    return {"ideas": ideas_list}


def update_graph_and_kb(ideas: dict) -> dict:
    global knowledge_base

    idea_list = ideas.get("ideas", [])
    if not idea_list:
        return {
            "kb_size": len(knowledge_base),
            "clusters_added": 0,
            "status": "no_ideas"
        }

    clustered = cluster_and_summarize(idea_list)
    embedding_to_explanation, group_to_explanation, _sim = build_cluster_graph(clustered)

    added = 0
    for emb_tuple, txt in embedding_to_explanation.items():
        if emb_tuple not in knowledge_base:
            added += 1
        knowledge_base[emb_tuple] = txt

    return {
        "kb_size": len(knowledge_base),
        "clusters_added": added,
        "status": "ok"
    }


def run_graph_rag(user_query: str) -> dict:
    global knowledge_base

    if not knowledge_base:
        return {
            "answer": "No knowledge available yet.",
            "sources_used": 0,
            "confidence": "low",
            "contexts": []
        }

    contexts = rag_query(knowledge_base, user_query, top_k=3)
    ctx_texts = [c["text"] for c in contexts]

    synthesis_prompt = f"""
You are the Graph RAG synthesis specialist.

User Query: {user_query}

Retrieved Contexts:
{json.dumps(ctx_texts, indent=2)}

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

async def handle_user_query(user_query: str) -> str:
    """
    This is the real brain.

    1. Route to persona + task.
    2. Pull current KB using graph_rag.
    3. Ask persona in 'plan' mode if KB is enough.
    4. If not enough:
        a. source_selector -> scraper -> graph_builder to enrich KB
        b. run graph_rag again
    5. Ask persona in 'deliver' mode for final stakeholder-facing output.
    6. Return that final output text.
    """

    # Step 1: persona routing
    routing = route_persona_and_task(user_query)
    persona_name = routing["persona_name"]           # "marketing" or "finance"
    persona_task = routing["persona_task"]           # ex. "draft_marketing_strategy"

    # Step 2: current analysis from KB
    initial_analysis = run_graph_rag(user_query)
    kb_size_now = len(knowledge_base)

    # Step 3: ask persona to plan
    plan = persona_plan(persona_name, persona_task, kb_size_now, initial_analysis)

    # Step 4: maybe enrich
    final_analysis = initial_analysis
    kb_size_after = kb_size_now

    if plan.get("need_more_info", False):
        search_hints = plan.get("search_hints", user_query)

        # 4a. pick sources
        sources = run_source_selector(search_hints)

        # 4b. scrape -> ideas
        ideas = await run_scraper(sources)

        # 4c. update KB
        _kb_update_info = update_graph_and_kb(ideas)
        kb_size_after = len(knowledge_base)

        # 4d. re-run graph rag with enriched KB
        final_analysis = run_graph_rag(user_query)

    # Step 5: persona deliver
    final_output_text = persona_deliver(
        persona_name=persona_name,
        persona_task=persona_task,
        kb_size=kb_size_after,
        analysis=final_analysis
    )

    # Step 6: return final stakeholder-facing text
    return final_output_text
