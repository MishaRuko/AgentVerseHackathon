# Social Trend Analyser

This project is a social trend analyser that collects information from various sources, clusters the data, builds a graph of trends, and provides an interface to query and visualize the data.

## Project Structure

The project is divided into two main parts: a `backend` built with Python and FastAPI, and a `frontend` built with Vue.js.

### Backend (`/backend`)

The backend is responsible for all the data processing, including scraping, clustering, and graph building.

- **`main.py`**: The main entry point for the FastAPI application. It defines the API endpoints and orchestrates the different backend components.

- **`/scrapers`**: This directory contains the scrapers for different data sources.
  - `reddit_scraper.py`: Scrapes posts from a given subreddit.
  - `news_scraper.py`: A generic scraper for news articles.

- **`/synthesis`**: This directory contains the logic for synthesizing and clustering the scraped data.
  - `cluster.py`: Implements text embedding and clustering using sentence transformers and scikit-learn.

- **`/graph`**: This directory contains the logic for building and analyzing the trend graph.
  - `graph_builder.py`: Defines the graph data structure and provides methods to build and update the graph.
  - `graph_analyser.py`: Analyzes the graph to extract insights, such as annotating clusters with keywords.

- **`requirements.txt`**: Lists all the Python dependencies for the backend.

### Frontend (`/frontend`)

The frontend provides a user interface to interact with the backend and visualize the data.

- **`index.html`**: The main HTML file for the Vue.js application. It includes the Mermaid.js library for graph visualization.

- **`/src`**: This directory contains the source code for the Vue.js application.
  - `App.vue`: The main Vue component that defines the UI and handles the interaction with the backend.
  - `main.js`: The entry point for the Vue.js application.

- **`package.json`**: Lists the npm dependencies for the frontend.
