from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sys
import os
import asyncio
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CURRENT_DIR)
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from multi_agent import (
    knowledge_base,
    route_persona_and_task,
    run_graph_rag,
    persona_plan,
    run_source_selector,
    run_scraper,
    update_graph_and_kb,
    persona_deliver,
)

app = FastAPI(
    title="Influx API",
    description="Agentic trend analysis, persona-facing output, and graph debug tools",
    version="0.1.0",
)

class AskRequest(BaseModel):
    query: str

class AskResponse(BaseModel):
    answer: str

async def handle_user_query(user_query: str) -> str:
    logger.info(f"{'='*80}")
    logger.info(f"🔍 NEW QUERY: {user_query}")
    logger.info(f"{'='*80}")
    
    # Step 1: Route to persona
    logger.info("📍 STEP 1: Routing query to appropriate persona...")
    routing = route_persona_and_task(user_query)
    persona_name = routing["persona_name"]
    persona_task = routing["persona_task"]
    logger.info(f"✅ Routed to: {persona_name.upper()} persona")
    logger.info(f"   Task: {persona_task}")

    # Step 2: Initial RAG query
    logger.info(f"\n📚 STEP 2: Querying knowledge base (current size: {len(knowledge_base)} entries)...")
    initial_analysis = run_graph_rag(user_query)
    kb_size_now = len(knowledge_base)
    logger.info(f"✅ Retrieved {len(initial_analysis.get('contexts', []))} contexts")
    logger.info(f"   Confidence: {initial_analysis.get('confidence', 'unknown')}")

    # Step 3: Plan next actions
    logger.info(f"\n🎯 STEP 3: Planning next actions...")
    plan = persona_plan(persona_name, persona_task, kb_size_now, initial_analysis)
    need_more_info = plan.get("need_more_info", False)
    logger.info(f"✅ Plan generated. Need more info: {need_more_info}")
    
    final_analysis = initial_analysis
    kb_size_after = kb_size_now

    if need_more_info:
        search_hints = plan.get("search_hints", user_query)
        logger.info(f"   Search hints: {search_hints}")

        # Allow up to 3 scraping rounds if data is insufficient
        max_scraping_rounds = 3
        scraping_round = 0
        needs_more_data = True
        
        while needs_more_data and scraping_round < max_scraping_rounds:
            scraping_round += 1
            round_prefix = f" (Round {scraping_round}/{max_scraping_rounds})" if max_scraping_rounds > 1 else ""
            
            # Step 4: Source selection
            logger.info(f"\n🔎 STEP 4{round_prefix}: Selecting sources to scrape...")
            
            # Modify search hints for subsequent rounds to get more diverse results
            if scraping_round > 1:
                search_hints_varied = f"{search_hints} alternative perspectives trends insights round {scraping_round}"
                logger.info(f"   Using varied search for round {scraping_round}")
            else:
                search_hints_varied = search_hints
                
            sources = run_source_selector(search_hints_varied)
            num_sources = len(sources.get("sources", []))
            logger.info(f"✅ Selected {num_sources} sources")
            
            # Log source types
            source_types = {}
            for src in sources.get("sources", []):
                src_type = src.get("type", "unknown")
                source_types[src_type] = source_types.get(src_type, 0) + 1
            logger.info(f"   Source breakdown: {source_types}")

            # Step 5: Scraping
            logger.info(f"\n🌐 STEP 5{round_prefix}: Scraping sources...")
            ideas = await run_scraper(sources)
            num_ideas = len(ideas.get("ideas", []))
            logger.info(f"✅ Extracted {num_ideas} ideas from sources")

            # Step 6: Update knowledge base
            logger.info(f"\n🧠 STEP 6{round_prefix}: Updating knowledge base...")
            logger.info(f"   KB size before: {len(knowledge_base)}")
            _kb_update_info = update_graph_and_kb(ideas)
            kb_size_after = len(knowledge_base)
            clusters_added = _kb_update_info.get("clusters_added", 0)
            logger.info(f"✅ KB updated. Size after: {kb_size_after} (+{kb_size_after - kb_size_now})")
            logger.info(f"   Clusters added: {clusters_added}")
            logger.info(f"   Status: {_kb_update_info.get('status', 'unknown')}")
            
            # Check if we need more data
            needs_more_data = _kb_update_info.get("needs_more_data", False)
            
            if needs_more_data and scraping_round < max_scraping_rounds:
                logger.warning(f"   🔄 Clusters too dissimilar. Starting round {scraping_round + 1} to gather more diverse data...")
            elif needs_more_data:
                logger.warning(f"   ⚠️  Max scraping rounds reached. Proceeding with available data.")
            else:
                logger.info(f"   ✅ Sufficient data quality achieved")

        # Step 7: Re-query with new knowledge
        logger.info(f"\n🔄 STEP 7: Re-querying knowledge base with new information...")
        final_analysis = run_graph_rag(user_query)
        logger.info(f"✅ Retrieved {len(final_analysis.get('contexts', []))} contexts")
        logger.info(f"   Confidence: {final_analysis.get('confidence', 'unknown')}")
    else:
        logger.info(f"   ⏭️  Skipping scraping - sufficient knowledge available")

    # Step 8: Generate final output
    logger.info(f"\n📝 STEP 8: Generating final {persona_name} persona response...")
    final_output_text = persona_deliver(
        persona_name=persona_name,
        persona_task=persona_task,
        kb_size=kb_size_after,
        analysis=final_analysis
    )
    
    output_preview = final_output_text[:200] + "..." if len(final_output_text) > 200 else final_output_text
    logger.info(f"✅ Response generated ({len(final_output_text)} chars)")
    logger.info(f"   Preview: {output_preview}")
    logger.info(f"\n{'='*80}")
    logger.info(f"✨ QUERY COMPLETE")
    logger.info(f"{'='*80}\n")

    return final_output_text

@app.post("/ask", response_model=AskResponse)
async def ask_endpoint(req: AskRequest):
    try:
        logger.info(f"\n🚀 API REQUEST received at /ask")
        final_answer_text = await handle_user_query(req.query)
        logger.info(f"✅ API RESPONSE ready (200 OK)")
        return AskResponse(answer=final_answer_text)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"\n{'='*80}\n❌ ERROR in /ask endpoint:\n{error_trace}{'='*80}\n")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
