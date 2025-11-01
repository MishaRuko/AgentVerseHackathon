import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

def scrape_page(url: str, timeout: int = 10):
    """
    Scrape a generic webpage.

    Args:
        url: full URL to scrape (http/https)
        timeout: request timeout in seconds

    Returns:
        {
            'url': <final_url_after_redirects>,
            'status_code': <http status>,
            'title': <page <title> text or ''>,
            'text': <visible main text, joined into paragraphs>,
            'links': [ list of absolute URLs found in <a href=...> ]
        }

    Notes:
        - This does a simple static fetch. It will NOT execute JavaScript.
        - This respects normal HTTP GET. It does not handle login, cookies, etc.
    """

    headers = {
        "User-Agent": "influx-general-scraper/1.0 (+research use)"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
    except requests.exceptions.RequestException as e:
        print(f"Request error for {url}: {e}")
        return {}

    result = {
        "url": resp.url,  # after redirects
        "status_code": resp.status_code,
        "title": "",
        "text": "",
        "links": []
    }

    # if non-200, we still return metadata so caller can log it
    if resp.status_code != 200 or "text" not in resp.headers.get("Content-Type", ""):
        return result

    soup = BeautifulSoup(resp.text, "html.parser")

    # 1. Get <title>
    title_tag = soup.find("title")
    if title_tag and title_tag.text:
        result["title"] = title_tag.text.strip()

    # 2. Remove junk that we never want in text extraction
    # things like nav/aside/footer could be content sometimes,
    # but script/style are never useful, so always drop those.
    for tag in soup(["script", "style", "noscript", "template"]):
        tag.decompose()

    # Optionally also drop things that are clearly layout/boilerplate.
    # You can expand this list later.
    boilerplate_selectors = [
        "header", "nav", "footer", "form", "button", "input",
        ".sidebar", ".advertisement", ".ads", "#ads", ".ad-container"
    ]
    for sel in boilerplate_selectors:
        for tag in soup.select(sel):
            tag.decompose()

    # 3. Extract visible text
    # Strategy: grab block-level tags in main body (p, h1..h6, li, article, section)
    # Join them with double newlines so we keep paragraph boundaries.
    text_chunks = []

    # Try narrowing to <main> or <article> first, fall back to whole body.
    main_region = soup.find("main")
    if not main_region:
        main_region = soup.find("article")
    if not main_region:
        main_region = soup.body if soup.body else soup

    # Collect paragraphs / headings / list items
    for tag in main_region.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "li", "section"]):
        # get visible text
        txt = tag.get_text(separator=" ", strip=True)
        # filter out super short garbage like lone bullets
        if txt and len(txt.split()) > 2:
            text_chunks.append(txt)

    result["text"] = "\n\n".join(text_chunks)

    # 4. Collect all links, convert to absolute, dedupe
    links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        # skip empty anchors, mailto, javascript:
        if href.startswith("#"):
            continue
        if href.startswith("mailto:") or href.startswith("javascript:"):
            continue

        abs_url = urljoin(resp.url, href)

        # we can also skip if it's not http/https
        parsed = urlparse(abs_url)
        if parsed.scheme in ["http", "https"]:
            links.add(abs_url)

    result["links"] = sorted(list(links))

    return result


if __name__ == "__main__":
    test_url = "https://www.python.org/"
    data = scrape_page(test_url)

    print("Final URL:", data["url"])
    print("HTTP Status:", data["status_code"])
    print("\nPage Title:", data["title"])
    print("\nExtracted Text:\n")
    print(data["text"][:1000], "..." if len(data["text"]) > 1000 else "")
    print("\nLinks:")
    for link in data["links"]:
        print("-", link)
