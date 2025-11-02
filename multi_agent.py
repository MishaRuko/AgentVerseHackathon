from strands import Agent, tool
from strands.models.openai import OpenAIModel
import json
import asyncio
import sys
import os
import requests
from urllib.parse import quote_plus
from dotenv import load_dotenv
import re
from urllib.parse import urlparse
from datetime import datetime
import asyncio
import yaml

# Load environment variables from .env file
load_dotenv()

# Add backend directory to path for imports
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))
from graph_rag import rag_query

# This script uses the Strands Agents SDK with the "Agents as Tools" pattern.
# Each specialist (source selector, scraper, vector DB) is implemented as a 
# separate Agent, then wrapped as a @tool function so the orchestrator can 
# invoke them. This follows the multi-agent example from Strands documentation.

# ============================================
# CONFIGURE OPENAI MODEL
# ============================================

# Make sure OPENAI_API_KEY is set in your environment
# export OPENAI_API_KEY='your-api-key-here'

openai_model = OpenAIModel(
    model_id="gpt-4o-mini",  # Using gpt-4o-mini for cost efficiency
    # Alternatively use: "gpt-4o", "gpt-4-turbo", "gpt-3.5-turbo"
)

# ============================================
# LOAD PROMPTS FROM YAML FILE
# ============================================

with open("agent_prompts.yaml", "r") as f:
    prompts = yaml.safe_load(f)
    SOURCE_SELECTOR_PROMPT = prompts["source_selector"]
    SCRAPER_PROMPT = prompts["scraper"]
    GRAPH_RAG_PROMPT = prompts["graph_rag"]

with open("marketing_strategist.yaml", "r") as f:
    prompts = yaml.safe_load(f)
    SYSTEM_PROMPT = prompts["orchestrator"]

# ============================================
# IMPORT SPECIALISED AGENTS 
# ============================================

import backend.scrapers.scraper_agent as WebScraper

# ============================================
# GOOGLE SEARCH HELPER FUNCTIONS
# ============================================

def google_search(query: str, num_results: int = 3) -> list:
    """
    Perform a Google search and return top results.
    Uses Google Custom Search JSON API.
    
    To use this, you need:
    1. GOOGLE_API_KEY environment variable
    2. GOOGLE_CSE_ID (Custom Search Engine ID) environment variable
    
    Get these from: https://developers.google.com/custom-search/v1/overview
    """
    api_key = os.environ.get("GOOGLE_API_KEY")
    cse_id = os.environ.get("GOOGLE_CSE_ID")
    
    if not api_key or not cse_id:
        print(f"  ⚠ Google API credentials not set, using mock results for: {query}")
        # Return mock results for demo purposes
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
    
    # Make actual Google search API call
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
            res = {
                "title": title,
                "url": link,
                "snippet": snippet,
                "type": infer_source_type(link, title, snippet)
            }
            results.append(res)
        
        return results
    except Exception as e:
        print(f"  ⚠ Google search error: {e}, using mock results")
        return google_search(query, num_results)  # Fallback to mock


def infer_source_type(url: str, title: str = "", snippet: str = "") -> str:
    """
    Heuristic classifier mapping a search result to the scraper type used by
    backend.scrapers.scraper_agent.scrape_source:
        - "reddit_post", "reddit_sub", "twitter", "news", "general"
    """
    if not url:
        return "general"

    parsed = urlparse(url)
    netloc = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    title = (title or "").lower()
    snippet = (snippet or "").lower()

    # Reddit: comment thread vs subreddit listing
    if "reddit.com" in netloc or "redd.it" in netloc:
        if "/comments/" in path or re.search(r"/comments/[a-z0-9]+", path):
            return "reddit_post"
        if re.search(r"^/r/[^/]+/?", path) or re.search(r"^/r/[^/]+/(hot|new|top)", path):
            return "reddit_sub"
        # fallback reddit -> treat as subreddit listing
        return "reddit_sub"

    # Twitter / X
    if "twitter.com" in netloc or "x.com" in netloc:
        if "/status/" in path:
            return "twitter"
        # if it's a profile or search, still treat as general (or add 'twitter' if desired)
        return "twitter"

    # Wikipedia / encyclopedic -> map to 'news' (your scraper expects 'news' for wiki-style)
    if "wikipedia.org" in netloc:
        return "news"

    # Heuristics for news sites (domain or path indicators)
    news_indicators = ["news", "article", "/articles/", "/202", "/story", "press", "opinion"]
    if any(ind in path for ind in news_indicators) or any(ind in title or ind in snippet for ind in news_indicators):
        return "news"

    # Some known news domains - expand as needed
    known_news_domains = {"nytimes.com", "theguardian.com", "bbc.co.uk", "cnn.com", "washingtonpost.com"}
    if any(d in netloc for d in known_news_domains):
        return "news"

    # Fallback to general webpage
    return "general"

