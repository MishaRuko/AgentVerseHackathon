from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sys
import os
import asyncio

# -------------------------------------------------
# make sure we can import multi_agent.py from repo root
# -------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(CURRENT_DIR)
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from multi_agent import handle_user_query  # orchestrator loop

# existing imports for the legacy pipeline
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

# -------------------------------------------------
# request / response models for /ask
# -------------------------------------------------

class AskRequest(BaseModel):
    query: str

class AskResponse(BaseModel):
    answer: str

# -------------------------------------------------
# NEW ENDPOINT: /ask
# -------------------------------------------------

@app.post("/ask", response_model=AskResponse)
async def ask_endpoint(req: AskRequest):
    """
    High-level entrypoint for the full agentic workflow.

    What happens inside handle_user_query():
    1. Route to persona (marketing vs finance) and pick persona_task.
    2. Run graph_rag on current knowledge_base.
    3. Ask persona in 'plan' mode if KB is enough and get:
          { need_more_info: bool, search_hints?: str }
    4. If need_more_info == True:
          source_selector -> scraper -> graph_builder to enrich KB,
          then rerun graph_rag.
    5. Ask persona in 'deliver' mode to generate stakeholder-facing answer.
    6. Return that text.
    """
    try:
        final_answer_text = await handle_user_query(req.query)
        return AskResponse(answer=final_answer_text)
    except Exception as e:
        # we bubble errors to client as 500
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------------------------------
# EXISTING ENDPOINT: /process-topic/{topic}
# -------------------------------------------------

@app.post("/process-topic/{topic}")
def process_topic(topic: str):
    """
    Scrapes Reddit and news for a given topic, clusters the content,
    builds a graph, analyzes it, and returns the clustered data and graph.

    This is the older direct pipeline. It does not integrate with
    the persona routing / KB enrichment loop.
    """
    # Scrape Reddit
    reddit_posts = reddit_scraper_sub.scrape_subreddit(topic, limit=10)

    # Scrape News (using a placeholder for now)
    news_article = news_scraper.scrape_article(
        "https://simple.wikipedia.org/wiki/Python_(programming_language)"
    )

    # Combine the scraped text
    all_texts = [post['content'] for post in reddit_posts if post['content']]
    if news_article and news_article['content']:
        all_texts.append(news_article['content'])

    if not all_texts:
        return {"error": "Could not find any content for the given topic."}

    # Create embeddings and cluster the text
    embeddings = clusterer.create_embeddings(all_texts)
    cluster_assignments = clusterer.cluster_embeddings(embeddings, num_clusters=3)

    # Prepare the response and build the graph
    clustered_data = []
    for i, text in enumerate(all_texts):
        cluster_id = f"cluster_{cluster_assignments[i]}"
        clustered_data.append({
            "text": text,
            "cluster": cluster_id
        })
        # Add cluster as a node initially without keywords
        graph_builder.add_or_update_node(
            cluster_id,
            {"label": f"Topic Cluster {cluster_assignments[i]}"}
        )

    # Add a node for the main topic
    graph_builder.add_or_update_node(topic, {"label": topic})

    # Annotate clusters with keywords
    current_graph = graph_analyser.annotate_clusters(graph_builder, clustered_data)

    # Add edges from the topic to each cluster (if not already added in annotate_clusters, which it isn't)
    unique_clusters = set([item['cluster'] for item in clustered_data])
    for cluster_id in unique_clusters:
        graph_builder.add_edge(topic, cluster_id, "contains_data_from")

    return {
        "clustered_data": clustered_data,
        "graph": graph_builder.get_graph()
    }

# -------------------------------------------------
# local dev runner
# -------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
