import json
import asyncio
import sys
import os
import re
from urllib.parse import quote_plus, urlparse
from datetime import datetime
from dotenv import load_dotenv
import yaml
import requests

from strands import Agent, tool
from strands.models.openai import OpenAIModel

# ---------------------------------------------------------------------
# ENV / PATH SETUP
# ---------------------------------------------------------------------

load_dotenv()

# make sure backend is importable
sys.path.append(os.path.join(os.path.dirname(__file__), 'backend'))

# internal imports from backend modules
# graph_rag: semantic retrieval over graph KB
from graph_rag import rag_query  # :contentReference[oaicite:1]{index=1}

# scraper pipeline -> ideas
import backend.scrapers.scraper_agent as WebScraper  # scrape_and_generate_ideas() :contentReference[oaicite:2]{index=2}

# clustering + summarisation of ideas into clusters
from clustering import cluster_and_summarize  # :contentReference[oaicite:3]{index=3}

# graph builder to connect related clusters and generate higher-level themes
from graph_builder import build_cluster_graph  # :contentReference[oaicite:4]{index=4}

# ---------------------------------------------------------------------
# GLOBAL STATE
# ---------------------------------------------------------------------

# This is the persistent knowledge base.
# Keys: tuple(embedding floats)
# Values: text summary / theme / explanation
#
# graph_builder_agent will KEEP ADDING to this.
# graph_rag_agent will READ from this.
knowledge_base = {}


# ---------------------------------------------------------------------
# OPENAI MODEL CHOICE
# ---------------------------------------------------------------------

openai_model = OpenAIModel(
    model_id="gpt-4o-mini",  # cost-effective but capable
)


# ---------------------------------------------------------------------
# LOAD PROMPTS
# ---------------------------------------------------------------------
#
# agent_prompts.yaml gives us:
# - source_selector: generate search queries
# - scraper: extract atomic ideas from text
# - graph_rag: synthesize final structured answer from retrieved contexts
#
# marketing_strategist.yaml currently defines "orchestrator", but we are going
# to override / extend that prompt with the new supervisor loop + persona routing.
#
# We still load them so we can reuse tone/behavior where helpful.

with open("agent_prompts.yaml", "r") as f:
    _prompt_yaml = yaml.safe_load(f)
    SOURCE_SELECTOR_PROMPT = _prompt_yaml["source_selector"]        # :contentReference[oaicite:5]{index=5}
    SCRAPER_PROMPT = _prompt_yaml["scraper"]                        # :contentReference[oaicite:6]{index=6}
    GRAPH_RAG_PROMPT = _prompt_yaml["graph_rag"]                    # :contentReference[oaicite:7]{index=7}

with open("marketing_strategist.yaml", "r") as f:
    _orchestrator_yaml = yaml.safe_load(f)
    BASE_ORCHESTRATOR_PROMPT = _orchestrator_yaml["orchestrator"]   # :contentReference[oaicite:8]{index=8}


# ---------------------------------------------------------------------
# PERSONA PROMPTS
# ---------------------------------------------------------------------
#
# We support multiple outward-facing personas.
# The Supervisor will figure out who should "speak" in the final answer.
#
# You can (and should) tune these.

MARKETING_PERSONA_PROMPT = """
You are the Marketing Strategy Persona.

Audience:
- brand / growth / social / campaign / product marketing teams

Voice:
- practical
- insight-led
- focuses on audiences, channels, messaging angles, competitor positioning

Your job:
1. Take structured analytical findings about trends, sentiment clusters, communities, etc.
2. Turn that into advice like:
   - how to position messaging
   - which audiences to target
   - what narratives are gaining traction or are risky
3. Be concrete. Talk like a strategist in a meeting deck.

When you answer:
- You MAY reference trends, communities, or sentiments.
- You MAY suggest tactical next steps.
- Do NOT invent data that you weren't given.
- Do NOT leak internal tool names. Just say "our analysis" or "what we're seeing online".
"""

IB_PERSONA_PROMPT = """
You are the Investment / Finance Persona.

Audience:
- investors, corporate strategy, M&A, competitive intelligence, leadership teams

Voice:
- analytical, clarity-first, not hype
- talks in terms of risk, upside, sentiment pressure, regulatory perception, market narrative

Your job:
1. Take structured analytical findings about trends, clusters, narratives, and perception.
2. Frame them as:
   - reputational risk
   - market confidence / skepticism
   - early signals of regulatory / PR / consumer backlash
   - competitor advantage angles
3. If relevant, mention what stakeholders (consumers, regulators, tech community, etc.) are saying.

When you answer:
- Be concise and boardroom-friendly.
- Do NOT fabricate numbers or financial projections.
- Do NOT leak internal tool names. Call it "the analysis".
"""


