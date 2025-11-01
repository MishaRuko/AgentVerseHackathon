from strands import Agent, tool
from strands.models.openai import OpenAIModel
import json
import asyncio
import os
import requests
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

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
# SYSTEM PROMPTS FOR SPECIALIST AGENTS
# ============================================

SOURCE_SELECTOR_PROMPT = """
You are a search query specialist. Your job is to take a user's question and generate 3 different Google search queries that will help find comprehensive information about that topic.

Guidelines:
1. Generate 3 distinct search queries that approach the topic from different angles
2. Each query should be relevant but explore different aspects of the user's question
3. Make queries specific and actionable for Google search
4. Consider using different search modifiers (site:, intitle:, etc.) to get diverse results
5. Return ONLY a JSON array (no extra text) with exactly 3 search queries:

["first search query", "second search query", "third search query"]

Example:
User query: "What are people saying about AI safety?"
Your response: ["AI safety concerns 2024", "site:reddit.com AI alignment discussion", "artificial intelligence safety research latest"]

Be concise and return only valid JSON.
"""

SCRAPER_PROMPT = """
You are a web scraping specialist. Given a list of sources (as JSON):
1. Extract content from each source
2. Return ONLY a JSON array (no extra text) with this format:
[
    {"source": "url", "text": "content...", "metadata": {"type": "..."}}
]

For this demo, simulate scraped content. Return only valid JSON.
"""

VECTOR_DB_PROMPT = """
You are a vector database specialist. Given documents (as JSON):
1. Process and store them in a vector database
2. Return ONLY a JSON object (no extra text) with this format:
{
    "stored": <count>,
    "ids": ["doc_0", "doc_1", ...]
}

For this demo, simulate storage. Return only valid JSON.
"""

# ============================================
# GOOGLE SEARCH HELPER FUNCTION
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
                "snippet": f"Mock search result about {query}..."
            },
            {
                "title": f"Result 2 for '{query}'",
                "url": f"https://example.com/result2?q={quote_plus(query)}",
                "snippet": f"Additional information about {query}..."
            },
            {
                "title": f"Result 3 for '{query}'",
                "url": f"https://example.com/result3?q={quote_plus(query)}",
                "snippet": f"More details about {query}..."
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
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", "")
            })
        
        return results
    except Exception as e:
        print(f"  ⚠ Google search error: {e}, using mock results")
        return google_search(query, num_results)  # Fallback to mock


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

_vector_db_agent_instance = Agent(
    model=openai_model,
    name="Vector Database Manager",
    description="Stores documents in vector database",
    system_prompt=VECTOR_DB_PROMPT,
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
                    "title": result["title"],
                    "snippet": result["snippet"],
                    "search_query": search_query,
                    "type": "web"
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
                    "title": result["title"],
                    "snippet": result["snippet"],
                    "search_query": search_query,
                    "type": "web"
                })
        
        return json.dumps({"sources": all_sources})


@tool(description="Scrapes content from provided sources and returns structured documents.")
def scraper_agent(sources_json: str) -> str:
    """
    Invokes the Web Scraper Agent to scrape content from sources.
    This is a REAL agent that can reason about which scraping strategies to use.
    """
    print("→ Scraper Agent activated")
    
    # Format the prompt for the agent
    prompt = f"""Please scrape the following sources and return the content as a JSON array.

Sources to scrape:
{sources_json}

Return ONLY a JSON array of documents with this format:
[
    {{"source": "url", "text": "scraped content", "metadata": {{"type": "...", "scraped_at": "...", "word_count": ...}}}}
]
"""
    
    # Invoke the actual agent
    result = _scraper_agent_instance(prompt)
    response_text = str(result).strip()
    
    # Try to parse as JSON, if it fails provide a fallback
    try:
        json.loads(response_text)
        return response_text
    except:
        # Fallback only if agent didn't return valid JSON
        print("  ⚠ Agent didn't return valid JSON, using fallback")
        try:
            payload = json.loads(sources_json)
        except:
            payload = {"sources": []}
        
        docs = []
        for i, s in enumerate(payload.get("sources", [])):
            url = s.get("url", "")
            doc_type = s.get("type", "unknown")
            
            if "reddit" in url.lower():
                text = f"[Reddit Discussion] Users are discussing AI safety concerns. Top comment: 'We need better alignment research.' Discussion includes views on AGI timelines and safety measures."
            else:
                text = f"[Article] This is a comprehensive article about artificial intelligence developments. The content covers recent breakthroughs, safety considerations, and expert opinions on the future of AI technology."
            
            docs.append({
                "source": url,
                "text": text,
                "metadata": {
                    "type": doc_type,
                    "scraped_at": "2025-11-01T00:00:00Z",
                    "word_count": len(text.split())
                }
            })
        
        return json.dumps(docs)


