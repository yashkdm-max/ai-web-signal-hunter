import time
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser
from typing import List, Dict, Callable, Optional

import requests
import trafilatura
from bs4 import BeautifulSoup

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

from src.config import USER_AGENT, REQUEST_DELAY_SECONDS

BLOCKED_DOMAINS = {
    "linkedin.com", "facebook.com", "instagram.com", "twitter.com",
    "x.com", "tiktok.com", "pinterest.com", "quora.com", "youtube.com"
}


class ResponsibleCrawler:
    def __init__(self):
        self.robots_cache: Dict[str, Optional[RobotFileParser]] = {}
        self.seen_hashes = set()
        self.seen_urls = set()

    def _get_domain(self, url: str) -> str:
        netloc = urlparse(url).netloc.lower()
        return netloc.replace("www.", "")

    def _is_allowed_by_robots(self, url: str) -> bool:
        parsed = urlparse(url)
        base_url = f"{parsed.scheme}://{parsed.netloc}"
        domain = self._get_domain(url)

        if any(blocked in domain for blocked in BLOCKED_DOMAINS):
            return False

        if base_url not in self.robots_cache:
            rp = RobotFileParser()
            rp.set_url(f"{base_url}/robots.txt")
            try:
                resp = requests.get(
                    f"{base_url}/robots.txt",
                    headers={"User-Agent": USER_AGENT},
                    timeout=4
                )
                if resp.status_code == 200:
                    rp.parse(resp.text.splitlines())
                    self.robots_cache[base_url] = rp
                else:
                    self.robots_cache[base_url] = None
            except Exception:
                self.robots_cache[base_url] = None

        rp = self.robots_cache[base_url]
        if rp is None:
            return True
        return rp.can_fetch(USER_AGENT, url)

    def _clean_topic_to_search_terms(self, topic: str) -> str:
        """Strips question words so search engines return richer discussions."""
        stop_prefixes = [
            "what features are people requesting from ",
            "what problems do small businesses mention about ",
            "what demand or complaints appear around ",
            "what are ", "what is ", "how do "
        ]
        cleaned = topic.strip().rstrip("?")
        lower = cleaned.lower()
        for prefix in stop_prefixes:
            if lower.startswith(prefix):
                cleaned = cleaned[len(prefix):]
                break
        return cleaned.strip()

    def discover_urls(
        self,
        topic: str,
        keywords: str,
        target_count: int,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> List[Dict[str, str]]:
        core_subject = self._clean_topic_to_search_terms(topic)

        queries = [
            topic,
            f"{core_subject} feature requests wishlist",
            f"{core_subject} complaints problems reddit",
            f"{core_subject} reviews pros cons pricing",
            f"best {core_subject} missing features forum"
        ]
        if keywords.strip():
            for kw in keywords.split(","):
                if kw.strip():
                    queries.insert(1, f"{core_subject} {kw.strip()}")

        discovered = []
        seen = set()
        max_candidates = max(target_count * 3, 60)

        for q in queries:
            if len(discovered) >= max_candidates:
                break
            if progress_callback:
                progress_callback(f"Searching web for: '{q}'...")
            try:
                with DDGS() as ddgs:
                    results = list(ddgs.text(q, max_results=20))
                    for r in results:
                        url = r.get("href") or r.get("link") or ""
                        if url and url not in seen and url.startswith("http"):
                            seen.add(url)
                            discovered.append({
                                "url": url,
                                "title": r.get("title", "Untitled Page")
                            })
            except Exception as e:
                if progress_callback:
                    progress_callback(f"Search warning for '{q}': {str(e)[:60]}")
            time.sleep(0.8)

        if progress_callback:
            progress_callback(f"Found {len(discovered)} candidate URLs to inspect.")
        return discovered

    def _extract_clean_text(self, html: str) -> str:
        # Primary extractor: trafilatura
        text = trafilatura.extract(
            html,
            include_comments=True,
            include_tables=True,
            no_fallback=False
        )
        if text and len(text.strip()) >= 200:
            return text.strip()

        # Secondary fallback: BeautifulSoup paragraph & list extraction
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        blocks = [
            el.get_text(" ", strip=True)
            for el in soup.find_all(["p", "li", "h1", "h2", "h3"])
            if len(el.get_text(strip=True)) > 35
        ]
        return "\n".join(blocks).strip()

    def crawl_and_clean(
        self,
        topic: str,
        keywords: str = "",
        max_pages: int = 25,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> List[Dict[str, str]]:
        candidates = self.discover_urls(topic, keywords, max_pages, progress_callback)
        if not candidates:
            return []

        crawled_pages = []
        domain_counts: Dict[str, int] = {}
        browser_headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36 "
                f"({USER_AGENT})"
            ),
            "Accept-Language": "en-US,en;q=0.9"
        }

        for item in candidates:
            if len(crawled_pages) >= max_pages:
                break

            url = item["url"]
            if url in self.seen_urls:
                continue
            self.seen_urls.add(url)

            domain = self._get_domain(url)
            max_per_domain = max(4, max_pages // 3)
            if domain_counts.get(domain, 0) >= max_per_domain:
                continue

            if not self._is_allowed_by_robots(url):
                continue

            if progress_callback:
                progress_callback(f"Crawling ({len(crawled_pages)+1}/{max_pages}): {domain} — {url[:50]}...")

            try:
                resp = requests.get(url, headers=browser_headers, timeout=8)
                if resp.status_code != 200:
                    continue
                if "text/html" not in resp.headers.get("Content-Type", ""):
                    continue

                cleaned_text = self._extract_clean_text(resp.text)
                if not cleaned_text or len(cleaned_text) < 200:
                    continue

                content_hash = hashlib.md5(cleaned_text[:1500].encode("utf-8")).hexdigest()
                if content_hash in self.seen_hashes:
                    continue
                self.seen_hashes.add(content_hash)

                metadata = trafilatura.extract_metadata(resp.text)
                title = (metadata.title if metadata and metadata.title else item["title"]).strip()

                crawled_pages.append({
                    "url": url,
                    "domain": domain,
                    "title": title,
                    "crawl_date": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
                    "text": cleaned_text[:4500]
                })
                domain_counts[domain] = domain_counts.get(domain, 0) + 1

                time.sleep(REQUEST_DELAY_SECONDS)

            except Exception:
                continue

        return crawled_pages