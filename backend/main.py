from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sys
import os
import asyncio

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

from .graph.graph_analyser import GraphAnalyser
from .graph.graph_builder import GraphBuilder
from .scrapers import news_scraper, reddit_scraper_sub
from .synthesis.cluster import Clusterer

app = FastAPI(
    title="Influx API",
    description="Agentic trend analysis, persona-facing output, and graph debug tools",
    version="0.1.0",
)

clusterer = Clusterer()
graph_builder = GraphBuilder()
graph_analyser = GraphAnalyser()

class AskRequest(BaseModel):
    query: str

class AskResponse(BaseModel):
    answer: str

async def handle_user_query(user_query: str) -> str:
    routing = route_persona_and_task(user_query)
    persona_name = routing["persona_name"]
    persona_task = routing["persona_task"]

    initial_analysis = run_graph_rag(user_query)
    kb_size_now = len(knowledge_base)

    plan = persona_plan(persona_name, persona_task, kb_size_now, initial_analysis)

    final_analysis = initial_analysis
    kb_size_after = kb_size_now

    if plan.get("need_more_info", False):
        search_hints = plan.get("search_hints", user_query)

        sources = run_source_selector(search_hints)

        ideas = await run_scraper(sources)

        _kb_update_info = update_graph_and_kb(ideas)
        kb_size_after = len(knowledge_base)

        final_analysis = run_graph_rag(user_query)

    final_output_text = persona_deliver(
        persona_name=persona_name,
        persona_task=persona_task,
        kb_size=kb_size_after,
        analysis=final_analysis
    )

    return final_output_text

@app.post("/ask", response_model=AskResponse)
async def ask_endpoint(req: AskRequest):
    try:
        final_answer_text = await handle_user_query(req.query)
        return AskResponse(answer=final_answer_text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process-topic/{topic}")
def process_topic(topic: str):
    reddit_posts = reddit_scraper_sub.scrape_subreddit(topic, limit=10)

    news_article = news_scraper.scrape_article(
        "https://simple.wikipedia.org/wiki/Python_(programming_language)"
    )

    all_texts = [post['content'] for post in reddit_posts if post['content']]
    if news_article and news_article['content']:
        all_texts.append(news_article['content'])

    if not all_texts:
        return {"error": "Could not find any content for the given topic."}

    embeddings = clusterer.create_embeddings(all_texts)
    cluster_assignments = clusterer.cluster_embeddings(embeddings, num_clusters=3)

    clustered_data = []
    for i, text in enumerate(all_texts):
        cluster_id = f"cluster_{cluster_assignments[i]}"
        clustered_data.append({
            "text": text,
            "cluster": cluster_id
        })
        graph_builder.add_or_update_node(
            cluster_id,
            {"label": f"Topic Cluster {cluster_assignments[i]}"}
        )

    graph_builder.add_or_update_node(topic, {"label": topic})

    current_graph = graph_analyser.annotate_clusters(graph_builder, clustered_data)

    unique_clusters = set([item['cluster'] for item in clustered_data])
    for cluster_id in unique_clusters:
        graph_builder.add_edge(topic, cluster_id, "contains_data_from")

    return {
        "clustered_data": clustered_data,
        "graph": graph_builder.get_graph()
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
