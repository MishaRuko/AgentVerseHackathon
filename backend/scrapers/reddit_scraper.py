import requests
import json

def scrape_subreddit(subreddit: str, limit: int = 5):
    """
    Scrapes a subreddit for a given number of posts using the JSON API.

    Args:
        subreddit: The name of the subreddit to scrape.
        limit: The maximum number of posts to scrape.

    Returns:
        A list of dictionaries, where each dictionary represents a post
        and contains the title and content.
    """
    url = f"https://www.reddit.com/r/{subreddit}/.json?limit={limit}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching subreddit {subreddit}: {e}")
        return []

    try:
        data = response.json()
        posts = []
        for post in data['data']['children']:
            posts.append({
                'title': post['data']['title'],
                'content': post['data']['selftext']
            })
        return posts
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing JSON from subreddit {subreddit}: {e}")
        return []

if __name__ == '__main__':
    # Example usage:
    posts = scrape_subreddit('python', limit=5)
    for post in posts:
        print(f"Title: {post['title']}")
        print(f"Content: {post['content']}\n")
