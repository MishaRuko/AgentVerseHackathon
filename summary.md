## Social Trend Analyser - Project Summary and Next Steps

### Work Done So Far

We have successfully set up the foundational structure of the Social Trend Analyser project, with a functional backend and a basic frontend. Here's a summary of what has been accomplished:

**Backend (Python & FastAPI):**

- **Project Scaffolding:** Created a clear directory structure for the backend, with separate modules for scraping, synthesis, and graph operations.
- **FastAPI Server:** Set up a FastAPI server (`main.py`) to handle API requests and orchestrate the backend logic.
- **Scrapers:**
  - Implemented a Reddit scraper (`reddit_scraper.py`) that fetches posts from a given subreddit using the JSON API.
  - Implemented a generic news article scraper (`news_scraper.py`) that can extract the title and content from a given URL.
- **Synthesizing Agent:**
  - Created a `Clusterer` class (`cluster.py`) that uses the `sentence-transformers` library to create text embeddings.
  - Implemented clustering using `scikit-learn`'s `KMeans` to group similar texts.
- **Graph Builder Agent:**
  - Developed a `GraphBuilder` class (`graph_builder.py`) to create and manage a graph data structure, storing it as a JSON file (`graph.json`).
- **Graph Analyser Agent:**
  - Implemented a `GraphAnalyser` class (`graph_analyser.py`) that performs basic keyword extraction (using `nltk`) to annotate the clusters in the graph.
- **API Endpoint:**
  - Created a `/process-topic/{topic}` endpoint that integrates all backend components: it scrapes data, clusters it, builds a graph, and annotates it.

**Frontend (Vue.js):**

- **Project Scaffolding:** Set up a Vue.js project in the `frontend` directory.
- **Basic UI:** Created a simple user interface in `App.vue` with:
  - An input field for the user to enter a topic.
  - A button to trigger the analysis.
  - Display areas for the clustered data and the graph.
- **Backend Integration:** The frontend is connected to the backend via an `axios` POST request to the `/process-topic` endpoint.
- **Graph Visualization Setup:** Included the Mermaid.js library in `index.html` and added the basic logic in `App.vue` to render the graph.

### Current Stopping Point

The project is at a stage where the backend is fully functional and can be tested via API calls. The frontend has a basic UI that can communicate with the backend, but the graph visualization with Mermaid.js is likely not working as expected, as reported by the user. The immediate next step would be to debug the Mermaid.js integration on the frontend.

### Division of Remaining Work (for a team of 4)

Here is a suggested division of the remaining work to complete the project:

**1. Frontend Developer:**

- **Primary Task:** Debug and fix the Mermaid.js graph visualization on the frontend.
- **Secondary Tasks:**
  - Enhance the UI/UX to make it more intuitive and visually appealing.
  - Implement more interactive ways to display the clustered data and the graph (e.g., clickable nodes, tooltips).
  - Add loading indicators and error handling for a better user experience.

**2. Backend Developer (API & Integration):**

- **Primary Task:** Improve and expand the FastAPI backend.
- **Secondary Tasks:**
  - Add more API endpoints for more granular control (e.g., endpoints to get specific clusters, to query the graph).
  - Implement proper error handling and validation for the API.
  - Work closely with the frontend developer to ensure smooth integration and data flow.
  - Consider adding a WebSocket connection for real-time updates.

**3. Data Scientist/Agent Developer (Clustering & Analysis):**

- **Primary Task:** Enhance the clustering and graph analysis algorithms.
- **Secondary Tasks:**
  - Experiment with different clustering algorithms (e.g., hierarchical clustering) and embedding models.
  - Implement more sophisticated keyword extraction and topic modeling techniques (e.g., TF-IDF, LDA).
  - Develop algorithms to identify and annotate relationships and trends between clusters.
  - Start working on the temporal analysis of trends.

**4. Data Engineer/Agent Developer (Scraping & Data):**

- **Primary Task:** Improve the data scraping and collection process.
- **Secondary Tasks:**
  - Enhance the scrapers to be more robust and handle different website structures.
  - Add more data sources (e.g., other social media platforms, news APIs).
  - Implement a more sophisticated way to find relevant news articles for a given topic (e.g., using a news API or a search engine).
  - Design and implement a more robust data storage solution for the scraped data and the graph (e.g., a database).
