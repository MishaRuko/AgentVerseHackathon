import asyncio
import json
import logging
import os
import re
import sys
from urllib.parse import quote_plus, urlparse

import requests
import scrapers.scraper_agent as WebScraper
import yaml
from clustering import cluster_and_summarize
from dotenv import load_dotenv
from graph_builder import build_cluster_graph
from graph_rag import rag_query
from strands import Agent
from strands.models.openai import OpenAIModel

from personas import (build_finance_persona_agent,
                      build_marketing_persona_agent, make_finance_persona_tool,
                      make_marketing_persona_tool)

logger = logging.getLogger(__name__)

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
if BACKEND_DIR not in sys.path:
    sys.path.append(BACKEND_DIR)

load_dotenv()


with open(os.path.join(REPO_ROOT, "system_prompt.yaml"), "r") as f:
    _sys_yaml = yaml.safe_load(f)
    SUPERVISOR_PROMPT = _sys_yaml["supervisor"]

with open(os.path.join(REPO_ROOT, "agent_prompts.yaml"), "r") as f:
    _p = yaml.safe_load(f)
    SOURCE_SELECTOR_PROMPT = _p["source_selector"]
    SCRAPER_PROMPT = _p["scraper"]
    GRAPH_RAG_PROMPT = _p["graph_rag"]

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

    # TWITTER DISABLED - uncomment to re-enable Twitter scraping
    # if "twitter.com" in netloc or "x.com" in netloc:
    #     return "twitter"

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

    except Exception as e:
        print(f"Google search API error: {e}. Falling back to mock results.")
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
finance_persona_tool = make_finance_persona_tool(_finance_persona_agent_instance)

_supervisor_router_agent_instance = Agent(
    model=openai_model,
    name="Supervisor Router",
    description="Classifies which persona should answer and what task it should perform.",
    system_prompt=SUPERVISOR_PROMPT,
    callback_handler=None,
)

knowledge_base = {}


def run_source_selector(user_query: str) -> dict:
    logger.info("   🔍 Source selector generating search queries...")
    raw = _source_selector_agent_instance(user_query)
    try:
        queries = json.loads(str(raw).strip())
        logger.info(f"   ✅ Generated {len(queries)} search queries")
    except Exception as e:
        logger.warning(f"   ⚠️  Failed to parse queries, using fallback: {e}")
        queries = [
            user_query,
            f"{user_query} latest discussion",
            f"{user_query} controversy reddit",
        ]

    all_sources = []
    for i, q in enumerate(queries[:3], 1):
        logger.info(f"   🔎 Query {i}: {q}")
        results = google_search(q, num_results=3)
        logger.info(f"      Found {len(results)} results")
        for r in results:
            all_sources.append({
                "url": r["url"],
                "type": r["type"],
            })

    logger.info(f"   ✅ Total sources collected: {len(all_sources)}")
    return {"sources": all_sources}


async def run_scraper(sources: dict) -> dict:
    source_list = sources.get("sources", [])
    logger.info(f"   🌐 Starting scraper for {len(source_list)} sources...")
    loop = asyncio.get_running_loop()
    ideas_list = await loop.run_in_executor(
        None,
        WebScraper.scrape_and_generate_ideas,
        source_list
    )
    logger.info(f"   ✅ Scraping complete. Extracted {len(ideas_list)} ideas")
    return {"ideas": ideas_list}


def update_graph_and_kb(ideas: dict) -> dict:
    global knowledge_base

    idea_list = ideas.get("ideas", [])
    if not idea_list:
        logger.warning("   ⚠️  No ideas to process")
        return ({
            "kb_size": len(knowledge_base),
            "clusters_added": 0,
            "status": "no_ideas",
            "needs_more_data": True
        }, None)

    logger.info(f"   🔄 Clustering {len(idea_list)} ideas...")
    clustered = cluster_and_summarize(idea_list)
    logger.info(f"   ✅ Created {len(clustered)} clusters")

    logger.info(f"   🔗 Building cluster graph...")
    embedding_to_explanation, group_to_explanation, _sim = build_cluster_graph(clustered)

    # Check if clusters are too dissimilar (no groups formed)
    needs_more_data = len(group_to_explanation) == 0 and len(clustered) > 1

    if needs_more_data:
        logger.warning(f"   ⚠️  Clusters too dissimilar - no meaningful connections found")
    else:
        logger.info(f"   ✅ Graph built with {len(group_to_explanation)} cluster groups")

    added = 0
    for emb_tuple, txt in embedding_to_explanation.items():
        if emb_tuple not in knowledge_base:
            added += 1
        knowledge_base[emb_tuple] = txt

    logger.info(f"   ✅ Added {added} new entries to knowledge base")
    frontend_info = [clustered, group_to_explanation, _sim]
    return ({
        "kb_size": len(knowledge_base),
        "clusters_added": added,
        "status": "ok" if not needs_more_data else "insufficient_similarity",
        "needs_more_data": needs_more_data
    }, frontend_info)


