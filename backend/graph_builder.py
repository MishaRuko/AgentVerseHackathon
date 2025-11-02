import os

import cdlib.algorithms
import networkx as nx
import numpy as np
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from strands import Agent
from strands.models.openai import OpenAIModel

load_dotenv()

openai_model = OpenAIModel(model_id="gpt-3.5-turbo")

agent = Agent(model=openai_model, tools=[], system_prompt="You are a helpful assistant that only generates text. You do not have access to any tools.")


def build_cluster_graph(clustered_data):
    """
    Builds a graph of clusters, finds communities using link clustering, and generates explanations for cluster groups.

    Args:
        clustered_data (list[dict]):
            Output from cluster_and_summarize. Output format documented in clustering.py.

    Returns:
        dict: A dictionary mapping combined embedding to long description for each cluster group.
    """
    model = SentenceTransformer('all-MiniLM-L6-v2')

    cluster_embeddings = [item["embedding"] for item in clustered_data]
    cluster_summaries = [item["summary"] for item in clustered_data]

    # 1. Build a cosine similarity matrix for the cluster embeddings.
    similarity_matrix = cosine_similarity(cluster_embeddings)

    # Force cosine similarities below a certain threshold to 0 for more meaningful connections
    meaningful_similarity_threshold = 0.4  # This value can be tuned
    similarity_matrix[similarity_matrix < meaningful_similarity_threshold] = 0

    # 2. Create a NetworkX graph from the similarity matrix
    G = nx.Graph()
    for i in range(len(clustered_data)):
        G.add_node(i, summary=cluster_summaries[i])

    # Add edges based on similarity
    for i in range(len(clustered_data)):
        for j in range(i + 1, len(clustered_data)):
            if similarity_matrix[i, j] > 0:  # Only add edges if similarity is greater than 0 after thresholding
                G.add_edge(i, j, weight=similarity_matrix[i, j])

    # 3. Find communities using link clustering
    communities = cdlib.algorithms.hierarchical_link_community(G)

    # Extract node communities from edge communities
    cluster_groups = []
    for edge_community in communities.communities:
        node_community = set()
        for edge in edge_community:
            node_community.add(edge[0])
            node_community.add(edge[1])
        cluster_groups.append(list(node_community))

    final_results = {}
    for group_nodes in cluster_groups:  # Iterate over the communities
        if len(group_nodes) <= 1:
            continue

        group_summaries = [G.nodes[node]['summary'] for node in group_nodes]

        # 4. For each cluster group, use an LLM to generate an explanation
        llm_prompt = f"""The following are summaries of related ideas:
{'- ' + '\n- '.join(group_summaries)}

Explain concisely and succinctly why these ideas are related and provide a brief overarching theme or connection. Do not ramble. The more ideas there are, the more broad/general you should try to make your explanation."""

        group_explanation = agent(llm_prompt)

        # 5. Combine, embed, and add to results
        combined_description = f"Overarching theme: {group_explanation}\n\nRelated ideas:\n{'- ' + '\n- '.join(group_summaries)}"
        combined_embedding = model.encode([combined_description])[0]

        final_results[tuple(combined_embedding.tolist())] = combined_description

    # Add individual clusters to the final result
    for i, item in enumerate(clustered_data):
        final_results[tuple(item["embedding"].tolist())] = item["summary"]

    return final_results
