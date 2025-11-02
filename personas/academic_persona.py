"""personas/academic_persona.py

Academic persona that augments LLM prompts with data fetched from Google Scholar
via the MCP server tools (see https://github.com/JackKuo666/Google-Scholar-MCP-Server).

Design goals:
- Keep the public API unchanged: `build_academic_persona_agent` and
  `make_academic_persona_tool` remain available and compatible with
  `multi_agent.py`'s usage.
- Call the Google Scholar MCP server tools directly (search_google_scholar_key_words, etc.)
  and include a short summary of those results in the persona prompt. If the search
  fails, degrade gracefully and proceed without Scholar data.
"""

import os
import json
import logging
import sys
import asyncio
from typing import List, Dict, Any, Optional
from pathlib import Path

from strands import Agent, tool
from strands.models.openai import OpenAIModel
from .prompts import ACADEMIC_PERSONA_PROMPT

logger = logging.getLogger(__name__)

# Add the Google Scholar MCP Server to the path
SCHOLAR_SERVER_PATH = Path(__file__).parent / "Google-Scholar-MCP-Server"
if SCHOLAR_SERVER_PATH.exists() and str(SCHOLAR_SERVER_PATH) not in sys.path:
    sys.path.insert(0, str(SCHOLAR_SERVER_PATH))

try:
    # Import the MCP tools directly
    from google_scholar_web_search import google_scholar_search, advanced_google_scholar_search
    SCHOLAR_AVAILABLE = True
    logger.info("Google Scholar MCP tools loaded successfully")
except ImportError as e:
    SCHOLAR_AVAILABLE = False
    logger.warning(f"Google Scholar MCP tools not available: {e}")