# ---------------------------------------------------------------------
# HELPER: SOURCE TYPE INFERENCE FOR GOOGLE RESULTS
# ---------------------------------------------------------------------

def infer_source_type(url: str, title: str = "", snippet: str = "") -> str:
    """
    Map a URL to a scraping mode expected by scrape_source():
    "reddit_post", "reddit_sub", "twitter", "news", "general".
    Heuristics adapted from original code.
    """

    if not url:
        return "general"

    parsed = urlparse(url)
    netloc = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    title = (title or "").lower()
    snippet = (snippet or "").lower()

    # Reddit
    if "reddit.com" in netloc or "redd.it" in netloc:
        if "/comments/" in path or re.search(r"/comments/[a-z0-9]+", path):
            return "reddit_post"
        if re.search(r"^/r/[^/]+/?", path) or re.search(r"^/r/[^/]+/(hot|new|top)", path):
            return "reddit_sub"
        return "reddit_sub"

    # Twitter / X
    if "twitter.com" in netloc or "x.com" in netloc:
        return "twitter"

    # Wikipedia / similar → treat as news/article-like
    if "wikipedia.org" in netloc:
        return "news"

    # News-like heuristics
    news_indicators = ["news", "article", "/articles/", "/202", "/story", "press", "opinion"]
    if any(ind in path for ind in news_indicators) or any(ind in title or ind in snippet for ind in news_indicators):
        return "news"

    known_news_domains = {
        "nytimes.com",
        "theguardian.com",
        "bbc.co.uk",
        "cnn.com",
        "washingtonpost.com"
    }
    if any(d in netloc for d in known_news_domains):
        return "news"

    return "general"


# ---------------------------------------------------------------------
# GOOGLE SEARCH HELPER
# ---------------------------------------------------------------------

