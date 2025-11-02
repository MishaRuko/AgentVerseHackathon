import json
import asyncio
from multi_agent import (
    _build_orchestrator,
    source_selector_agent,
    scraper_agent,
    graph_rag_agent
)
from backend.clustering import cluster_and_summarize

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
        # print(f"  {i}. {src.get('title', 'No title')}")
        print(f"     URL: {src.get('url')}")
        # print(f"     Query: {src.get('search_query', 'N/A')}")

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
        # print(f"  - {doc.get('source')}")
        # print(f"    Preview: {doc.get('text', '')[:80]}...")
        print(doc)

    # Cluster the list 
    clustered_data = cluster_and_summarize(scraped_docs)

    return json.dumps(clustered_data, indent=2)


if __name__ == "__main__":
    async def main():
        result = await process_user_query(query="How is Liverpool FC performing in the Premier League this season?")
        print("\nFinal Result:", result)

    asyncio.run(main())