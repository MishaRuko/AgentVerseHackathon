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
                    # Nodes structure matches cluster_and_summarize output
                    # Each node should have: id (index), summary, num_ideas (from ideas array length)
                    nodes = [
                        {
                            "id": 0,
                            "summary": "Technology Innovation Trends",
                            "num_ideas": 10
                        },
                        {
                            "id": 1,
                            "summary": "Climate Change Solutions",
                            "num_ideas": 25
                        },
                        {
                            "id": 2,
                            "summary": "Healthcare Advancements",
                            "num_ideas": 15
                        },
                        {
                            "id": 3,
                            "summary": "Education Reform",
                            "num_ideas": 30
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