def run_graph_rag(user_query: str) -> dict:
    global knowledge_base

    if not knowledge_base:
        logger.warning("   ⚠️  Knowledge base is empty")
        return {
            "answer": "No knowledge available yet.",
            "sources_used": 0,
            "confidence": "low",
            "contexts": []
        }

    logger.info(f"   🔍 Querying KB with {len(knowledge_base)} entries...")
    contexts = rag_query(knowledge_base, user_query, top_k=3)
    ctx_texts = [c["text"] for c in contexts]
    logger.info(f"   ✅ Retrieved {len(contexts)} relevant contexts")

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

    logger.info(f"\n--SYNTHESIS PROMPT--\n{synthesis_prompt}\n--------------------")

    logger.info(f"   🤖 Synthesizing answer with LLM...")
    llm_raw = _graph_rag_agent_instance(synthesis_prompt)
    llm_text = str(llm_raw).strip()

    try:
        parsed = json.loads(llm_text)
        logger.info(f"   ✅ Synthesis complete (confidence: {parsed.get('confidence', 'unknown')})")
    except Exception as e:
        logger.warning(f"   ⚠️  Failed to parse LLM response: {e}")
        parsed = {
            "answer": llm_text,
            "sources_used": len(contexts),
            "confidence": "medium"
        }

    parsed["contexts"] = contexts
    return parsed


def route_persona_and_task(user_query: str) -> dict:
    logger.info("   🤖 Supervisor analyzing query for routing...")
    result = _supervisor_router_agent_instance(user_query)
    try:
        routing = json.loads(str(result).strip())
        logger.info(f"   ✅ Routing decision made")
    except Exception as e:
        logger.warning(f"   ⚠️  Failed to parse routing, using default: {e}")
        routing = {
            "persona_name": "marketing",
            "persona_task": "summarize_findings_for_stakeholder"
        }
    return routing


def persona_plan(persona_name: str, persona_task: str, user_query: str, kb_size: int, analysis: dict) -> dict:
    logger.info(f"   🤖 {persona_name.capitalize()} persona creating plan...")
    analysis_json = json.dumps(analysis)

    if persona_name == "marketing":
        raw = marketing_persona_tool(
            mode="plan",
            persona_task=persona_task,
            user_query=user_query,
            kb_size=kb_size,
            graph_answer_json=analysis_json
        )
    else:
        raw = finance_persona_tool(
            mode="plan",
            persona_task=persona_task,
            user_query=user_query,
            kb_size=kb_size,
            graph_answer_json=analysis_json
        )

    try:
        plan = json.loads(raw)
        logger.info(f"   ✅ Plan created")
    except Exception as e:
        logger.warning(f"   ⚠️  Failed to parse plan, using default: {e}")
        plan = {
            "need_more_info": True,
            "persona_task": persona_task,
            "search_hints": user_query or "broadly scrape recent discussion and sentiment on this topic"
        }
    return plan


def persona_deliver(persona_name: str, persona_task: str, user_query: str, kb_size: int, analysis: dict) -> str:
    logger.info(f"   🤖 {persona_name.capitalize()} persona generating final response...")
    analysis_json = json.dumps(analysis)

    if persona_name == "marketing":
        final_resp = marketing_persona_tool(
            mode="deliver",
            persona_task=persona_task,
            user_query=user_query,
            kb_size=kb_size,
            graph_answer_json=analysis_json
        )
    else:
        final_resp = finance_persona_tool(
            mode="deliver",
            persona_task=persona_task,
            user_query=user_query,
            kb_size=kb_size,
            graph_answer_json=analysis_json
        )

    logger.info(f"   ✅ Response generated by {persona_name} persona")
    return final_resp
