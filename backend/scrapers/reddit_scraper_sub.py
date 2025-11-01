import requests
import json
import time

def scrape_subreddit(subreddit: str, limit: int = 5):
    """
    Scrapes a subreddit for a given number of posts using the JSON API,
    including top-level comments for each post.

    Args:
        subreddit: The name of the subreddit to scrape.
        limit: The maximum number of posts to scrape.

    Returns:
        A list of dictionaries, where each dictionary represents a post
        and contains the title, content, and a list of comments.
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
            post_data = post['data']
            post_id = post_data['id']
            post_url = f"https://www.reddit.com/r/{subreddit}/comments/{post_id}/.json"
            
            # Fetch comments for each post
            try:
                time.sleep(1)  # avoid rate limiting
                comment_response = requests.get(post_url, headers=headers)
                comment_response.raise_for_status()
                comment_data = comment_response.json()
                
                # Extract top-level comments
                comments = []
                for comment in comment_data[1]['data']['children']:
                    if comment['kind'] == 't1':  # comment, not "more"
                        comments.append(comment['data']['body'])
            except requests.exceptions.RequestException as e:
                print(f"Error fetching comments for post {post_id}: {e}")
                comments = []

            posts.append({
                'title': post_data['title'],
                'content': post_data['selftext'],
                'comments': comments
            })

        return posts

    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error parsing JSON from subreddit {subreddit}: {e}")
        return []


if __name__ == '__main__':
    posts = scrape_subreddit('python', limit=3)
    for post in posts:
        print(f"\nTitle: {post['title']}")
        print(f"Content: {post['content']}")
        print("Comments:")
        for c in post['comments']:
            print(f"- {c}")