def google_search(query: str, num_results: int = 3) -> list:
    """
    Google Custom Search API helper. Falls back to mock if creds missing.
    """

    api_key = os.environ.get("GOOGLE_API_KEY")
    cse_id = os.environ.get("GOOGLE_CSE_ID")

    if not api_key or not cse_id:
        # fallback mock
        return [
            {
                "title": f"Result 1 for '{query}'",
                "url": f"https://example.com/result1?q={quote_plus(query)}",
                "snippet": f"Mock search result about {query}...",
                "type": "general"
            },
            {
                "title": f"Result 2 for '{query}'",
                "url": f"https://example.com/result2?q={quote_plus(query)}",
                "snippet": f"Additional information about {query}...",
                "type": "general"
            },
            {
                "title": f"Result 3 for '{query}'",
                "url": f"https://example.com/result3?q={quote_plus(query)}",
                "snippet": f"More details about {query}...",
                "type": "general"
            }
        ][:num_results]

    try:
        url = "https://www.googleapis.com/customsearch/v1"
        params = {
            "key": api_key,
            "cx": cse_id,
            "q": query,
            "num": num_results
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("items", [])[:num_results]:
            title = item.get("title", "")
            link = item.get("link", "")
            snippet = item.get("snippet", "")
            results.append({
                "title": title,
                "url": link,
                "snippet": snippet,
                "type": infer_source_type(link, title, snippet),
            })
        return results

    except Exception as e:
        # fallback to mock
        return google_search(query, num_results)


# ---------------------------------------------------------------------
# SPECIALIST AGENT INSTANCES
# ---------------------------------------------------------------------

_source_selector_agent_instance = Agent(
    model=openai_model,
    name="Source Selector",
    description="Generates targeted search queries for multiple source types.",
    system_prompt=SOURCE_SELECTOR_PROMPT,
    callback_handler=None,
)

_scraper_agent_instance = Agent(
    model=openai_model,
    name="Web Scraper",
    description="Extracts atomic ideas from raw sources.",
    system_prompt=SCRAPER_PROMPT,
    callback_handler=None,
)

_graph_rag_agent_instance = Agent(
    model=openai_model,
    name="Graph RAG Synthesizer",
    description="Synthesizes an answer from retrieved graph/cluster contexts.",
    system_prompt=GRAPH_RAG_PROMPT,
    callback_handler=None,
)

_marketing_persona_agent_instance = Agent(
    model=openai_model,
    name="Marketing Persona",
    description="Turns raw trend intelligence into actionable marketing strategy.",
    system_prompt=MARKETING_PERSONA_PROMPT,
    callback_handler=None,
)

_investment_banking_persona_agent_instance = Agent(
    model=openai_model,
    name="Finance Persona",
    description="Frames trend intelligence in terms of risk, market sentiment, competitive posture.",
    system_prompt=IB_PERSONA_PROMPT,
    callback_handler=None,
)


# ---------------------------------------------------------------------
# TOOL WRAPPERS
# ---------------------------------------------------------------------

@tool(description="Generate 3 diverse Google queries, then gather top sources for each.")
def source_selector_agent(user_query: str) -> str:
    """
    1. Ask the Source Selector agent to generate EXACTLY 3 search queries as a JSON array.
    2. Run google_search for each query (top 3 results).
    3. Return list of {url, type} objects as JSON: {\"sources\": [{\"url\":...,\"type\":...}, ...]}
    """
    try:
        result = _source_selector_agent_instance(user_query)
        queries = json.loads(str(result).strip())

        all_sources = []
        for q in queries:
            search_results = google_search(q, num_results=3)
            for r in search_results:
                all_sources.append({
                    "url": r["url"],
                    "type": r["type"],
                })

        return json.dumps({"sources": all_sources})
    except Exception as e:
        # fallback if the agent didn't return valid JSON
        fallback_queries = [
            user_query,
            f"{user_query} latest discussion",
            f"{user_query} controversy reddit"
        ]
        all_sources = []
        for fq in fallback_queries:
            for r in google_search(fq, num_results=3):
                all_sources.append({
                    "url": r["url"],
                    "type": infer_source_type(r["url"], r.get("title",""), r.get("snippet","")),
                })
        return json.dumps({"sources": all_sources})


@tool(description="Scrape provided sources and extract atomic 'ideas' statements for clustering.")
async def scraper_agent(sources_json: str) -> str:
    """
    Input:
        sources_json: '{"sources":[{"url":"...","type":"reddit_post"}, ...]}'
    Output:
        JSON: {"ideas": ["idea1", "idea2", ...]}

    Uses scrape_and_generate_ideas() to crawl and LLM-extract atomic ideas
    from Reddit/Twitter/news/general pages. :contentReference[oaicite:9]{index=9}
    """
    try:
        payload = json.loads(sources_json)
        sources = payload.get("sources", [])
    except Exception:
        sources = []

    # scrape_and_generate_ideas is sync, so run it in a thread to not block event loop
    loop = asyncio.get_running_loop()
    ideas_list = await loop.run_in_executor(
        None,
        WebScraper.scrape_and_generate_ideas,
        sources
    )

    return json.dumps({"ideas": ideas_list})


@tool(description="Cluster ideas, build/expand the global knowledge graph, and update the shared knowledge base.")
def graph_builder_agent(ideas_json: str) -> str:
    """
    Input:
        ideas_json: '{"ideas":["...", "...", ...]}'

    Steps:
    1. Cluster raw idea strings and summarize each cluster. (cluster_and_summarize) :contentReference[oaicite:10]{index=10}
    2. Build a similarity graph of clusters, detect higher-level communities,
       and generate overarching theme explanations. (build_cluster_graph) :contentReference[oaicite:11]{index=11}
    3. Convert those clusters + community themes into embeddings->text entries.
    4. Merge them into the global knowledge_base dict.

    Output:
        JSON: {
          "kb_size": <int>,
          "clusters_added": <int>,
          "status": "ok"
        }
    """
    global knowledge_base

    try:
        payload = json.loads(ideas_json)
        ideas = payload.get("ideas", [])
    except Exception:
        ideas = []

    # If nothing to add, just report current KB size
    if not ideas:
        return json.dumps({
            "kb_size": len(knowledge_base),
            "clusters_added": 0,
            "status": "no_ideas"
        })

    # 1. cluster_and_summarize -> list of {summary, embedding, ideas:[{idea, embedding}, ...]}
    clustered_data = cluster_and_summarize(ideas)  # :contentReference[oaicite:12]{index=12}

    # 2. build_cluster_graph -> (embedding_to_explanation, group_to_explanation, sim_matrix)
    embedding_to_explanation, group_to_explanation, _sim = build_cluster_graph(clustered_data)  # :contentReference[oaicite:13]{index=13}

    # 3. Merge into global KB.
    # embedding_to_explanation already maps tuple(embedding) -> text summary/theme
    added = 0
    for emb_tuple, text_block in embedding_to_explanation.items():
        # emb_tuple is tuple(float,...)
        # text_block is explanation string
        # we just overwrite or insert
        if emb_tuple not in knowledge_base:
            added += 1
        knowledge_base[emb_tuple] = text_block

    return json.dumps({
        "kb_size": len(knowledge_base),
        "clusters_added": added,
        "status": "ok"
    })


@tool(description="Query the global knowledge base using Graph RAG and synthesize an answer.")
def graph_rag_agent(user_query: str) -> str:
    """
    Input:
        user_query: "string question from supervisor"
    Behavior:
        1. Use rag_query(...) to retrieve top contexts from knowledge_base. :contentReference[oaicite:14]{index=14}
        2. Ask the _graph_rag_agent_instance (LLM with GRAPH_RAG_PROMPT) to synthesize an answer
           ONLY using those contexts (like in agent_prompts.yaml graph_rag spec). :contentReference[oaicite:15]{index=15}
    Output:
        JSON:
        {
            "answer": "...",
            "sources_used": n,
            "confidence": "high|medium|low",
            "contexts": [...]
        }
    """
    global knowledge_base

    if not knowledge_base:
        return json.dumps({
            "answer": "No knowledge available yet.",
            "sources_used": 0,
            "confidence": "low",
            "contexts": []
        })

    # 1. retrieve top-K contexts from KB
    contexts = rag_query(knowledge_base, user_query, top_k=3)  # returns list[{"text","index","score"}, ...] :contentReference[oaicite:16]{index=16}

    # 2. build synthesis prompt for the Graph RAG agent
    context_texts = [ctx["text"] for ctx in contexts]
    synthesis_prompt = f"""
You are the Graph RAG synthesis specialist.

User Query: {user_query}

Retrieved Contexts:
{json.dumps(context_texts, indent=2)}

Follow your system instructions. Return ONLY a JSON object with:
{{
    "answer": "your comprehensive answer here",
    "sources_used": <number of contexts used>,
    "confidence": "high/medium/low"
}}
"""

    llm_raw = _graph_rag_agent_instance(synthesis_prompt)
    llm_text = str(llm_raw).strip()

    # try to parse valid JSON from the persona
    try:
        parsed = json.loads(llm_text)
    except Exception:
        parsed = {
            "answer": llm_text,
            "sources_used": len(contexts),
            "confidence": "medium",
        }

    parsed["contexts"] = contexts
    return json.dumps(parsed)


@tool(description="Format final insights for a marketing stakeholder. Input is the raw analytical answer JSON from graph_rag_agent.")
def marketing_persona_agent(answer_json: str) -> str:
    """
    Input:
        answer_json: stringified JSON from graph_rag_agent() with fields:
            answer, sources_used, confidence, contexts

    Output:
        A plain-English narrative aimed at marketing / growth / brand teams.
    """
    try:
        payload = json.loads(answer_json)
    except Exception:
        payload = {"answer": answer_json}

    # Build a prompt for the marketing persona agent
    persona_prompt = f"""
You are the Marketing Strategy Persona.

Here is the structured trend analysis you need to translate:
{json.dumps(payload, indent=2)}

Rewrite this for a marketing/growth audience:
- identify what audiences are saying / feeling
- highlight opportunities and risks in messaging, positioning, channels
- suggest 2-3 next steps
- DO NOT invent new facts that are not implied by the analysis
    """.strip()

    resp = _marketing_persona_agent_instance(persona_prompt)
    return str(resp).strip()


@tool(description="Format final insights for an investment / finance stakeholder. Input is the raw analytical answer JSON from graph_rag_agent.")
def ib_persona_agent(answer_json: str) -> str:
    """
    Input:
        answer_json: stringified JSON from graph_rag_agent() with fields:
            answer, sources_used, confidence, contexts

    Output:
        A plain-English narrative aimed at investors / corp strat / finance.
    """
    try:
        payload = json.loads(answer_json)
    except Exception:
        payload = {"answer": answer_json}

    persona_prompt = f"""
You are the Investment / Finance Persona.

Here is the structured trend analysis you need to translate:
{json.dumps(payload, indent=2)}

Rewrite this for an investor / exec / finance audience:
- talk in terms of perceived risk, market sentiment, regulatory pressure, competitive posture
- explain why this matters for valuation / reputation / approach
- keep it executive and concise
- DO NOT invent any numerical projections or financials
    """.strip()

    resp = _investment_banking_persona_agent_instance(persona_prompt)
    return str(resp).strip()


# ---------------------------------------------------------------------
# ORCHESTRATOR (SUPERVISOR)
# ---------------------------------------------------------------------
#
# We now define the actual Supervisor agent.
#
# The Supervisor's job:
#
# 1. Understand the user's question.
# 2. Decide which persona should answer (marketing_persona_agent vs ib_persona_agent, etc.).
#    - Marketing if the question is about campaigns, positioning, audience, comms, reputation with consumers.
#    - Finance if the question is about valuation, investor sentiment, competitive risk, regulatory outlook.
#
# 3. Try to answer from existing knowledge_base:
#    - Call graph_rag_agent(user_query)
#    - If confidence == "high", skip scraping.
#
# 4. If confidence is "medium" or "low", or the info is clearly missing / outdated:
#    - Call source_selector_agent(user_query) to get candidate sources.
#    - Call scraper_agent(...) on those sources to extract atomic ideas.
#    - Call graph_builder_agent(...) to cluster, build/expand graph, and update global KB.
#    - Call graph_rag_agent(user_query) AGAIN to get a better answer.
#
# 5. Take the final answer JSON from graph_rag_agent and send it to the chosen persona tool
#    (marketing_persona_agent or ib_persona_agent). Return ONLY that persona output to the user.
#
# IMPORTANT FOR THE LLM:
# - The Supervisor should not speak directly in analyst voice. It should ALWAYS run a persona tool
#   for the final wording.
# - The Supervisor should return ONLY what the persona tool returns.

SUPERVISOR_PROMPT = f"""
You are the Supervisor Orchestrator.

Your responsibilities:
1. Figure out the user's intent and which persona should address them:
   - If the question is about branding, messaging, audience perception, campaign strategy,
     social media playbooks, creator marketing → use marketing_persona_agent.
   - If the question is about investor risk, market sentiment, regulatory pressure,
     competitor position, valuation narrative → use ib_persona_agent.

2. ALWAYS attempt to ground the answer in evidence from the knowledge graph / knowledge base.
   You query it via graph_rag_agent.

3. Your decision loop is:
   a) Call graph_rag_agent(user_query).
   b) Examine its JSON. If confidence is "high", continue.
   c) If confidence is "medium" or "low", or if the analysis seems incomplete:
      i.   Call source_selector_agent(user_query) to get sources.
      ii.  Call scraper_agent(...) on that result to get ideas.
      iii. Call graph_builder_agent(...) on that result to expand the global knowledge base.
      iv.  Call graph_rag_agent(user_query) AGAIN to get an updated answer.

4. Once you have the final graph_rag_agent JSON output, DO NOT answer directly.
   Instead:
   - Call the correct persona tool (marketing_persona_agent or ib_persona_agent),
     passing in the JSON string you got from graph_rag_agent.
   - Return ONLY what the persona tool returns. No extra wrapping.

5. VERY IMPORTANT:
   - You NEVER reveal internal tool names to the user.
   - You NEVER dump raw embeddings or raw contexts to the user.
   - You NEVER say "my confidence is X" unless the persona wording naturally implies uncertainty.
   - You NEVER invent facts not supported by the analysis.

Tools you can call:
- source_selector_agent(user_query: str) -> JSON {"sources":[{"url": "...", "type": "..."}]}
- scraper_agent(sources_json: str) -> JSON {"ideas":[...]}
- graph_builder_agent(ideas_json: str) -> JSON { "kb_size": int, "clusters_added": int, "status": "ok" }
- graph_rag_agent(user_query: str) -> JSON {"answer": "...", "sources_used": n, "confidence": "...", "contexts":[...]}
- marketing_persona_agent(answer_json: str) -> str
- ib_persona_agent(answer_json: str) -> str

Follow the loop above to produce your final response.
""".strip()


def _build_orchestrator() -> Agent:
    """
    Build the Supervisor agent with access to all tools including personas.
    """
    orchestrator = Agent(
        model=openai_model,
        system_prompt=SUPERVISOR_PROMPT,
        tools=[
            source_selector_agent,
            scraper_agent,
            graph_builder_agent,
            graph_rag_agent,
            marketing_persona_agent,
            ib_persona_agent,
        ],
        callback_handler=None,
    )
    return orchestrator