# ============================================
# CREATE SPECIALIST AGENT INSTANCES
# ============================================

# Create the specialist agents (these are actual Agent objects using OpenAI)
_source_selector_agent_instance = Agent(
    model=openai_model,
    name="Source Selector",
    description="Analyzes queries and identifies relevant information sources",
    system_prompt=SOURCE_SELECTOR_PROMPT,
    callback_handler=None
)

_scraper_agent_instance = Agent(
    model=openai_model,
    name="Web Scraper",
    description="Scrapes content from provided sources",
    system_prompt=SCRAPER_PROMPT,
    callback_handler=None
)

_graph_rag_agent_instance = Agent(
    model=openai_model,
    name="Graph RAG Manager",
    description="Builds knowledge base from documents and answers queries using graph RAG",
    system_prompt=GRAPH_RAG_PROMPT,
    callback_handler=None
)


# ============================================
# WRAP AGENTS AS TOOLS FOR ORCHESTRATOR
# ============================================

@tool(description="Generates search queries and finds relevant sources via Google search.")
def source_selector_agent(query: str) -> str:
    """
    Invokes the Source Selector Agent to:
    1. Generate 3 different Google search queries
    2. Search Google for each query
    3. Return top 3 results per query (9 total URLs)
    """
    print("→ Source Selector Agent activated")
    print(f"  📝 User query: {query}")
    
    try:
        # Step 1: Ask agent to generate 3 search queries
        result = _source_selector_agent_instance(query)
        response_text = str(result).strip()
        
        print(f"  🤖 Agent generated queries: {response_text[:150]}...")
        
        # Parse the search queries from agent response
        search_queries = json.loads(response_text)
        
        if not isinstance(search_queries, list) or len(search_queries) != 3:
            raise ValueError("Agent must return exactly 3 search queries as a JSON array")
        
        print(f"  ✓ Generated {len(search_queries)} search queries")
        
        # Step 2: Search Google for each query
        all_sources = []
        for i, search_query in enumerate(search_queries, 1):
            print(f"  🔍 Searching Google [{i}/3]: {search_query}")
            results = google_search(search_query, num_results=3)
            
            # Add results to sources list
            for result in results:
                all_sources.append({
                    "url": result["url"],
                    "type": result["type"]
                })
        
        print(f"  ✓ Found {len(all_sources)} total sources")
        
        return json.dumps({"sources": all_sources})
        
    except Exception as e:
        print(f"  ⚠ Error: {type(e).__name__}: {str(e)[:100]}")
        print(f"  → Using fallback with generic search queries")
        
        # Fallback: Generate basic search queries
        fallback_queries = [
            query,
            f"{query} latest news",
            f"{query} discussion forum"
        ]
        
        all_sources = []
        for search_query in fallback_queries:
            results = google_search(search_query, num_results=3)
            for result in results:
                all_sources.append({
                    "url": result["url"],
                    "type": "web"
                })
        
        return json.dumps({"sources": all_sources})


