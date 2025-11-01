import requests
from bs4 import BeautifulSoup

def scrape_article(url: str):
    """
    Scrapes a news article for its title and content.

    Args:
        url: The URL of the news article to scrape.

    Returns:
        A dictionary containing the title and content of the article,
        or None if scraping fails.
    """
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Error fetching article from {url}: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')
    
    # Find title
    title_elem = soup.find('h1')
    title = title_elem.get_text(strip=True) if title_elem else "No title found"

    # Find content - this is a guess and might need to be adapted for different sites
    # Look for a common container for article text
    article_body = soup.find('div', {'id': 'mw-content-text'})

    if not article_body:
        article_body = soup.find('body') # Fallback to the whole body

    paragraphs = article_body.find_all('p') if article_body else []
    content = '\n'.join([p.get_text(strip=True) for p in paragraphs])

    return {'title': title, 'content': content}

if __name__ == '__main__':
    # Example usage with a Simple English Wikipedia article
    article = scrape_article('https://simple.wikipedia.org/wiki/Python_(programming_language)')
    if article:
        print(f"Title: {article['title']}")
        print(f"Content: {article['content']}")
