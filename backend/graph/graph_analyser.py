
import nltk
from nltk.corpus import stopwords
from collections import Counter
import re
import json
import os
import sys

class GraphAnalyser:
    def __init__(self):
        # Ensure stopwords are downloaded
        try:
            stopwords.words('english')
        except LookupError:
            nltk.download('stopwords')
        self.stop_words = set(stopwords.words('english'))

    def _extract_keywords(self, texts: list[str], num_keywords: int = 5) -> list[str]:
        """
        Extracts keywords from a list of texts.
        """
        all_words = []
        for text in texts:
            # Remove punctuation and convert to lowercase
            text = re.sub(r'[^a-zA-Z\s]', '', text).lower()
            words = text.split()
            all_words.extend([word for word in words if word not in self.stop_words and len(word) > 2])
        
        word_counts = Counter(all_words)
        return [word for word, count in word_counts.most_common(num_keywords)]

    def annotate_clusters(self, graph_builder, clustered_data):
        """
        Annotates clusters in the graph with keywords.

        Args:
            graph_builder: An instance of GraphBuilder.
            clustered_data: The output from the Clusterer, a list of dicts with 'text' and 'cluster'.
        """
        clusters_texts = {}
        for item in clustered_data:
            cluster_id = item['cluster']
            if cluster_id not in clusters_texts:
                clusters_texts[cluster_id] = []
            clusters_texts[cluster_id].append(item['text'])

        for cluster_id, texts in clusters_texts.items():
            keywords = self._extract_keywords(texts)
            graph_builder.add_or_update_node(cluster_id, {"keywords": keywords})

        return graph_builder.get_graph()

if __name__ == '__main__':
    # For testing purposes, add the parent directory to sys.path
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from graph.graph_builder import GraphBuilder

    analyser = GraphAnalyser()
    graph_builder = GraphBuilder(graph_file="test_graph_analyser.json")

    clustered_data = [
        {"text": "Python is a programming language. I love Python.", "cluster": "cluster_0"},
        {"text": "I enjoy cooking. Baking is also fun.", "cluster": "cluster_1"},
        {"text": "Python development is interesting. New features in Python.", "cluster": "cluster_0"},
        {"text": "I like to bake cakes and cookies.", "cluster": "cluster_1"},
        {"text": "Machine learning with Python is powerful.", "cluster": "cluster_0"},
    ]

    updated_graph = analyser.annotate_clusters(graph_builder, clustered_data)
    print("Annotated Graph:")
    print(json.dumps(updated_graph, indent=4))

    # Clean up test file
    if os.path.exists("test_graph_analyser.json"):
        os.remove("test_graph_analyser.json")