@tool(description="Scrapes content from provided sources and returns structured documents.")
async def scraper_agent(sources_json: str) -> str:
    """
    Uses the WebScraper class to scrape content from sources.
    Returns structured documents in JSON format.
    """

    print("→ Scraper Agent activated")

    try:
        payload = json.loads(sources_json)
        sources = payload.get("sources") if isinstance(payload, dict) else payload
        sources = sources or []
    except Exception:
        sources = []

    # ensure each source is the expected shape for scrape_and_generate_ideas:
    # list of {"url": "...", "type": "..."}
    # (source_selector_agent should already produce that)
    # Call the synchronous function in a thread pool so we don't block the event loop
    loop = asyncio.get_running_loop()
    try:
        LoI = await loop.run_in_executor(
            None,
            WebScraper.scrape_and_generate_ideas,
            sources
        )

        print(LoI)
        return json.dumps(LoI)

    except Exception as e:
        print(f"  ⚠ scrape failure: {e}")
        LoI = []
        return json.dumps(LoI)

@tool(description="Answers queries using Graph RAG by searching a knowledge base and synthesizing answers.")
def graph_rag_agent(kb: dict, query: str) -> str:
    """
    Uses graph_rag.py to query a knowledge base and synthesize an answer.
    
    This agent:
    1. Takes a pre-built knowledge base (dict of embedding:text pairs)
    2. Uses rag_query() to retrieve relevant contexts via semantic search
    3. Passes the contexts to the LLM agent to synthesize a comprehensive answer
    
    Args:
        kb: Pre-built knowledge base dictionary {embedding_tuple: text_string}
            Where embedding_tuple is a tuple of floats (from OpenAI embeddings)
        query: User query string to answer
    
    Returns:
        JSON string with answer, confidence, and retrieved contexts
    """
    print(f"→ Graph RAG Agent activated")
    print(f"  🔍 Query: '{query}'")
    
    try:
        if not kb or not isinstance(kb, dict):
            return json.dumps({"error": "Knowledge base must be a non-empty dictionary"})
        
        print(f"  � Knowledge base size: {len(kb)} documents")
        
        # Retrieve relevant contexts using graph_rag
        contexts = rag_query(kb, query, top_k=3)
        
        print(f"  ✓ Retrieved {len(contexts)} relevant contexts")
        
        # Use the agent to synthesize an answer from contexts
        context_texts = [ctx["text"] for ctx in contexts]
        prompt = f"""Based on the following retrieved contexts, answer the user's query.

User Query: {query}

Retrieved Contexts:
{json.dumps(context_texts, indent=2)}

Provide a comprehensive answer based on these contexts. Return ONLY a JSON object with this format:
{{
    "answer": "your comprehensive answer here",
    "sources_used": <number of contexts used>,
    "confidence": "high/medium/low"
}}
"""
        
        result = _graph_rag_agent_instance(prompt)
        response_text = str(result).strip()
        
        # Try to parse as JSON
        try:
            answer_data = json.loads(response_text)
            answer_data["contexts"] = contexts  # Add retrieved contexts
            return json.dumps(answer_data)
        except:
            # Fallback if agent doesn't return valid JSON
            return json.dumps({
                "answer": response_text,
                "contexts": contexts,
                "sources_used": len(contexts),
                "confidence": "medium"
            })
        
    except Exception as e:
        print(f"  ⚠ Error in Graph RAG Agent: {type(e).__name__}: {str(e)}")
        return json.dumps({"error": str(e)})


# ============================================
# ORCHESTRATOR AGENT
# ============================================

def _build_orchestrator() -> Agent:
    """
    Create the main orchestrator Agent that coordinates the specialist agents.
    
    The orchestrator has access to three specialist agents (wrapped as tools)
    and can invoke them to complete complex workflows.
    """
    system_prompt = SYSTEM_PROMPT

    orchestrator = Agent(
        model=openai_model,
        system_prompt=system_prompt,
        tools=[source_selector_agent, scraper_agent, graph_rag_agent],
        callback_handler=None
    )
    return orchestrator