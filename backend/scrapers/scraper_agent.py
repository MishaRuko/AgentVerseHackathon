################################################
# RUN AS A MODULE, NOT AS A PYTHON FILE        #
# Run command from the AgentVerseHacathon dir: #
# python -m backend.scrapers.scraper_agent     #
################################################

import os
import sys
import yaml
from typing import List, Tuple, Dict, Any, Union

# Add backend to path for imports
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from llm import llm

# Load scraper prompt from YAML file
_prompt_cache = None

def _load_scraper_prompt() -> str:
    """Load the scraper prompt from agent_prompts.yaml"""
    global _prompt_cache
    if _prompt_cache is not None:
        return _prompt_cache
    
    # Get the path to agent_prompts.yaml (in the root directory)
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    yaml_path = os.path.join(root_dir, "agent_prompts.yaml")
    
    try:
        with open(yaml_path, "r") as f:
            prompts = yaml.safe_load(f)
            _prompt_cache = prompts.get("scraper", "")
            return _prompt_cache
    except Exception as e:
        print(f"Warning: Could not load scraper prompt from YAML: {e}")
        # Fallback to basic prompt
        return (
            "You are extracting distinct ideas from text for downstream clustering.\n"
            "Rules:\n"
            "- Each idea should be a standalone short statement.\n"
            "- Do not include speaker names, timestamps, or metadata.\n"
            "- Do not number them.\n"
            "- One idea per line.\n"
        )

# import all scrapers
from . import general_scraper
from . import news_scraper
from . import reddit_scraper_post
from . import reddit_scraper_sub
from . import scholar_scraper
# TWITTER DISABLED - uncomment to re-enable Twitter scraping
# from . import twitter_scraper

def scrape_source(url: str, source_type: str) -> Any:
    """
    Dispatch to the correct scraper based on source_type.

    Args:
        url (str): The URL to scrape OR a search query for scholar.
        source_type (str): One of:
            "general"        -> generic webpage
            "news"           -> news / wiki-style article
            "reddit_post"    -> single reddit post + comments
            "reddit_sub"     -> whole subreddit listing
            "scholar"        -> Google Scholar search (url is the query string)
            "scholar_url"    -> Google Scholar URL scraping (url is actual scholar URL)
            # "twitter"        -> tweet + replies (DISABLED)

    Returns:
        The raw scraped data (whatever that scraper returns).
        This can be a dict or list[dict] depending on scraper.
    """

    source_type = source_type.lower().strip()

    if source_type == "general":
        # returns dict {url, status_code, title, text, links}
        return general_scraper.scrape_page(url)

    elif source_type == "news":
        # returns dict {title, content}
        return news_scraper.scrape_article(url)

    elif source_type == "reddit_post":
        # returns dict {title, content, comments:[...]}
        return reddit_scraper_post.scrape_post(url)

    elif source_type == "reddit_sub":
        # url is expected to be a subreddit name, not a full https:// link
        # for consistency with what you've done so far.
        # Example input for this branch should be: "python" not "https://reddit.com/r/python"
        # returns list[ {title, content, comments:[...]} ]
        return reddit_scraper_sub.scrape_subreddit(url, limit=5)

    elif source_type == "scholar":
        # url is actually a search query, not a URL
        # returns list[ {title, authors, year, abstract, url, citations, source} ]
        return scholar_scraper.scrape_scholar_search(url, num_results=5)

    elif source_type == "scholar_url":
        # url is an actual Google Scholar URL
        # returns list[ {title, authors, abstract, url, source} ]
        return scholar_scraper.scrape_scholar_url(url)

    # TWITTER DISABLED - uncomment to re-enable Twitter scraping
    # elif source_type == "twitter":
    #     # returns dict {title, content, comments:[...]}
    #     # needs bearer token from env
    #     bearer_token = os.getenv("X_BEARER_TOKEN")
    #     if not bearer_token:
    #         print("[WARNING] X_BEARER_TOKEN not set - skipping Twitter scraping")
    #         return {
    #             "title": "Twitter scraping unavailable",
    #             "content": "Twitter API access requires X_BEARER_TOKEN environment variable",
    #             "comments": []
    #         }
    #     return twitter_scraper.get_post_and_replies(url, bearer_token, max_results=50)

    elif source_type == "unsupported_tiktok":
        return None

    else:
        raise ValueError(f"Unknown source_type '{source_type}'")


def _flatten_reddit_post_dict(post_dict: Dict[str, Any]) -> str:
    """
    Take a single reddit post dict like:
        { 'title': ..., 'content': ..., 'comments': [...] }
    and turn it into a big text block.
    """
    if not isinstance(post_dict, dict):
        return ""

    title = post_dict.get("title", "")
    body = post_dict.get("content", "")
    comments = post_dict.get("comments", [])

    comments_text = "\n".join([f"- {c}" for c in comments if isinstance(c, str)])
    combined = f"POST TITLE:\n{title}\n\nPOST BODY:\n{body}\n\nCOMMENTS:\n{comments_text}"
    return combined.strip()


