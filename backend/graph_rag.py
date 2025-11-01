import os
import openai
import faiss
import numpy as np
from typing import Dict, List, Tuple, Union
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Minimal RAG module that accepts a knowledge base as a dict:
#   kb = {tuple(embedding): "summary text", ...}
# The embeddings are used directly to build a FAISS index, and the summaries are the retrieved texts.
# The public API is `rag_query(kb: Dict, query: str, top_k: int) -> (answer, contexts)`.

# Config
EMBED_MODEL = "text-embedding-3-small"

openai.api_key = os.getenv("OPENAI_API_KEY")


def embed_query(query: str, model: str = EMBED_MODEL) -> np.ndarray:
    """Embed a single query string using OpenAI embeddings."""
    from openai import OpenAI
    client = OpenAI(api_key=openai.api_key)
    resp = client.embeddings.create(input=[query], model=model)
    return np.array(resp.data[0].embedding, dtype="float32")


def build_index_from_kb(kb: Dict[Union[tuple, List], str]):
    """Build an in-memory FAISS index from a knowledge base dict where:
       - keys are embeddings (list or tuple of floats)
       - values are text summaries

    Returns (index, texts, embeddings_list)
    """
    if not kb:
        raise ValueError("Knowledge base is empty")
    
    embeddings_list = []
    texts = []
    
    for emb, text in kb.items():
        # Convert embedding to numpy array if needed
        emb_array = np.array(emb, dtype="float32")
        embeddings_list.append(emb_array)
        texts.append(text)
    
    embeddings = np.array(embeddings_list, dtype="float32")
    if embeddings.size == 0:
        raise RuntimeError("No embeddings provided")
    
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings)
    
    return index, texts, embeddings_list


def retrieve(query: str, index, texts: List[str], top_k: int = 5) -> List[dict]:
    """Retrieve top_k most similar texts from the index for the given query."""
    q_emb = embed_query(query)
    D, I = index.search(np.array([q_emb], dtype="float32"), top_k)
    results: List[dict] = []
    for idx, dist in zip(I[0], D[0]):
        if idx < 0 or idx >= len(texts):
            continue
        results.append({"text": texts[idx], "index": int(idx), "score": float(dist)})
    return results


def rag_query(kb: Dict[Union[tuple, List], str], query: str, top_k: int = 5) -> List[dict]:
    """Top-level RAG API: retrieve relevant contexts from a knowledge base for a query.
    
    This function retrieves the most similar text summaries from the KB based on semantic similarity
    to the query. The returned contexts can be passed to a Strands agent or LLM for final processing.
    
    Args:
        kb: Dict mapping embeddings (tuple/list of floats) to their corresponding text summaries.
            Example: {tuple(embedding1): "Summary 1", tuple(embedding2): "Summary 2"}
        query: User query string to search for.
        top_k: Number of most similar contexts to retrieve.
    
    Returns:
        contexts: List of retrieved context dicts, each containing:
            - "text": The text summary
            - "index": The index in the KB
            - "score": Similarity score (lower = more similar for L2 distance)
    
    Note: This builds an in-memory index on each call. For multiple queries, build the index once
    with `build_index_from_kb` and call `retrieve` directly for better performance.
    """
    if not isinstance(kb, dict):
        raise TypeError("kb must be a dict mapping embeddings->text")
    if not isinstance(query, str):
        raise TypeError("query must be a string")
    
    index, texts, embeddings_list = build_index_from_kb(kb)
    contexts = retrieve(query, index, texts, top_k=top_k)
    
    return contexts


__all__ = ["rag_query", "build_index_from_kb", "retrieve", "embed_query"]


'''
# ============================================================================
# TEST CASE
# ============================================================================

if __name__ == "__main__":
    print("Running graph_rag.py test...")
    print("-" * 80)
    
    # Test with real OpenAI embeddings if API key is available
    if os.getenv("OPENAI_API_KEY"):
        print("✓ OpenAI API key found, testing with real embeddings...")
        
        # Create sample texts with varying relevance
        texts = [
            "Python is a high-level programming language known for its readability and versatility. It's widely used in web development, data science, and automation.",
            "Machine learning is a subset of artificial intelligence that enables computers to learn from data without explicit programming.",
            "JavaScript is a programming language primarily used for web development, especially for creating interactive front-end applications.",
            "Data science combines statistics, programming, and domain expertise to extract insights from large datasets.",
            "The Python pandas library is essential for data manipulation and analysis, offering powerful data structures like DataFrames.",
            "Cloud computing provides on-demand access to computing resources over the internet, including storage and processing power.",
            "Django and Flask are popular Python web frameworks used to build scalable web applications rapidly.",
            "Neural networks are computational models inspired by the human brain, consisting of interconnected nodes that process information.",
            "The recipe for chocolate chip cookies includes flour, sugar, butter, eggs, and chocolate chips baked at 350°F.",
            "React is a JavaScript library for building user interfaces, developed and maintained by Facebook.",
            "Python's syntax emphasizes code readability with significant whitespace and allows developers to express concepts in fewer lines.",
            "Database management systems like PostgreSQL and MongoDB are crucial for storing and retrieving application data efficiently.",
            "The Great Wall of China stretches over 13,000 miles and was built over several centuries to protect against invasions.",
            "TensorFlow and PyTorch are leading deep learning frameworks that simplify building and training neural networks.",
            "Version control systems like Git help developers track changes in code and collaborate effectively on software projects."
        ]
        
        # Generate real embeddings for the KB
        from openai import OpenAI
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        kb = {}
        for text in texts:
            resp = client.embeddings.create(input=[text], model=EMBED_MODEL)
            emb = tuple(resp.data[0].embedding)
            kb[emb] = text
        
        print(f"✓ Created KB with {len(kb)} documents")
        
        # Test rag_query
        contexts = rag_query(kb, "Tell me about Python", top_k=2)
        print(f"✓ Retrieved {len(contexts)} contexts:")
        for i, ctx in enumerate(contexts, 1):
            print(f"  {i}. Score={ctx['score']:.4f}: {ctx['text'][:60]}...")
    else:
        # Fallback to mock embeddings for basic index test
        print("⚠ OPENAI_API_KEY not set, using mock embeddings for basic test...")
        kb = {
            tuple([1.0, 0.0, 0.0, 0.0, 0.0]): "Information about machine learning and AI.",
            tuple([0.0, 1.0, 0.0, 0.0, 0.0]): "Details about Python programming.",
        }
        index, texts, embeddings = build_index_from_kb(kb)
        print(f"✓ Index built: {len(texts)} documents, dimension={embeddings[0].shape[0]}")
        print("  Set OPENAI_API_KEY in .env to test full rag_query functionality")
    
    print("-" * 80)
    print("Test completed!")'''