@tool(description="Stores documents in a vector database and returns storage confirmation.")
def vector_db_agent(documents_json: str) -> str:
    """
    Invokes the Vector Database Agent to store documents.
    This is a REAL agent that can reason about document processing and storage.
    """
    print("→ Vector DB Agent activated")
    
    # Format the prompt for the agent
    prompt = f"""Please process and store the following documents in the vector database.

Documents to store:
{documents_json}

Return ONLY a JSON object with this format:
{{
    "stored": <count>,
    "ids": ["id1", "id2", ...],
    "embedding_model": "model_name",
    "vector_dimension": 1536,
    "index_name": "index_name"
}}
"""
    
    # Invoke the actual agent
    result = _vector_db_agent_instance(prompt)
    response_text = str(result).strip()
    
    # Try to parse as JSON, if it fails provide a fallback
    try:
        json.loads(response_text)
        return response_text
    except:
        # Fallback only if agent didn't return valid JSON
        print("  ⚠ Agent didn't return valid JSON, using fallback")
        try:
            docs = json.loads(documents_json)
        except:
            docs = []
        
        stored_ids = []
        for i, doc in enumerate(docs):
            doc_id = f"vec_doc_{hash(doc.get('source', '')) % 10000}_{i}"
            stored_ids.append(doc_id)
        
        result = {
            "stored": len(docs),
            "ids": stored_ids,
            "embedding_model": "mock-embeddings-v1",
            "vector_dimension": 1536,
            "index_name": "ai_safety_documents"
        }
        
        return json.dumps(result)


# ============================================
# ORCHESTRATOR AGENT
# ============================================

def _build_orchestrator() -> Agent:
    """
    Create the main orchestrator Agent that coordinates the specialist agents.
    
    The orchestrator has access to three specialist agents (wrapped as tools)
    and can invoke them to complete complex workflows.
    """
    system_prompt = """
You are the Teacher's Assistant orchestrator that coordinates specialist agents.

You have access to three specialist agents:
1. source_selector_agent - Generates 3 Google search queries and returns top 3 results per query (9 URLs total)
2. scraper_agent - Scrapes content from provided URLs
3. vector_db_agent - Stores documents in a vector database

When given a task, think through which agents to use and in what order.
    """

    orchestrator = Agent(
        model=openai_model,
        system_prompt=system_prompt,
        tools=[source_selector_agent, scraper_agent, vector_db_agent],
        callback_handler=None
    )
    return orchestrator


async def process_user_query(query: str, user_id: str = "user123", session_id: str = "session456") -> str:
    """
    High-level workflow that uses the orchestrator to coordinate specialist agents.
    
    This implementation uses the "Agents as Tools" pattern where each specialist
    agent is wrapped as a tool and invoked by the orchestrator agent.
    """
    orchestrator = _build_orchestrator()

    print("=" * 60)
    print("MULTI-AGENT WORKFLOW STARTED")
    print("=" * 60)

    # Step 1: Source selection
    print("\n📋 Step 1: Selecting sources...")
    print(f"Query: {query}")
    tool1 = orchestrator.tool.source_selector_agent(query=query)
    
    # Extract the response - tool returns a dict with toolUseId, status, content
    sources_json = tool1.get("content", [{}])[-1].get("text", "{}")
    try:
        sources_payload = json.loads(sources_json)
    except Exception as e:
        print(f"Warning: Could not parse sources JSON: {e}")
        sources_payload = {"sources": []}
    
    print(f"✓ Found {len(sources_payload.get('sources', []))} sources from Google search")
    for i, src in enumerate(sources_payload.get("sources", [])[:6], 1):  # Show first 6
        print(f"  {i}. {src.get('title', 'No title')}")
        print(f"     URL: {src.get('url')}")
        print(f"     Query: {src.get('search_query', 'N/A')}")

    # Step 2: Scraping
    print("\n🌐 Step 2: Scraping sources...")
    tool2 = orchestrator.tool.scraper_agent(sources_json=json.dumps(sources_payload))
    
    scraped_json = tool2.get("content", [{}])[-1].get("text", "[]")
    try:
        scraped_docs = json.loads(scraped_json)
    except Exception as e:
        print(f"Warning: Could not parse scraped JSON: {e}")
        scraped_docs = []
    
    print(f"✓ Scraped {len(scraped_docs)} documents")
    for doc in scraped_docs[:2]:  # Show first 2
        print(f"  - {doc.get('source')}")
        print(f"    Preview: {doc.get('text', '')[:80]}...")

    # Step 3: Vector DB storage
    print("\n💾 Step 3: Storing in vector database...")
    tool3 = orchestrator.tool.vector_db_agent(documents_json=json.dumps(scraped_docs))
    
    store_json = tool3.get("content", [{}])[-1].get("text", "{}")
    try:
        store_result = json.loads(store_json)
    except Exception as e:
        print(f"Warning: Could not parse storage JSON: {e}")
        store_result = {"stored": 0, "ids": []}
    
    print(f"✓ Stored {store_result.get('stored', 0)} documents")
    print(f"  Document IDs: {', '.join(store_result.get('ids', [])[:5])}{'...' if len(store_result.get('ids', [])) > 5 else ''}")

    print("\n" + "=" * 60)
    print("WORKFLOW COMPLETED SUCCESSFULLY")
    print("=" * 60)

    return json.dumps(store_result, indent=2)


if __name__ == "__main__":
    async def main():
        result = await process_user_query(query="How is Liverpool FC performing in the Premier League this season?")
        print("\nFinal Result:", result)

    asyncio.run(main())