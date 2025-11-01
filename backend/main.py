from fastapi import FastAPI

from .graph.graph_analyser import GraphAnalyser
from .graph.graph_builder import GraphBuilder
from .scrapers import news_scraper, reddit_scraper
from .synthesis.cluster import Clusterer

app = FastAPI()

clusterer = Clusterer()
graph_builder = GraphBuilder()
graph_analyser = GraphAnalyser()


@app.post("/process-topic/{topic}")
def process_topic(topic: str):
    """
    Scrapes Reddit and news for a given topic, clusters the content,
    builds a graph, analyzes it, and returns the clustered data and graph.
    """
    # Scrape Reddit
    reddit_posts = reddit_scraper.scrape_subreddit(topic, limit=10)

    # Scrape News (using a placeholder for now)
    news_article = news_scraper.scrape_article('https://simple.wikipedia.org/wiki/Python_(programming_language)')

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
        graph_builder.add_or_update_node(cluster_id, {"label": f"Topic Cluster {cluster_assignments[i]}"})

    # Add a node for the main topic
    graph_builder.add_or_update_node(topic, {"label": topic})

    # Annotate clusters with keywords
    current_graph = graph_analyser.annotate_clusters(graph_builder, clustered_data)

    # Add edges from the topic to each cluster (if not already added in annotate_clusters, which it isn't)
    unique_clusters = set([item['cluster'] for item in clustered_data])
    for cluster_id in unique_clusters:
        graph_builder.add_edge(topic, cluster_id, "contains_data_from")

    return {"clustered_data": clustered_data, "graph": graph_builder.get_graph()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

