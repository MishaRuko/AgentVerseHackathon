
import json

class GraphBuilder:
    def __init__(self, graph_file="graph.json"):
        """
        Initializes the GraphBuilder. Loads an existing graph if available,
        otherwise starts with an empty graph.

        Args:
            graph_file: The file path to store/load the graph.
        """
        self.graph_file = graph_file
        self.graph = self._load_graph()

    def _load_graph(self):
        """
        Loads the graph from a JSON file.
        """
        try:
            with open(self.graph_file, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {"nodes": {}, "edges": []}

    def _save_graph(self):
        """
        Saves the current graph to a JSON file.
        """
        with open(self.graph_file, 'w') as f:
            json.dump(self.graph, f, indent=4)

    def add_or_update_node(self, node_id: str, attributes: dict = None):
        """
        Adds a new node or updates an existing node's attributes.
        """
        if node_id not in self.graph["nodes"]:
            self.graph["nodes"][node_id] = {"id": node_id, "attributes": {}}
        if attributes:
            self.graph["nodes"][node_id]["attributes"].update(attributes)
        self._save_graph()

    def add_edge(self, source_node_id: str, target_node_id: str, relationship: str, weight: float = 1.0):
        """
        Adds an edge between two nodes.
        """
        # Ensure both nodes exist before adding an edge
        if source_node_id not in self.graph["nodes"]:
            self.add_or_update_node(source_node_id)
        if target_node_id not in self.graph["nodes"]:
            self.add_or_update_node(target_node_id)

        edge = {
            "source": source_node_id,
            "target": target_node_id,
            "relationship": relationship,
            "weight": weight
        }
        self.graph["edges"].append(edge)
        self._save_graph()

    def get_graph(self):
        """
        Returns the current graph.
        """
        return self.graph

if __name__ == '__main__':
    # Example usage:
    graph_builder = GraphBuilder(graph_file="test_graph.json")

    # Add some nodes (clusters)
    graph_builder.add_or_update_node("cluster_0", {"label": "Python Programming"})
    graph_builder.add_or_update_node("cluster_1", {"label": "Software Development"})
    graph_builder.add_or_update_node("cluster_2", {"label": "Daily Life"})

    # Add some edges (relationships)
    graph_builder.add_edge("cluster_0", "cluster_1", "related_to", 0.8)
    graph_builder.add_edge("cluster_1", "cluster_2", "influences", 0.3)

    print("Current Graph:")
    print(json.dumps(graph_builder.get_graph(), indent=4))

    # Clean up test file
    import os
    if os.path.exists("test_graph.json"):
        os.remove("test_graph.json")
