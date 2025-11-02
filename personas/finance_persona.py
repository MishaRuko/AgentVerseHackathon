"""personas/finance_persona.py

Finance persona that augments LLM prompts with data fetched from an external
MCP server (see MCP server at https://github.com/financial-datasets/mcp-server).

Design goals:
- Keep the public API unchanged: `build_finance_persona_agent` and
  `make_finance_persona_tool` remain available and compatible with
  `multi_agent.py`'s usage.
- When available, query the MCP server for relevant financial datasets and
  include a short summary of those results in the persona prompt. If the MCP
  server is unreachable, degrade gracefully and proceed without MCP data.
"""

import os
import json
import logging
from typing import List, Dict, Any, Optional

import requests
from strands import Agent, tool
from strands.models.openai import OpenAIModel
from .prompts import FINANCE_PERSONA_PROMPT

logger = logging.getLogger(__name__)


class MCPClient:
    """Minimal, resilient client for an MCP server.

    The MCP server API is not rigidly defined here; the client will try a few
    reasonable endpoints and return a uniform list of result dicts. This keeps
    the persona resilient to small API differences while surfacing helpful
    finance data when available.
    """

    def __init__(self, base_url: Optional[str] = None, timeout: float = 5.0):
        self.base_url = base_url or os.getenv("MCP_SERVER_URL", "http://localhost:9000")
        self.timeout = timeout

    def _try_post(self, path: str, payload: dict) -> Optional[dict]:
        url = self.base_url.rstrip("/") + path
        try:
            resp = requests.post(url, json=payload, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.debug("MCP POST %s failed: %s", url, e)
            return None

    def _try_get(self, path: str, params: dict) -> Optional[dict]:
        url = self.base_url.rstrip("/") + path
        try:
            resp = requests.get(url, params=params, timeout=self.timeout)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.debug("MCP GET %s failed: %s", url, e)
            return None

    def query(self, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """Return a list of result dicts with keys like title, summary, url, source.

        The method tries several common paths used by MCP-style servers and
        normalises the responses. If nothing works it returns an empty list.
        """
        if not self.base_url:
            return []

        # Candidate endpoints to try (most likely first)
        attempts = [
            ("POST", "/api/query", {"query": query, "top_k": top_k}),
            ("POST", "/query", {"query": query, "top_k": top_k}),
            ("POST", "/api/v1/query", {"query": query, "top_k": top_k}),
            ("GET", "/search", {"q": query, "top_k": top_k}),
            ("GET", "/api/v1/search", {"query": query, "top_k": top_k}),
        ]

        for method, path, payload in attempts:
            try:
                if method == "POST":
                    data = self._try_post(path, payload)
                else:
                    data = self._try_get(path, payload)

                if not data:
                    continue

                # Normalize responses that might be wrapped differently
                # Common forms: {results:[{title,summary,url}...]}, or list directly
                if isinstance(data, dict):
                    if "results" in data and isinstance(data["results"], list):
                        raw_list = data["results"]
                    elif "items" in data and isinstance(data["items"], list):
                        raw_list = data["items"]
                    else:
                        # Single-object response: try to extract plausible fields
                        raw_list = [data]
                elif isinstance(data, list):
                    raw_list = data
                else:
                    raw_list = []

                normalized = []
                for item in raw_list[:top_k]:
                    if not isinstance(item, dict):
                        continue
                    title = item.get("title") or item.get("name") or item.get("dataset") or ""
                    summary = item.get("summary") or item.get("description") or item.get("snippet") or ""
                    url = item.get("url") or item.get("link") or item.get("path") or ""
                    source = item.get("source") or item.get("provider") or "mcp"
                    normalized.append({"title": title, "summary": summary, "url": url, "source": source})

                if normalized:
                    logger.info("MCP: retrieved %d records from %s", len(normalized), self.base_url)
                    return normalized

            except Exception:
                # _try_post/_try_get already log at debug level
                continue

        logger.info("MCP: no usable response from %s", self.base_url)
        return []


def build_finance_persona_agent(model: OpenAIModel) -> Agent:
    return Agent(
        model=model,
        name="Finance Persona",
        description="Finance/investment analyst. Can plan info needs and deliver financial analysis.",
        system_prompt=FINANCE_PERSONA_PROMPT,
        callback_handler=None,
    )


def _summarize_mcp_results(results: List[Dict[str, Any]], max_items: int = 5) -> str:
    if not results:
        return "(no MCP data available)"
    lines = []
    for r in results[:max_items]:
        title = r.get("title") or "(untitled)"
        summary = r.get("summary") or ""
        url = r.get("url") or ""
        lines.append(f"- {title}: {summary}" + (f" (source: {url})" if url else ""))
    return "\n".join(lines)


def make_finance_persona_tool(persona_agent: Agent):
    """Return a Strands tool wrapping the finance persona.

    The returned tool keeps the same signature as before so `multi_agent.py`
    can call it without modification. When generating results the tool will
    attempt to fetch related data from an MCP server and include a short
    MCP summary in the persona prompt.
    """

    mcp_client = MCPClient()

    @tool(description="Finance persona. mode='plan' or 'deliver'. Helps plan enrichment and generate financial output.")
    def finance_persona_agent(mode: str, persona_task: str, user_query: str, kb_size: int, graph_answer_json: str) -> str:
        """
        mode: "plan" or "deliver"
        persona_task: ex. 'investment_analysis', 'risk_assessment'
        user_query: the original user question or request
        kb_size: current size of the knowledge base (int)
        graph_answer_json: stringified JSON from graph_rag containing fields:
            - answer
            - confidence
            - contexts
        returns:
          - if mode == 'plan': JSON string telling Supervisor if more info is needed
          - if mode == 'deliver': final stakeholder-facing output text
        """

        # Try to parse graph_answer_json if it's a JSON string
        try:
            graph_json_obj = json.loads(graph_answer_json) if isinstance(graph_answer_json, str) and graph_answer_json else graph_answer_json
        except Exception:
            graph_json_obj = None

        # Build a lightweight MCP query. Prefer using the user_query, then graph 'answer' text if present,
        # otherwise fall back to the persona task string.
        query_text = user_query
        if not query_text:
            if isinstance(graph_json_obj, dict):
                query_text = graph_json_obj.get("answer") or graph_json_obj.get("query")
        if not query_text:
            query_text = persona_task or "financial signals"

        # Fetch MCP results (best-effort). If the server is not available we will proceed.
        try:
            mcp_results = mcp_client.query(query_text, top_k=5)
        except Exception as e:
            logger.debug("Error querying MCP server: %s", e)
            mcp_results = []

        mcp_summary = _summarize_mcp_results(mcp_results, max_items=5)

        # Compose the persona prompt, injecting MCP summary and the graph snapshot.
        prompt_parts = [f"You are operating in MODE = {mode}.", ""]
        prompt_parts.append(f"Original user query: {user_query}")
        prompt_parts.append(f"persona_task: {persona_task}")
        prompt_parts.append(f"kb_size: {kb_size}")
        prompt_parts.append("")
        prompt_parts.append("Here is the current graph-based analysis snapshot:")
        prompt_parts.append(graph_answer_json if graph_answer_json else "(no graph snapshot provided)")
        prompt_parts.append("")
        prompt_parts.append("MCP server summary (best-effort):")
        prompt_parts.append(mcp_summary)
        prompt_parts.append("")
        prompt_parts.append("Follow the MODE rules from your system prompt.")
        prompt_parts.append("When generating search_hints in MODE \"plan\", ensure they are specific to the user's query: \"" + user_query + "\".")
        prompt_parts.append("When responding in MODE \"deliver\", tailor your response to address the user's query: \"" + user_query + "\".")
        prompt_parts.append("If MODE is \"plan\", respond with a pure JSON object as a string.")
        prompt_parts.append("If MODE is \"deliver\", respond with final stakeholder-facing narrative (no JSON).")

        prompt = "\n".join(prompt_parts)

        # Call the persona agent and return the string result
        try:
            resp = persona_agent(prompt)
            return str(resp).strip()
        except Exception as e:
            logger.exception("Finance persona agent call failed: %s", e)
            # Fallback: return a minimal JSON for plan mode or a plain failure note for deliver
            if mode == "plan":
                search_hints = user_query or "collect more financial datasets and market reports"
                fallback = json.dumps({"need_more_info": True, "persona_task": persona_task, "search_hints": search_hints})
                return fallback
            return "Finance persona failed to produce a response."

    return finance_persona_agent
