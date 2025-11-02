import asyncio
import websockets
import json

async def handle_client(websocket):
    print(f"Client connected from {websocket.remote_address}")
    graph_sent = False  # Track if we've sent the graph data
    try:
        async for message in websocket:
            print(f"Received message: {message}")
            if isinstance(message, str):
                message_lower = message.lower()
                # First message (or any message about social area) triggers graph display
                # After graph is displayed, subsequent messages are queries about the graph
                if not graph_sent or "social area" in message_lower:
                    # Simulate graph data response matching the structure from clustering.py and graph_builder.py
                    # Nodes structure matches cluster_and_summarize output:
                    # Each node has: summary, embedding, ideas (array of {idea: str, embedding: list[float]})
                    # The frontend will calculate num_ideas by counting ideas.length
                    nodes = [
                        {
                            "summary": "Technology Innovation Trends",
                            "embedding": [0.1] * 384,  # Dummy embedding (not used by frontend)
                            "ideas": [
                                {"idea": "AI integration in software development", "embedding": [0.1] * 384},
                                {"idea": "Cloud computing advancements", "embedding": [0.1] * 384},
                                {"idea": "Machine learning frameworks", "embedding": [0.1] * 384},
                                {"idea": "DevOps automation tools", "embedding": [0.1] * 384},
                                {"idea": "Microservices architecture", "embedding": [0.1] * 384},
                                {"idea": "Containerization technologies", "embedding": [0.1] * 384},
                                {"idea": "API-first development", "embedding": [0.1] * 384},
                                {"idea": "Serverless computing", "embedding": [0.1] * 384},
                                {"idea": "Quantum computing research", "embedding": [0.1] * 384},
                                {"idea": "Blockchain implementation", "embedding": [0.1] * 384},
                            ]
                        },
                        {
                            "summary": "Climate Change Solutions",
                            "embedding": [0.2] * 384,
                            "ideas": [
                                {"idea": "Renewable energy transition", "embedding": [0.2] * 384},
                                {"idea": "Carbon capture technologies", "embedding": [0.2] * 384},
                                {"idea": "Electric vehicle adoption", "embedding": [0.2] * 384},
                                {"idea": "Sustainable agriculture practices", "embedding": [0.2] * 384},
                                {"idea": "Green building standards", "embedding": [0.2] * 384},
                                {"idea": "Ocean cleanup initiatives", "embedding": [0.2] * 384},
                                {"idea": "Reforestation programs", "embedding": [0.2] * 384},
                                {"idea": "Climate policy implementation", "embedding": [0.2] * 384},
                                {"idea": "Energy efficiency measures", "embedding": [0.2] * 384},
                                {"idea": "Circular economy models", "embedding": [0.2] * 384},
                                {"idea": "Carbon pricing mechanisms", "embedding": [0.2] * 384},
                                {"idea": "Clean transportation systems", "embedding": [0.2] * 384},
                                {"idea": "Waste reduction strategies", "embedding": [0.2] * 384},
                                {"idea": "Renewable energy storage", "embedding": [0.2] * 384},
                                {"idea": "Sustainable water management", "embedding": [0.2] * 384},
                                {"idea": "Biodiversity conservation", "embedding": [0.2] * 384},
                                {"idea": "Climate adaptation planning", "embedding": [0.2] * 384},
                                {"idea": "Green finance initiatives", "embedding": [0.2] * 384},
                                {"idea": "Sustainable supply chains", "embedding": [0.2] * 384},
                                {"idea": "Community resilience building", "embedding": [0.2] * 384},
                                {"idea": "Carbon offset programs", "embedding": [0.2] * 384},
                                {"idea": "Eco-friendly technologies", "embedding": [0.2] * 384},
                                {"idea": "Sustainable consumption patterns", "embedding": [0.2] * 384},
                                {"idea": "Climate education programs", "embedding": [0.2] * 384},
                                {"idea": "International climate cooperation", "embedding": [0.2] * 384},
                            ]
                        },
                        {
                            "summary": "Healthcare Advancements",
                            "embedding": [0.3] * 384,
                            "ideas": [
                                {"idea": "Telemedicine expansion", "embedding": [0.3] * 384},
                                {"idea": "AI diagnostics", "embedding": [0.3] * 384},
                                {"idea": "Personalized medicine", "embedding": [0.3] * 384},
                                {"idea": "Gene therapy breakthroughs", "embedding": [0.3] * 384},
                                {"idea": "Preventive care programs", "embedding": [0.3] * 384},
                                {"idea": "Mental health support", "embedding": [0.3] * 384},
                                {"idea": "Healthcare accessibility", "embedding": [0.3] * 384},
                                {"idea": "Medical device innovation", "embedding": [0.3] * 384},
                                {"idea": "Public health surveillance", "embedding": [0.3] * 384},
                                {"idea": "Drug discovery acceleration", "embedding": [0.3] * 384},
                                {"idea": "Remote patient monitoring", "embedding": [0.3] * 384},
                                {"idea": "Healthcare data analytics", "embedding": [0.3] * 384},
                                {"idea": "Patient engagement tools", "embedding": [0.3] * 384},
                                {"idea": "Healthcare cost reduction", "embedding": [0.3] * 384},
                                {"idea": "Medical training improvements", "embedding": [0.3] * 384},
                            ]
                        },
                        {
                            "summary": "Education Reform",
                            "embedding": [0.4] * 384,
                            "ideas": [
                                {"idea": "Online learning platforms", "embedding": [0.4] * 384},
                                {"idea": "Personalized learning paths", "embedding": [0.4] * 384},
                                {"idea": "Student-centered curriculum", "embedding": [0.4] * 384},
                                {"idea": "Digital literacy programs", "embedding": [0.4] * 384},
                                {"idea": "Educational equity initiatives", "embedding": [0.4] * 384},
                                {"idea": "Teacher training programs", "embedding": [0.4] * 384},
                                {"idea": "Project-based learning", "embedding": [0.4] * 384},
                                {"idea": "STEM education emphasis", "embedding": [0.4] * 384},
                                {"idea": "Accessibility in education", "embedding": [0.4] * 384},
                                {"idea": "Education technology integration", "embedding": [0.4] * 384},
                                {"idea": "Lifelong learning opportunities", "embedding": [0.4] * 384},
                                {"idea": "Alternative assessment methods", "embedding": [0.4] * 384},
                                {"idea": "Collaborative learning spaces", "embedding": [0.4] * 384},
                                {"idea": "Critical thinking development", "embedding": [0.4] * 384},
                                {"idea": "Global education partnerships", "embedding": [0.4] * 384},
                                {"idea": "Early childhood education", "embedding": [0.4] * 384},
                                {"idea": "Vocational training programs", "embedding": [0.4] * 384},
                                {"idea": "Educational funding reform", "embedding": [0.4] * 384},
                                {"idea": "Parent engagement strategies", "embedding": [0.4] * 384},
                                {"idea": "Curriculum standardization", "embedding": [0.4] * 384},
                                {"idea": "Gamification in learning", "embedding": [0.4] * 384},
                                {"idea": "Adaptive learning systems", "embedding": [0.4] * 384},
                                {"idea": "School infrastructure improvement", "embedding": [0.4] * 384},
                                {"idea": "Student mental health support", "embedding": [0.4] * 384},
                                {"idea": "Education policy updates", "embedding": [0.4] * 384},
                                {"idea": "Multilingual education support", "embedding": [0.4] * 384},
                                {"idea": "Community school partnerships", "embedding": [0.4] * 384},
                                {"idea": "Student assessment reform", "embedding": [0.4] * 384},
                                {"idea": "Educational research integration", "embedding": [0.4] * 384},
                                {"idea": "Teacher retention strategies", "embedding": [0.4] * 384},
                            ]
                        },
                    ]
                    
                    # Similarity matrix (numpy array format when serialized)
                    # Values below threshold (0.35) are set to 0
                    # Only nodes with similarity > 0 AND in annotations should be connected
                    similarity_matrix = [
                        [1.0, 0.7, 0.2, 0.0],   # Node 0
                        [0.7, 1.0, 0.9, 0.4],   # Node 1
                        [0.2, 0.9, 1.0, 0.8],   # Node 2
                        [0.0, 0.4, 0.8, 1.0],   # Node 3
                    ]

                    # Annotations: group_to_explanation format
                    # Keys are tuples of node indices (groups of connected nodes)
                    # When JSON serialized, tuples become arrays: [0, 1]
                    # Each annotation explains why the nodes in the tuple are connected
                    # Note: JSON doesn't support tuple keys directly, so we convert to string representation
                    # The frontend can handle both "[0, 1]" format and "0-1" format
                    annotations_dict = {
                        (0, 1, 2): "Overarching theme: Technology and Climate\n\nRelated ideas:\n- Technology Innovation Trends\n- Climate Change Solutions\n\nTech solutions for environmental challenges, including renewable energy innovations, carbon capture technologies, and smart city infrastructure.",
                        (1, 2): "Overarching theme: Climate and Healthcare\n\nRelated ideas:\n- Climate Change Solutions\n- Healthcare Advancements\n\nPublic health impacts of climate change, including heat-related illnesses, vector-borne diseases, and healthcare system resilience.",
                        (2, 3): "Overarching theme: Healthcare and Education\n\nRelated ideas:\n- Healthcare Advancements\n- Education Reform\n\nMedical education and training innovations, telemedicine in schools, and health literacy programs.",
                        (1, 3): "Overarching theme: Climate and Education\n\nRelated ideas:\n- Climate Change Solutions\n- Education Reform\n\nClimate awareness in educational systems, sustainability curricula, and environmental stewardship programs.",
                    }
                    
                    # Convert tuple keys to JSON-serializable format
                    # Using array strings like "[0, 1]" which the frontend can parse
                    annotations = {}
                    for key_tuple, value in annotations_dict.items():
                        # Convert tuple to JSON string representation
                        key_str = json.dumps(list(key_tuple))
                        annotations[key_str] = value

                    response = {
                        "nodes": nodes,
                        "annotations": annotations,
                        "similarity_matrix": similarity_matrix
                    }
                    await websocket.send(json.dumps(response))
                    graph_sent = True
                    print(f"Sent graph data with {len(nodes)} nodes and {len(annotations)} annotations")
                else:
                    # Simulate chat response for queries about the graph
                    response = f"Backend received your query about the graph: '{message}'. This is a simulated response. The graph shows connections between different social trend clusters based on their similarity."
                    await websocket.send(response)
            else:
                await websocket.send("Backend received a non-string message.")
    except websockets.exceptions.ConnectionClosed:
        print(f"Client disconnected")
    except Exception as e:
        print(f"Error: {e}")

async def main():
    print("Starting WebSocket server on ws://localhost:8001")
    async with websockets.serve(handle_client, "0.0.0.0", 8001):
        await asyncio.Future()  # run forever

if __name__ == '__main__':
    asyncio.run(main())
