import requests
import json
from urllib.parse import urlparse

def extract_tweet_id(tweet_url: str) -> str:
    """
    Extracts the Tweet ID from a standard X/Twitter URL.
    Example URL:
        https://x.com/someuser/status/1234567890123456789
        https://twitter.com/someuser/status/1234567890123456789
    """
    path_parts = urlparse(tweet_url).path.strip("/").split("/")
    # look for ".../status/<id>"
    for i, part in enumerate(path_parts):
        if part == "status" and i + 1 < len(path_parts):
            return path_parts[i + 1]
    raise ValueError("Could not extract tweet ID from URL")


def get_post_and_replies(tweet_url: str, bearer_token: str, max_results: int = 50):
    """
    Fetches a single X post (tweet) and its replies using the official X API v2.

    Args:
        tweet_url: URL to the post on X (twitter.com or x.com).
        bearer_token: Your X API Bearer Token (App-only OAuth2 token).
        max_results: Max number of replies to return from recent search (10–100 allowed).

    Returns:
        {
            'title': <tweet text>,
            'content': <alias of tweet text, kept for Reddit parity>,
            'comments': [ list of reply texts ]
        }

    Notes:
        - You must have an X developer account + project to get a Bearer token.
          Even "Free" access needs auth and has strict read limits. :contentReference[oaicite:2]{index=2}
        - Replies are pulled via conversation_id:<original_id>, which returns
          the full thread (root + replies) from the last ~7 days, in reverse
          chrono order. :contentReference[oaicite:3]{index=3}
    """

    tweet_id = extract_tweet_id(tweet_url)

    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "User-Agent": "influx-trend-scraper/1.0"
    }

    # 1) Get the original post data, including its conversation_id
    tweet_lookup_url = (
        f"https://api.x.com/2/tweets/{tweet_id}"
        "?tweet.fields=author_id,created_at,conversation_id,text"
    )

    try:
        tweet_resp = requests.get(tweet_lookup_url, headers=headers)
        tweet_resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching tweet {tweet_id}: {e}")
        return {}

    try:
        tweet_json = tweet_resp.json()
        tweet_data = tweet_json["data"]
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing tweet JSON: {e}")
        return {}

    root_text = tweet_data.get("text", "")
    conversation_id = tweet_data.get("conversation_id", tweet_id)

    # 2) Search for all posts in this conversation
    # We request:
    #   - tweet.fields to get metadata
    #   - max_results controls page size (10..100)
    # NOTE: This returns the entire thread, including the root tweet,
    #       other people's replies, and nested replies.
    search_url = (
        "https://api.x.com/2/tweets/search/recent"
        f"?query=conversation_id:{conversation_id}"
        f"&tweet.fields=author_id,created_at,conversation_id,in_reply_to_user_id,referenced_tweets,text"
        f"&max_results={max_results}"
    )

    try:
        convo_resp = requests.get(search_url, headers=headers)
        convo_resp.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching replies for conversation {conversation_id}: {e}")
        # Still return the main tweet if replies fail
        return {
            "title": root_text,
            "content": root_text,
            "comments": []
        }

    try:
        convo_json = convo_resp.json()
        convo_tweets = convo_json.get("data", [])
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing replies JSON: {e}")
        convo_tweets = []

    # 3) Build the "comments" list
    # Strategy:
    #   - Ignore the root tweet (same id as tweet_id).
    #   - Keep every other tweet's text.
    # If you only want direct replies to the root (not replies-to-replies),
    # you could additionally check referenced_tweets for type == "replied_to"
    # where id == tweet_id.
    comments = []
    for t in convo_tweets:
        if t.get("id") == tweet_id:
            continue  # skip the root in the comment list
        body = t.get("text", "")
        if body:
            comments.append(body)

    # Return in the same shape as the Reddit scraper
    return {
        "title": root_text,
        "content": root_text,
        "comments": comments
    }


if __name__ == "__main__":
    # EXAMPLE USAGE:
    # Put your Bearer token here
    BEARER = "YOUR_BEARER_TOKEN_HERE"

    # Any public post URL on X/Twitter
    url = "https://x.com/DUALIPA/status/1786350497877688525"

    data = get_post_and_replies(url, BEARER, max_results=50)

    print("Title:", data.get("title", ""))
    print("Content:", data.get("content", ""))
    print("Comments:")
    for c in data.get("comments", []):
        print("-", c)