class GoogleScholarMCPClient:
    """Client for Google Scholar searches using MCP server tools.

    This client directly calls the MCP server tool functions:
    - google_scholar_search: Search by keywords
    - advanced_google_scholar_search: Advanced search with author and year filters
    
    Falls back gracefully if the Scholar tools are not available.
    """

    def __init__(self):
        self.available = SCHOLAR_AVAILABLE
        
        if not self.available:
            logger.warning("Google Scholar MCP tools not available. Will proceed without paper data.")
        else:
            logger.info("✅ Google Scholar MCP tools ready")

    def search_papers(self, query: str, num_results: int = 5, author: Optional[str] = None, 
                     year_range: Optional[tuple] = None) -> List[Dict[str, Any]]:
        """Search Google Scholar using MCP server tools with fallback to scraper.
        
        Tries MCP tools first, then falls back to the scraper_agent if MCP fails.
        
        Returns a list of paper dicts with keys like title, authors, year, citations, abstract, url.
        If both methods fail, returns an empty list.
        """
        papers = []
        
        # First, try MCP tools if available
        if self.available:
            # Limit to reasonable number of results
            num_results = min(num_results, 5)
            logger.info(f"Trying Google Scholar MCP tool for: '{query}' (max {num_results} results)")

            try:
                # Use the appropriate MCP tool
                if author or year_range:
                    # Use advanced search
                    raw_results = advanced_google_scholar_search(
                        query=query,
                        author=author,
                        year_range=year_range,
                        num_results=num_results
                    )
                else:
                    # Use basic keyword search
                    raw_results = google_scholar_search(
                        query=query,
                        num_results=num_results
                    )
                
                # Check if we got an error
                if isinstance(raw_results, list) and len(raw_results) > 0:
                    if isinstance(raw_results[0], dict) and 'error' not in raw_results[0]:
                        # Normalize the results from MCP tool format
                        papers = self._normalize_mcp_results(raw_results)
                        
                        if papers:
                            logger.info(f"✅ Google Scholar MCP: successfully retrieved {len(papers)} papers")
                            return papers
                
            except Exception as e:
                logger.debug(f"MCP tool error: {e}, trying fallback scraper")
        
        # Fallback to scraper_agent if MCP failed or not available
        logger.info(f"Using fallback scraper for Google Scholar search: '{query}'")
        try:
            # Import scraper_agent from backend
            scraper_path = Path(__file__).parent.parent / "backend" / "scrapers"
            if str(scraper_path) not in sys.path:
                sys.path.insert(0, str(scraper_path.parent))
            
            from scrapers import scraper_agent
            
            # Use the scholar scraper through scraper_agent
            papers = scraper_agent.scrape_source(query, "scholar")
            
            if papers:
                logger.info(f"✅ Google Scholar scraper: successfully retrieved {len(papers)} papers")
                return papers
            else:
                logger.warning(f"⚠️  Google Scholar scraper: no papers retrieved")
                
        except Exception as e:
            logger.error(f"❌ Error with fallback scraper: {e}")
        
        logger.info("Both MCP and scraper failed - persona will continue without Scholar data")
        return []
    
    def _normalize_mcp_results(self, raw_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize results from MCP tools to consistent format.
        
        The MCP tools return results with keys:
        - Title
        - Authors (string)
        - Abstract  
        - URL
        """
        papers = []
        
        for item in raw_results:
            if not isinstance(item, dict):
                continue
            
            # Skip error entries
            if 'error' in item:
                continue
            
            # Extract fields from MCP format
            title = item.get('Title', '')
            if not title or title == 'No title available':
                continue
            
            # Parse authors string (format: "Author1, Author2 - Journal, Year")
            authors_str = item.get('Authors', '')
            authors = []
            year = ''
            
            if authors_str and authors_str != 'No authors available':
                # Split by dash to separate authors from publication info
                if ' - ' in authors_str:
                    author_part, pub_part = authors_str.split(' - ', 1)
                    # Extract authors
                    authors = [a.strip() for a in author_part.split(',') if a.strip()]
                    # Try to extract year from publication part
                    import re
                    year_match = re.search(r'\b(19|20)\d{2}\b', pub_part)
                    if year_match:
                        year = year_match.group(0)
                else:
                    authors = [a.strip() for a in authors_str.split(',') if a.strip()]
            
            abstract = item.get('Abstract', '')
            if abstract == 'No abstract available':
                abstract = ''
            
            url = item.get('URL', '')
            if url == 'No link available':
                url = ''
            
            papers.append({
                'title': title,
                'authors': authors,
                'year': year,
                'citations': 0,  # MCP tools don't return citation count from web scraping
                'abstract': abstract,
                'url': url,
                'source': 'Google Scholar'
            })
        
        return papers




def build_academic_persona_agent(model: OpenAIModel) -> Agent:
    return Agent(
        model=model,
        name="Academic Research Persona",
        description="Academic researcher. Can plan research needs and deliver scholarly analysis.",
        system_prompt=ACADEMIC_PERSONA_PROMPT,
        callback_handler=None,
    )


def _summarize_scholar_results(results: List[Dict[str, Any]], max_items: int = 5) -> str:
    """Format Google Scholar results for inclusion in the persona prompt."""
    if not results:
        return "(no Google Scholar data available)"
    lines = []
    for r in results[:max_items]:
        title = r.get("title") or "(untitled)"
        authors = r.get("authors", [])
        author_str = ", ".join(authors[:3]) if isinstance(authors, list) else str(authors)
        if len(authors) > 3:
            author_str += " et al."
        year = r.get("year") or ""
        citations = r.get("citations") or 0
        abstract = r.get("abstract") or ""
        url = r.get("url") or ""
        
        paper_info = f"- **{title}**"
        if author_str:
            paper_info += f" by {author_str}"
        if year:
            paper_info += f" ({year})"
        if citations:
            paper_info += f" - {citations} citations"
        if abstract:
            # Truncate abstract to first 200 chars
            abstract_short = abstract[:200] + "..." if len(abstract) > 200 else abstract
            paper_info += f"\n  Abstract: {abstract_short}"
        if url:
            paper_info += f"\n  URL: {url}"
        
        lines.append(paper_info)
    return "\n".join(lines)


def make_academic_persona_tool(persona_agent: Agent):
    """Return a Strands tool wrapping the academic persona.

    The returned tool keeps the same signature as before so `multi_agent.py`
    can call it without modification. When generating results the tool will
    attempt to fetch related academic papers from Google Scholar MCP server 
    and include a short summary in the persona prompt.
    """

    scholar_client = GoogleScholarMCPClient()

    @tool(description="Academic research persona. mode='plan' or 'deliver'. Helps plan research and generate scholarly output.")
    def academic_persona_agent(mode: str, persona_task: str, user_query: str, kb_size: int, graph_answer_json: str) -> str:
        """
        mode: "plan" or "deliver"
        persona_task: ex. 'literature_review', 'research_landscape_scan'
        user_query: the original research question or request
        kb_size: current size of the knowledge base (int)
        graph_answer_json: stringified JSON from graph_rag containing fields:
            - answer
            - confidence
            - contexts
        returns:
          - if mode == 'plan': JSON string telling Supervisor if more info is needed
          - if mode == 'deliver': final researcher-facing output text
        """

        # Try to parse graph_answer_json if it's a JSON string
        try:
            graph_json_obj = json.loads(graph_answer_json) if isinstance(graph_answer_json, str) and graph_answer_json else graph_answer_json
        except Exception:
            graph_json_obj = None

        # Build a query for Google Scholar. Prefer using the user_query, then graph 'answer' text if present,
        # otherwise fall back to the persona task string.
        query_text = user_query
        if not query_text:
            if isinstance(graph_json_obj, dict):
                query_text = graph_json_obj.get("answer") or graph_json_obj.get("query")
        if not query_text:
            query_text = persona_task or "academic research"

        # Fetch Google Scholar results (best-effort). If the server is not available we will proceed.
        try:
            scholar_results = scholar_client.search_papers(query_text, num_results=5)
            logger.info(f"Academic persona: Retrieved {len(scholar_results)} papers from Google Scholar")
        except Exception as e:
            logger.warning(f"Error querying Google Scholar: {e}")
            scholar_results = []

        scholar_summary = _summarize_scholar_results(scholar_results, max_items=5)
        has_scholar_data = len(scholar_results) > 0

        # Compose the persona prompt, injecting Google Scholar summary and the graph snapshot.
        prompt_parts = [f"You are operating in MODE = {mode}.", ""]
        prompt_parts.append(f"Original research query: {user_query}")
        prompt_parts.append(f"persona_task: {persona_task}")
        prompt_parts.append(f"kb_size: {kb_size}")
        prompt_parts.append("")
        prompt_parts.append("Here is the current graph-based analysis snapshot:")
        prompt_parts.append(graph_answer_json if graph_answer_json else "(no graph snapshot provided)")
        prompt_parts.append("")
        prompt_parts.append("Google Scholar papers (already fetched from academic databases):")
        prompt_parts.append(scholar_summary)
        if has_scholar_data:
            prompt_parts.append("")
            prompt_parts.append(f"✅ NOTE: {len(scholar_results)} academic papers have been retrieved from Google Scholar.")
            prompt_parts.append("Since you have Google Scholar papers, you should return need_more_info: false in plan mode.")
            prompt_parts.append("DO NOT request web scraping for academic queries - use the Scholar papers provided above.")
        else:
            prompt_parts.append("")
            prompt_parts.append("⚠️ NOTE: No Google Scholar papers were retrieved (API may be rate-limited or unavailable).")
            prompt_parts.append("If you need more academic sources in MODE \"plan\", include 'site:scholar.google.com' in your search_hints.")
            prompt_parts.append("Example: 'large language models site:scholar.google.com' or 'transformer architecture site:scholar.google.com'")
        prompt_parts.append("")
        prompt_parts.append("Follow the MODE rules from your system prompt.")
        prompt_parts.append("When generating search_hints in MODE \"plan\", ensure they are specific to the user's research query: \"" + user_query + "\".")
        prompt_parts.append("When responding in MODE \"deliver\", tailor your response to address the user's research query: \"" + user_query + "\".")
        prompt_parts.append("If MODE is \"plan\", respond with a pure JSON object as a string.")
        prompt_parts.append("If MODE is \"deliver\", respond with final researcher-facing narrative (no JSON).")

        prompt = "\n".join(prompt_parts)

        # Call the persona agent and return the string result
        try:
            resp = persona_agent(prompt)
            result = str(resp).strip()
            
            # Log and potentially modify the plan result
            if mode == "plan":
                try:
                    plan_obj = json.loads(result)
                    original_need_more = plan_obj.get('need_more_info')
                    logger.info(f"Academic persona plan: need_more_info={original_need_more}, has_scholar_data={has_scholar_data}")
                    
                    # If requesting more info, ensure search hints target Google Scholar
                    if original_need_more and 'search_hints' in plan_obj:
                        hints = plan_obj['search_hints']
                        # Force site:scholar.google.com if not already present
                        if 'site:scholar.google.com' not in hints and 'scholar.google.com' not in hints:
                            plan_obj['search_hints'] = f"{hints} site:scholar.google.com"
                            result = json.dumps(plan_obj)
                            logger.info(f"Academic persona: Added site:scholar.google.com to search hints: {plan_obj['search_hints']}")
                except Exception as e:
                    logger.warning(f"Failed to parse/modify plan JSON: {e}")
            
            return result
        except Exception as e:
            logger.exception("Academic persona agent call failed: %s", e)
            # Fallback: return a plan requesting Scholar sources
            if mode == "plan":
                logger.warning("Academic persona fallback: requesting Scholar sources")
                fallback = json.dumps({
                    "need_more_info": True, 
                    "persona_task": persona_task,
                    "search_hints": f"{user_query} site:scholar.google.com"
                })
                return fallback
            return "Academic persona failed to produce a response."

    return academic_persona_agent
