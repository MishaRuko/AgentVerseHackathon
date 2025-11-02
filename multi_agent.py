import os
import sys
import json
import re
import asyncio
import requests
import yaml
from urllib.parse import quote_plus, urlparse
from dotenv import load_dotenv
from strands import Agent
from strands.models.openai import OpenAIModel

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.append(BACKEND_DIR)

load_dotenv()

from graph_rag import rag_query
import scrapers.scraper_agent as WebScraper
from clustering import cluster_and_summarize
from graph_builder import build_cluster_graph
from personas import (
    build_marketing_persona_agent,
    make_marketing_persona_tool,
    build_finance_persona_agent,
    make_finance_persona_tool,
)

with open(os.path.join(REPO_ROOT, "system_prompt.yaml"), "r") as f:
    _sys_yaml = yaml.safe_load(f)
    SUPERVISOR_PROMPT = _sys_yaml["supervisor"]

with open(os.path.join(REPO_ROOT, "agent_prompts.yaml"), "r") as f:
    _p = yaml.safe_load(f)
    SOURCE_SELECTOR_PROMPT = _p["source_selector"]
    SCRAPER_PROMPT = _p["scraper"]
    GRAPH_RAG_PROMPT = _p["graph_rag"]

with open(os.path.join(REPO_ROOT, "marketing_strategist.yaml"), "r") as f:
    _o = yaml.safe_load(f)
    BASE_ORCHESTRATOR_PROMPT = _o["orchestrator"]

openai_model = OpenAIModel(
    model_id="gpt-4o-mini",
)

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

_marketing_persona_agent_instance = build_marketing_persona_agent(openai_model)
_finance_persona_agent_instance = build_finance_persona_agent(openai_model)

marketing_persona_tool = make_marketing_persona_tool(_marketing_persona_agent_instance)
finance_persona_tool   = make_finance_persona_tool(_finance_persona_agent_instance)

_supervisor_router_agent_instance = Agent(
    model=openai_model,
    name="Supervisor Router",
    description="Classifies which persona should answer and what task it should perform.",
    system_prompt=(
        "You are a routing assistant.\n"
        "Input: a user query.\n"
        "Output: STRICT JSON with keys:\n"
        "{\n"
        '  \"persona_name\": \"marketing\" | \"finance\",\n'
        '  \"persona_task\": string   // e.g. \"draft_marketing_strategy\", \"risk_scan\", \"investor_opportunity_scan\"\n'
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

knowledge_base = {}

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
    return parsed


def route_persona_and_task(user_query: str) -> dict:
    result = _supervisor_router_agent_instance(user_query)
    try:
        routing = json.loads(str(result).strip())
    except Exception:
        routing = {
            "persona_name": "marketing",
            "persona_task": "summarize_findings_for_stakeholder"
        }
    return routing


def persona_plan(persona_name: str, persona_task: str, kb_size: int, analysis: dict) -> dict:
    analysis_json = json.dumps(analysis)

    if persona_name == "marketing":
        raw = marketing_persona_tool(
            mode="plan",
            persona_task=persona_task,
            kb_size=kb_size,
            graph_answer_json=analysis_json
        )
    else:
        raw = finance_persona_tool(
            mode="plan",
            persona_task=persona_task,
            kb_size=kb_size,
            graph_answer_json=analysis_json
        )

    try:
        plan = json.loads(raw)
    except Exception:
        plan = {
            "need_more_info": True,
            "persona_task": persona_task,
            "search_hints": "broadly scrape recent discussion and sentiment on this topic"
        }
    return plan


def persona_deliver(persona_name: str, persona_task: str, kb_size: int, analysis: dict) -> str:
    analysis_json = json.dumps(analysis)

    if persona_name == "marketing":
        final_resp = marketing_persona_tool(
            mode="deliver",
            persona_task=persona_task,
            kb_size=kb_size,
            graph_answer_json=analysis_json
        )
    else:
        final_resp = finance_persona_tool(
            mode="deliver",
            persona_task=persona_task,
            kb_size=kb_size,
            graph_answer_json=analysis_json
        )

    return final_resp
