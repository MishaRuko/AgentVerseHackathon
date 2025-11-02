"""
Google Scholar scraper - scrapes search results from Google Scholar
"""

import requests
from bs4 import BeautifulSoup
from typing import List, Dict, Any
import time
import random


def scrape_scholar_search(query: str, num_results: int = 5) -> List[Dict[str, Any]]:
    """
    Scrape Google Scholar search results for a given query.
    
    Args:
        query: The search query (research question/topic)
        num_results: Number of results to retrieve (default: 5)
    
    Returns:
        List of paper dictionaries with title, authors, abstract, url, year
    """
    # Construct Google Scholar search URL
    search_url = f"https://scholar.google.com/scholar?q={query.replace(' ', '+')}"
    
    # Use multiple user agents and rotate them
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    ]
    
    headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }
    
    try:
        # Add a random delay to appear more human-like
        time.sleep(random.uniform(1, 3))
        
        response = requests.get(search_url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"Failed to fetch Google Scholar. Status code: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        papers = []
        count = 0
        
        # Find all paper results (each is in a div with class 'gs_ri')
        for item in soup.find_all('div', class_='gs_ri'):
            if count >= num_results:
                break
            
            try:
                # Extract title
                title_tag = item.find('h3', class_='gs_rt')
                if not title_tag:
                    continue
                    
                # Remove citation markers like [PDF], [HTML], etc.
                for span in title_tag.find_all('span', class_='gs_ctc'):
                    span.decompose()
                
                title = title_tag.get_text(strip=True)
                
                # Extract URL
                link_tag = title_tag.find('a')
                url = link_tag['href'] if link_tag and link_tag.has_attr('href') else ''
                
                # Extract authors and publication info
                authors_tag = item.find('div', class_='gs_a')
                authors_text = authors_tag.get_text(strip=True) if authors_tag else ''
                
                # Parse authors (format: "Author1, Author2 - Journal, Year")
                authors = []
                year = ''
                if authors_text:
                    if ' - ' in authors_text:
                        author_part = authors_text.split(' - ')[0]
                        pub_part = authors_text.split(' - ')[-1]
                        authors = [a.strip() for a in author_part.split(',') if a.strip()]
                        # Try to extract year
                        import re
                        year_match = re.search(r'\b(19|20)\d{2}\b', pub_part)
                        if year_match:
                            year = year_match.group(0)
                    else:
                        authors = [a.strip() for a in authors_text.split(',') if a.strip()]
                
                # Extract abstract/snippet
                abstract_tag = item.find('div', class_='gs_rs')
                abstract = abstract_tag.get_text(strip=True) if abstract_tag else ''
                
                # Extract citation info if available
                citations_tag = item.find('div', class_='gs_fl')
                citations = 0
                if citations_tag:
                    cited_by = citations_tag.find('a', string=lambda text: text and 'Cited by' in text)
                    if cited_by:
                        import re
                        cit_match = re.search(r'Cited by (\d+)', cited_by.get_text())
                        if cit_match:
                            citations = int(cit_match.group(1))
                
                paper = {
                    'title': title,
                    'authors': authors,
                    'year': year,
                    'abstract': abstract,
                    'url': url,
                    'citations': citations,
                    'source': 'Google Scholar'
                }
                
                papers.append(paper)
                count += 1
                
            except Exception as e:
                print(f"Error parsing paper: {e}")
                continue
        
        return papers
        
    except requests.exceptions.RequestException as e:
        print(f"Network error scraping Google Scholar: {e}")
        return []
    except Exception as e:
        print(f"Error scraping Google Scholar: {e}")
        return []


def scrape_scholar_url(url: str) -> List[Dict[str, Any]]:
    """
    Scrape a specific Google Scholar URL (search results page).
    
    Args:
        url: The Google Scholar URL to scrape
    
    Returns:
        List of paper dictionaries
    """
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    ]
    
    headers = {
        "User-Agent": random.choice(user_agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    
    try:
        time.sleep(random.uniform(1, 3))
        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code != 200:
            print(f"Failed to fetch URL. Status code: {response.status_code}")
            return []
        
        soup = BeautifulSoup(response.text, 'html.parser')
        papers = []
        
        for item in soup.find_all('div', class_='gs_ri'):
            try:
                title_tag = item.find('h3', class_='gs_rt')
                if not title_tag:
                    continue
                
                for span in title_tag.find_all('span', class_='gs_ctc'):
                    span.decompose()
                
                title = title_tag.get_text(strip=True)
                link_tag = title_tag.find('a')
                paper_url = link_tag['href'] if link_tag and link_tag.has_attr('href') else ''
                
                authors_tag = item.find('div', class_='gs_a')
                authors_text = authors_tag.get_text(strip=True) if authors_tag else ''
                
                abstract_tag = item.find('div', class_='gs_rs')
                abstract = abstract_tag.get_text(strip=True) if abstract_tag else ''
                
                paper = {
                    'title': title,
                    'authors': authors_text,
                    'abstract': abstract,
                    'url': paper_url,
                    'source': 'Google Scholar'
                }
                
                papers.append(paper)
                
            except Exception as e:
                print(f"Error parsing paper: {e}")
                continue
        
        return papers
        
    except Exception as e:
        print(f"Error scraping URL: {e}")
        return []