def _flatten_reddit_sub_list(posts_list: List[Dict[str, Any]]) -> str:
    """
    Take the subreddit scrape output:
        [ {title, content, comments:[...]}, { ... }, ... ]
    and stitch them all together into one big text blob.
    """
    if not isinstance(posts_list, list):
        return ""

    chunks = []
    for idx, post in enumerate(posts_list):
        chunks.append(f"[POST {idx+1}]\n" + _flatten_reddit_post_dict(post))
    return "\n\n".join(chunks).strip()


def _flatten_news_dict(news_dict: Dict[str, Any]) -> str:
    """
    news_scraper returns:
        { 'title': ..., 'content': ... }
    """
    if not isinstance(news_dict, dict):
        return ""

    title = news_dict.get("title", "")
    body = news_dict.get("content", "")
    combined = f"HEADLINE:\n{title}\n\nARTICLE:\n{body}"
    return combined.strip()


def _flatten_general_dict(page_dict: Dict[str, Any]) -> str:
    """
    general_scraper returns:
        { 'url', 'status_code', 'title', 'text', 'links' }
    We'll focus on 'title' and 'text' for idea extraction.
    """
    if not isinstance(page_dict, dict):
        return ""

    title = page_dict.get("title", "")
    text = page_dict.get("text", "")
    combined = f"PAGE TITLE:\n{title}\n\nPAGE TEXT:\n{text}"
    return combined.strip()


def normalize_scraped_data(raw_data: Any, source_type: str) -> str:
    """
    Convert whatever structure the scraper returned into
    one big string that represents the "content" of that source.

    Args:
        raw_data: scraper's raw return (dict or list)
        source_type: same type tag we used for scraping

    Returns:
        str: a single text blob suitable for feeding to LLM
    """

    source_type = source_type.lower().strip()

    if source_type == "reddit_post":
        return _flatten_reddit_post_dict(raw_data)

    if source_type == "reddit_sub":
        return _flatten_reddit_sub_list(raw_data)

    # TWITTER DISABLED - uncomment to re-enable Twitter scraping
    # if source_type == "twitter":
    #     return _flatten_twitter_dict(raw_data)

    if source_type == "news":
        return _flatten_news_dict(raw_data)

    if source_type == "general":
        return _flatten_general_dict(raw_data)

    # fallback
    return str(raw_data)


def ideas_from_text(full_text: str) -> List[str]:
    """
    Use the LLM to extract atomic 'ideas' from a text blob.

    We want short, self-contained statements that we can cluster later.
    The prompt is loaded from agent_prompts.yaml for consistency.
    """

    if not full_text.strip():
        return []

    # Load the base prompt from YAML
    base_prompt = _load_scraper_prompt()
    
    # Append the actual text to analyze
    prompt = f"{base_prompt}\n\nText:\n{full_text}"

    response = llm.invoke(prompt).content

    # split by newline, strip empties
    raw_lines = response.split("\n")
    ideas = [line.strip() for line in raw_lines if line.strip()]

    return ideas


def scrape_and_generate_ideas(batch: List[Dict[str, str]]) -> List[str]:
    """
    Main entry point.

    Args:
        batch: list like:
            [
                {
                    "url": "https://www.reddit.com/r/whatever/comments/abc123/post_title/",
                    "type": "reddit_post"
                },
                {
                    "url": "python",
                    "type": "reddit_sub"
                },
                {
                    "url": "https://example.com/some-article",
                    "type": "news"
                },
                {
                    "url": "https://randomblog.com/some-page",
                    "type": "general"
                }
            ]

    Returns:
        A single flat list of ideas (strings) aggregated from all sources.
    """

    all_ideas = []
    print("Scraper Activated")

    for source in batch:
        # 1. scrape
        try:
            url = source["url"]
            source_type = source["type"]
            scraped = scrape_source(url, source_type)
            if scraped is None:
                continue
        except Exception as e:
            print(f"[ERROR] scraping {url} ({source_type}): {e}")
            continue

        # 2. normalize into text blob
        normalized_text = normalize_scraped_data(scraped, source_type)

        # 3. ask LLM to turn that blob into atomic ideas
        try:
            ideas = ideas_from_text(normalized_text)
        except Exception as e:
            print(f"[ERROR] idea extraction for {url} ({source_type}): {e}")
            ideas = []

        all_ideas.extend(ideas)

    return all_ideas


if __name__ == "__main__":
    # small demo batch to show usage:
    test_batch = [
    {
        "url": "https://www.reddit.com/r/python/comments/abc123/some_post_title/",
        "type": "reddit_post"
    },
    {
        "url": "python",
        "type": "reddit_sub"
    },
    # TWITTER DISABLED - uncomment to test Twitter scraping (requires X_BEARER_TOKEN)
    # {
    #     "url": "https://x.com/elonmusk/status/1786350497877688525",
    #     "type": "twitter"
    # },
    {
        "url": "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "type": "news"
    },
    {
        "url": "https://example.com/",
        "type": "general"
    }
]

    ideas = scrape_and_generate_ideas(test_batch)

    # print them out
    print("Collected ideas:")
    for i, idea in enumerate(ideas, start=1):
        print(f"{i}. {idea}")
