from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
import sys
import os
import asyncio
import logging
import json
import numpy as np

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

# Helper for sending progress updates to the frontend
async def _send_progress(websocket: WebSocket | None, message: str, stage: str = "progress"):
    if websocket is None:
        return
    payload = {"type": stage, "message": message}
    try:
        await websocket.send_json(payload)
        logger.info(f"📤 Sent progress: {message}")
    except Exception as e:
        logger.error(f"Failed to send progress: {e}")
        return
    

# Helper function to convert numpy arrays to lists recursively
def convert_numpy_to_list(obj):
    """Recursively convert numpy arrays to Python lists for JSON serialization."""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, dict):
        return {key: convert_numpy_to_list(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_to_list(item) for item in obj]
    elif isinstance(obj, tuple):
        return tuple(convert_numpy_to_list(item) for item in obj)
    else:
        return obj

# Helper for sending graph data to the frontend
async def _send_graph_data(websocket: WebSocket | None, graph_data: dict):
    if websocket is None:
        return
    try:
        # Convert any numpy arrays to lists for JSON serialization
        graph_data_serializable = convert_numpy_to_list(graph_data)
        await websocket.send_text(json.dumps(graph_data_serializable))
        logger.info(f"📤 Sent graph data with {len(graph_data.get('nodes', []))} nodes")
    except Exception as e:
        logger.error(f"Failed to send graph data: {e}")
        return

async def handle_user_query(user_query: str, websocket: WebSocket | None = None) -> str:
    logger.info(f"{'='*80}")
    logger.info(f"🔍 NEW QUERY: {user_query}")
    logger.info(f"{'='*80}")
    
    # Step 1: Route to persona
    await _send_progress(websocket, "Routing query to appropriate persona...", "progress")
    logger.info("🎯 STEP 1: Routing query to appropriate persona...")
    routing = route_persona_and_task(user_query)
    persona_name = routing["persona_name"]
    persona_task = routing["persona_task"]
    logger.info(f"✅ Routed to: {persona_name.upper()} persona")
    logger.info(f"   Task: {persona_task}")

    # Step 2: Initial RAG query
    await _send_progress(websocket, f"Querying knowledge base ({len(knowledge_base)} entries)...", "progress")
    logger.info(f"\n📚 STEP 2: Querying knowledge base (current size: {len(knowledge_base)} entries)...")
    initial_analysis = run_graph_rag(user_query)
    kb_size_now = len(knowledge_base)
    logger.info(f"✅ Retrieved {len(initial_analysis.get('contexts', []))} contexts")
    logger.info(f"   Confidence: {initial_analysis.get('confidence', 'unknown')}")

    # Step 3: Plan next actions
    await _send_progress(websocket, "Planning next actions...", "progress")
    logger.info(f"\n🎯 STEP 3: Planning next actions...")
    plan = persona_plan(persona_name, persona_task, user_query, kb_size_now, initial_analysis)
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
            await _send_progress(websocket, f"Selecting sources to scrape{round_prefix}...", "progress")
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
            await _send_progress(websocket, f"Scraping {num_sources} sources{round_prefix}...", "progress")
            logger.info(f"\n🌐 STEP 5{round_prefix}: Scraping sources...")
            ideas = await run_scraper(sources)
            num_ideas = len(ideas.get("ideas", []))
            logger.info(f"✅ Extracted {num_ideas} ideas from sources")

            # Step 6: Update knowledge base
            await _send_progress(websocket, f"Updating knowledge base{round_prefix}...", "progress")
            logger.info(f"\n🧠 STEP 6{round_prefix}: Updating knowledge base...")
            logger.info(f"   KB size before: {len(knowledge_base)}")

            # frontend [0] = nodes; frontend[1] = group_to_explanation; frontend_info[2] = _sim matrix
            _kb_update_info, frontend_info = update_graph_and_kb(ideas) 
            kb_size_after = len(knowledge_base)
            clusters_added = _kb_update_info.get("clusters_added", 0)
            logger.info(f"✅ KB updated. Size after: {kb_size_after} (+{kb_size_after - kb_size_now})")
            logger.info(f"   Clusters added: {clusters_added}")
            logger.info(f"   Status: {_kb_update_info.get('status', 'unknown')}")

            # Extract data for frontend
            annotations = {}
            for key_tuple, value in frontend_info[1].items():
                # Convert tuple to JSON string representation
                key_str = json.dumps(list(key_tuple))
                annotations[key_str] = value
            
            response_graph = {
                "nodes": frontend_info[0],
                "annotations": annotations,
                "similarity_matrix": frontend_info[2]
            }
            
            # Send graph data to frontend
            logger.info(f"📤 Sending graph data to frontend with {len(response_graph['nodes'])} nodes")
            await _send_graph_data(websocket, response_graph)
            
            # Check if we need more data
            needs_more_data = _kb_update_info.get("needs_more_data", False)
            
            if needs_more_data and scraping_round < max_scraping_rounds:
                logger.warning(f"   🔄 Clusters too dissimilar. Starting round {scraping_round + 1} to gather more diverse data...")
                await _send_progress(websocket, f"Need more diverse data, starting round {scraping_round + 1}...", "progress")
            elif needs_more_data:
                logger.warning(f"   ⚠️ Max scraping rounds reached. Proceeding with available data.")
                await _send_progress(websocket, "Max rounds reached, proceeding with available data...", "progress")
            else:
                logger.info(f"   ✅ Sufficient data quality achieved")
                await _send_progress(websocket, "Sufficient data quality achieved!", "progress")

        # Step 7: Re-query with new knowledge
        await _send_progress(websocket, "Re-querying knowledge base with new information...", "progress")
        logger.info(f"\n🔄 STEP 7: Re-querying knowledge base with new information...")
        final_analysis = run_graph_rag(user_query)
        logger.info(f"✅ Retrieved {len(final_analysis.get('contexts', []))} contexts")
        logger.info(f"   Confidence: {final_analysis.get('confidence', 'unknown')}")
    else:
        logger.info(f"   ⭐️ Skipping scraping - sufficient knowledge available")
        await _send_progress(websocket, "Sufficient knowledge available, generating response...", "progress")

    # Step 8: Generate final output
    await _send_progress(websocket, f"Generating final {persona_name} persona response...", "progress")
    logger.info(f"\n📝 STEP 8: Generating final {persona_name} persona response...")
    final_output_text = persona_deliver(
        persona_name=persona_name,
        persona_task=persona_task,
        user_query=user_query,
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
        final_answer_text = await handle_user_query(req.query, websocket=None)
        logger.info(f"✅ API RESPONSE ready (200 OK)")
        return AskResponse(answer=final_answer_text)
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        logger.error(f"\n{'='*80}\n❌ ERROR in /ask endpoint:\n{error_trace}{'='*80}\n")
        raise HTTPException(status_code=500, detail=str(e))

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint that handles queries and sends graph updates.
    Expects text messages (queries) from client.
    Sends back:
        - Progress messages as text
        - Graph data as JSON
        - Final result as text
    """
    await websocket.accept()
    logger.info("✅ WebSocket connection accepted")
    
    try:
        while True:
            try:
                # Receive message from client
                logger.info("⏳ Waiting for message from client...")
                message = await websocket.receive_text()
                logger.info(f"📨 Received message: {message}")
                
                if not message or not message.strip():
                    await websocket.send_text("Empty message received")
                    continue
                
                # Process the query
                try:
                    await _send_progress(websocket, "Query received, processing...", "progress")
                    final_answer = await handle_user_query(message, websocket)
                    
                    # Send final result
                    await websocket.send_text(final_answer)
                    logger.info(f"✅ Sent final answer ({len(final_answer)} chars)")
                    
                except Exception as e:
                    error_msg = f"Error processing query: {str(e)}"
                    logger.error(f"❌ {error_msg}")
                    await websocket.send_text(error_msg)
                    
            except WebSocketDisconnect:
                logger.info("Client disconnected")
                break
            except Exception as e:
                logger.error(f"❌ Error receiving message: {e}")
                try:
                    await websocket.send_text(f"Error: {str(e)}")
                except:
                    pass
                break
                
    except Exception as e:
        logger.error(f"❌ WebSocket error: {e}")
        try:
            await websocket.send_text(f"Connection error: {str(e)}")
        except:
            pass

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)