import hdbscan
from sentence_transformers import SentenceTransformer

from graph_builder import build_cluster_graph
from llm import llm


def cluster_and_summarize(ideas):
    """
    Clusters a list of ideas, generates a summary for each cluster, and returns the result in a specific format.

    Args:
        ideas (list[str]): A list of strings representing the ideas.

    Returns:
        list[dict]:
            A list of dictionaries, where each dictionary contains the summary, its embedding, and a list of the original ideas and their embeddings.
            List format:
            [
                {
                    "summary": str,
                    "embedding": list[float],
                    "ideas": [
                        {"idea": str, "embedding": list[float]},
                        ...
                    ]
                },
                ...
            ]
    """
    model = SentenceTransformer('all-MiniLM-L6-v2')
    embeddings = model.encode(ideas)

    clusterer = hdbscan.HDBSCAN(min_cluster_size=2, min_samples=1)
    clusterer.fit(embeddings)

    clustered_ideas = {}
    for i, label in enumerate(clusterer.labels_):
        if label not in clustered_ideas:
            clustered_ideas[label] = []
        clustered_ideas[label].append({"idea": ideas[i], "embedding": embeddings[i]})

    result = []
    for cluster_id, cluster_items in clustered_ideas.items():
        if cluster_id == -1:
            # Skip outliers
            continue

        concatenated_ideas = " ".join([item["idea"] for item in cluster_items])

        # Generate summary using the LLM
        prompt = f"Summarize the following ideas: {concatenated_ideas}"
        summary = llm.invoke(prompt).content

        summary_embedding = model.encode([summary])[0]

        result.append({
            "summary": summary,
            "embedding": summary_embedding,
            "ideas": cluster_items
        })

    return result


if __name__ == '__main__':
    # Example usage:
    sample_ideas = [
        "I think we should build a new feature for our app.",
        "A new feature for the app would be great.",
        "Let's add a chat function to our product.",
        "A messaging feature is what our users want.",
        "The user interface is confusing.",
        "The UI needs a complete redesign.",
        "I don't like the color scheme of the website.",
        "The website's colors are not appealing.",
        "The payment process is too complicated.",
        "Simplifying the checkout flow should be a priority.",
        "Users are complaining about the app crashing.",
        "We need to fix the bugs that are causing the crashes.",
        "The app is slow to load.",
        "We need to improve the app's performance.",
        "The login process is not intuitive.",
        "Let's make the login flow more user-friendly.",
        "I want to be able to save my favorite items.",
        "A wishlist feature would be a great addition.",
        "The search functionality is not very accurate.",
        "We should improve the search algorithm.",
        "The app drains my battery.",
        "We need to optimize the app for better battery life.",
        "The navigation bar is cluttered.",
        "Let's simplify the navigation.",
        "The app should have a dark mode.",
        "A dark mode option would be easier on the eyes.",
        "The app takes up too much storage space.",
        "We should reduce the app's size."
    ]

    clustered_data = cluster_and_summarize(sample_ideas)
    embedding_to_explanation, group_to_explanation, similarity_matrix = build_cluster_graph(clustered_data)
    breakpoint()
