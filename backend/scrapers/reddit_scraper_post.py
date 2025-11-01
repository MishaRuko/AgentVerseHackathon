import requests
import json
from urllib.parse import urlparse

def scrape_post(post_url: str):
    """
    Scrapes a single Reddit post (title, body, comments) from its URL
    using Reddit's public JSON view.

    Args:
        post_url: The full URL of the Reddit post. Can be with or without the trailing slash.

    Returns:
        A dictionary with:
        {
            'title': ...,
            'content': ...,
            'comments': [ ... ]
        }
        or {} if something goes wrong.
    """

    # make sure the URL ends with .json so we get the structured data
    # examples we accept:
    #   https://www.reddit.com/r/python/comments/abc123/some_title/
    #   https://reddit.com/r/python/comments/abc123/some_title
    # we convert it to:
    #   https://www.reddit.com/r/python/comments/abc123/some_title/.json
    parsed = urlparse(post_url)
    base_url = f"https://{parsed.netloc}{parsed.path}"
    if not base_url.endswith('/'):
        base_url += '/'
    json_url = base_url + ".json"

    headers = {'User-Agent': 'Mozilla/5.0'}

    try:
        response = requests.get(json_url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching post: {e}")
        return {}

    try:
        data = response.json()

        # data[0] = post metadata
        # data[1] = comments listing
        post_info = data[0]['data']['children'][0]['data']

        title = post_info.get('title', '')
        content = post_info.get('selftext', '')

        comments_raw = data[1]['data']['children']

        comments = []
        for c in comments_raw:
            # c['kind'] == 't1' means it's a comment, 'more' means "load more"
            if c.get('kind') == 't1':
                body = c['data'].get('body', '')
                comments.append(body)

        return {
            'title': title,
            'content': content,
            'comments': comments
        }

    except (json.JSONDecodeError, KeyError, IndexError) as e:
        print(f"Error parsing JSON from post: {e}")
        return {}


if __name__ == '__main__':
    # example usage:
    # replace this with any reddit post link you want
    url = "https://www.reddit.com/r/Python/comments/1ols60g/solvex_an_open_source_fastapi_scipy_api_im/"
    post_data = scrape_post(url)

    if post_data:
        print(f"Title: {post_data['title']}\n")
        print(f"Content: {post_data['content']}\n")
        print("Comments:")
        for comment in post_data['comments']:
            print(f"- {comment}")
