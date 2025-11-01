import os
from typing import List, Tuple, Dict, Any, Union

from ..llm import llm

# import all scrapers
from . import general_scraper
from . import news_scraper
from . import reddit_scraper_post
from . import reddit_scraper_sub
from . import twitter_scraper

def scrape_source(url: str, source_type: str) -> Any:
    """
    Dispatch to the correct scraper based on source_type.

    Args:
        url (str): The URL to scrape.
        source_type (str): One of:
            "general"        -> generic webpage
            "news"           -> news / wiki-style article
            "reddit_post"    -> single reddit post + comments
            "reddit_sub"     -> whole subreddit listing
            "twitter"        -> tweet + replies

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

    elif source_type == "twitter":
        # returns dict {title, content, comments:[...]}
        # needs bearer token from env
        bearer_token = os.getenv("X_BEARER_TOKEN")
        if not bearer_token:
            raise RuntimeError("X_BEARER_TOKEN environment variable not set for twitter scraping")

        return twitter_scraper.get_post_and_replies(url, bearer_token, max_results=50)

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


def _flatten_twitter_dict(tweet_dict: Dict[str, Any]) -> str:
    """
    Take twitter scrape output:
        { 'title': root_text, 'content': root_text, 'comments': [...] }
    and merge.
    """
    if not isinstance(tweet_dict, dict):
        return ""

    root = tweet_dict.get("content", "")
    replies = tweet_dict.get("comments", [])
    replies_text = "\n".join([f"- {r}" for r in replies if isinstance(r, str)])

    combined = f"TWEET:\n{root}\n\nREPLIES:\n{replies_text}"
    return combined.strip()


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

    if source_type == "twitter":
        return _flatten_twitter_dict(raw_data)

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
    We'll ask the model to respond with one idea per line, no numbering,
    no extra commentary.
    """

    if not full_text.strip():
        return []

    prompt = (
        "You are extracting distinct ideas from text for downstream clustering.\n"
        "Rules:\n"
        "- Each idea should be a standalone short statement about a claim, topic, concern, trend, opinion, insight, or issue.\n"
        "- Do not include speaker names, timestamps, or metadata.\n"
        "- Do not number them.\n"
        "- One idea per line.\n\n"
        "Text:\n"
        f"{full_text}\n\n"
        "Now list the ideas, one per line:"
    )

    response = llm.invoke(prompt).content

    # split by newline, strip empties
    raw_lines = response.split("\n")
    ideas = [line.strip() for line in raw_lines if line.strip()]

    return ideas


def scrape_and_generate_ideas(batch: List[Tuple[str, str]]) -> List[str]:
    """
    Main entry point.

    Args:
        batch: list like:
            [
                ("https://www.reddit.com/r/whatever/comments/abc123/post_title/", "reddit_post"),
                ("python", "reddit_sub"),
                ("https://x.com/someuser/status/1234567890", "twitter"),
                ("https://example.com/some-article", "news"),
                ("https://randomblog.com/some-page", "general"),
                ...
            ]

    Returns:
        A single flat list of ideas (strings) aggregated from all sources.
    """

    all_ideas = []

    for url, source_type in batch:
        # 1. scrape
        try:
            scraped = scrape_source(url, source_type)
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
    # note: for twitter you MUST have X_BEARER_TOKEN in env or this will raise.
    test_batch = [
        # single reddit post thread
        ("https://www.reddit.com/r/python/comments/abc123/some_post_title/", "reddit_post"),

        # subreddit (just the name, assuming the scraper expects that)
        ("python", "reddit_sub"),

        # tweet + replies
        ("https://x.com/elonmusk/status/1786350497877688525", "twitter"),

        # news/wikipedia/article style
        ("https://en.wikipedia.org/wiki/Python_(programming_language)", "news"),

        # generic webpage
        ("https://example.com/", "general"),
    ]

    ideas = scrape_and_generate_ideas(test_batch)

    # print them out
    print("Collected ideas:")
    for i, idea in enumerate(ideas, start=1):
        print(f"{i}. {idea}")
