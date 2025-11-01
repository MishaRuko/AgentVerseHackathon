
from sentence_transformers import SentenceTransformer
import numpy as np
import hdbscan

class Clusterer:
    def __init__(self, model_name='all-MiniLM-L6-v2'):
        """
        Initializes the Clusterer with a sentence transformer model.

        Args:
            model_name: The name of the sentence transformer model to use.
        """
        self.model = SentenceTransformer(model_name)

    def create_embeddings(self, texts):
        """
        Creates vector embeddings for a list of texts.

        Args:
            texts: A list of strings to be encoded.

        Returns:
            A numpy array of vector embeddings.
        """
        return self.model.encode(texts)

    def cluster_embeddings(self, embeddings):
        """
        Clusters a set of embeddings using HDBSCAN clustering.

        Args:
            embeddings: A numpy array of vector embeddings.

        Returns:
            A list of cluster assignments for each embedding.
        """
        clusterer = hdbscan.HDBSCAN(min_cluster_size=2, gen_min_span_tree=True)
        clusterer.fit(embeddings)
        return clusterer.labels_.tolist()

if __name__ == '__main__':
    # Example usage:
    clusterer = Clusterer()
    texts = [
        "This is a sentence about Python.",
        "I love programming in Python.",
        "Java is another popular programming language.",
        "I enjoy cooking and baking.",
        "Baking is a fun hobby.",
        "The new Python version has cool features.",
        "I am learning to code in my spare time.",
        "Cooking is a great way to relax.",
        "I am a software engineer.",
        "I like to read books about technology.",
        "My favorite food is pizza.",
        "I am going to the gym tomorrow.",
        "I am excited to learn about clustering.",
        "This is a test sentence.",
        "I am writing a blog post about my project.",
        "The weather is nice today.",
        "I am going for a walk in the park.",
        "I am listening to music.",
        "I am watching a movie.",
        "I am playing a video game.",
        "I am reading a book.",
        "I am studying for an exam.",
        "I am working on a new project.",
        "I am learning a new language.",
        "I am traveling to a new country.",
        "I am meeting new people.",
        "I am trying new things.",
        "I am having fun.",
        "I am happy.",
        "I am sad.",
        "I am angry.",
        "I am tired.",
        "I am hungry.",
        "I am thirsty.",
        "I am sleepy.",
        "I am awake.",
        "I am alive.",
        "I am human.",
        "I am a robot.",
        "I am a computer.",
        "I am a program.",
        "I am an AI.",
    ]
    embeddings = clusterer.create_embeddings(texts)
    
    cluster_assignments = clusterer.cluster_embeddings(embeddings)
    
    for text, cluster in zip(texts, cluster_assignments):
        print(f'Text: "{text}" -> Cluster: {cluster}')
