"""
PubMed E-utilities API client.

WHAT THIS DOES:
Fetches medical research abstracts from PubMed (the NIH's database of 35M+ articles).

HOW IT WORKS:
PubMed provides the E-utilities API with two key endpoints:
1. esearch — Search by term, returns list of PMIDs (PubMed IDs)
2. efetch — Fetch full article details by PMIDs

RATE LIMITS:
- Without API key: 3 requests/second
- With API key: 10 requests/second
We implement rate limiting to stay under these limits.

USAGE:
    client = PubMedClient()
    articles = await client.search_and_fetch("ACE inhibitors heart failure", max_results=100)
    # Returns list of dicts with title, abstract, authors, etc.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional
from xml.etree import ElementTree as ET

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

# PubMed E-utilities base URL
EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedClient:
    """
    Async client for PubMed E-utilities API.
    
    Handles searching for articles and fetching their full details,
    with built-in rate limiting to respect PubMed's usage policies.
    """
    
    def __init__(self):
        settings = get_settings()
        self.api_key = settings.pubmed_api_key or None
        
        # Rate limiting: 3 req/sec without key, 10 req/sec with key
        self.request_delay = 0.1 if self.api_key else 0.34  # seconds between requests
        self._last_request_time = 0.0
        
        # HTTP client with timeout
        self._client: Optional[httpx.AsyncClient] = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client (lazy initialization)."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def _rate_limit(self):
        """
        Wait if needed to respect rate limits.
        
        This ensures we don't make requests faster than PubMed allows.
        Simple but effective — just track time since last request.
        """
        now = asyncio.get_event_loop().time()
        time_since_last = now - self._last_request_time
        
        if time_since_last < self.request_delay:
            await asyncio.sleep(self.request_delay - time_since_last)
        
        self._last_request_time = asyncio.get_event_loop().time()
    
    def _build_params(self, **kwargs) -> dict:
        """Build request params, adding API key if available."""
        params = {k: v for k, v in kwargs.items() if v is not None}
        if self.api_key:
            params["api_key"] = self.api_key
        return params
    
    # =========================================================================
    # SEARCH — Find articles matching a query
    # =========================================================================
    
    async def search(self, term: str, max_results: int = 100) -> list[str]:
        """
        Search PubMed and return list of PMIDs.
        
        WHAT IT DOES:
        Sends search query to PubMed's esearch endpoint.
        Returns PMIDs (unique identifiers) for matching articles.
        
        Args:
            term: Search query (e.g., "ACE inhibitors heart failure")
            max_results: Maximum number of PMIDs to return
            
        Returns:
            List of PMID strings (e.g., ["12345678", "23456789"])
            
        Example:
            pmids = await client.search("diabetes treatment", max_results=50)
            # Returns: ["38123456", "38123457", ...]
        """
        await self._rate_limit()
        
        client = await self._get_client()
        
        params = self._build_params(
            db="pubmed",           # Search PubMed database
            term=term,             # The search query
            retmax=max_results,    # Maximum results to return
            retmode="json",        # Return JSON format
            sort="relevance",      # Sort by relevance (not date)
        )
        
        try:
            response = await client.get(f"{EUTILS_BASE}/esearch.fcgi", params=params)
            response.raise_for_status()
            
            data = response.json()
            pmids = data.get("esearchresult", {}).get("idlist", [])
            
            logger.info(f"PubMed search '{term}' returned {len(pmids)} results")
            return pmids
            
        except httpx.HTTPError as e:
            logger.error(f"PubMed search failed: {e}")
            raise
    
    # =========================================================================
    # FETCH — Get full article details
    # =========================================================================
    
    async def fetch_abstracts(self, pmids: list[str]) -> list[dict]:
        """
        Fetch full article details for given PMIDs.
        
        WHAT IT DOES:
        Sends PMIDs to PubMed's efetch endpoint.
        Returns full article metadata: title, abstract, authors, etc.
        
        Args:
            pmids: List of PubMed IDs to fetch
            
        Returns:
            List of dicts, each containing:
            - pmid: str
            - title: str
            - abstract: str
            - authors: list[str]
            - journal: str
            - publication_date: date or None
            
        Note:
            PubMed returns XML, not JSON. We parse it into clean dicts.
            Articles without abstracts are skipped (common for older articles).
        """
        if not pmids:
            return []
        
        await self._rate_limit()
        
        client = await self._get_client()
        
        # efetch accepts comma-separated PMIDs
        params = self._build_params(
            db="pubmed",
            id=",".join(pmids),
            retmode="xml",         # XML format (more complete than JSON)
            rettype="abstract",    # We want abstracts
        )
        
        try:
            response = await client.get(f"{EUTILS_BASE}/efetch.fcgi", params=params)
            response.raise_for_status()
            
            # Parse XML response
            articles = self._parse_pubmed_xml(response.text)
            
            logger.info(f"Fetched {len(articles)} articles from PubMed")
            return articles
            
        except httpx.HTTPError as e:
            logger.error(f"PubMed fetch failed: {e}")
            raise
    
    def _parse_pubmed_xml(self, xml_text: str) -> list[dict]:
        """
        Parse PubMed XML response into list of article dicts.
        
        PubMed XML structure (simplified):
        <PubmedArticleSet>
          <PubmedArticle>
            <MedlineCitation>
              <PMID>12345678</PMID>
              <Article>
                <ArticleTitle>Effect of ACE inhibitors...</ArticleTitle>
                <Abstract>
                  <AbstractText>Background: ...</AbstractText>
                </Abstract>
                <AuthorList>
                  <Author>
                    <LastName>Smith</LastName>
                    <ForeName>John</ForeName>
                  </Author>
                </AuthorList>
                <Journal>
                  <Title>Journal of Cardiology</Title>
                </Journal>
              </Article>
              <DateCompleted>
                <Year>2023</Year>
                <Month>05</Month>
                <Day>15</Day>
              </DateCompleted>
            </MedlineCitation>
          </PubmedArticle>
        </PubmedArticleSet>
        """
        articles = []
        
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error(f"Failed to parse PubMed XML: {e}")
            return []
        
        # Find all PubmedArticle elements
        for article_elem in root.findall(".//PubmedArticle"):
            try:
                article = self._parse_single_article(article_elem)
                if article:  # Only add if we got valid data
                    articles.append(article)
            except Exception as e:
                # Log but don't fail — some articles may have weird formatting
                logger.warning(f"Failed to parse article: {e}")
                continue
        
        return articles
    
    def _parse_single_article(self, article_elem: ET.Element) -> Optional[dict]:
        """
        Parse a single PubmedArticle element into a dict.
        
        Returns None if the article doesn't have an abstract
        (we need abstracts for embedding/search).
        """
        citation = article_elem.find(".//MedlineCitation")
        if citation is None:
            return None
        
        # PMID (required)
        pmid_elem = citation.find(".//PMID")
        if pmid_elem is None or not pmid_elem.text:
            return None
        pmid = pmid_elem.text
        
        # Article element contains most of what we need
        article = citation.find(".//Article")
        if article is None:
            return None
        
        # Title (required)
        title_elem = article.find(".//ArticleTitle")
        title = title_elem.text if title_elem is not None else None
        if not title:
            return None
        
        # Abstract (required — we skip articles without abstracts)
        abstract = self._extract_abstract(article)
        if not abstract:
            logger.debug(f"Skipping PMID {pmid}: no abstract")
            return None
        
        # Authors (optional)
        authors = self._extract_authors(article)
        
        # Journal (optional)
        journal_elem = article.find(".//Journal/Title")
        journal = journal_elem.text if journal_elem is not None else None
        
        # Publication date (optional)
        pub_date = self._extract_date(citation)
        
        return {
            "pmid": pmid,
            "title": title,
            "abstract": abstract,
            "authors": authors,
            "journal": journal,
            "publication_date": pub_date,
        }
    
    def _extract_abstract(self, article_elem: ET.Element) -> Optional[str]:
        """
        Extract abstract text from Article element.
        
        Handles both simple abstracts and structured abstracts
        (which have multiple AbstractText elements with labels).
        """
        abstract_elem = article_elem.find(".//Abstract")
        if abstract_elem is None:
            return None
        
        # Some abstracts have multiple sections (Background, Methods, Results, etc.)
        abstract_texts = abstract_elem.findall(".//AbstractText")
        
        if not abstract_texts:
            return None
        
        parts = []
        for text_elem in abstract_texts:
            # Structured abstracts have a "Label" attribute
            label = text_elem.get("Label")
            text = text_elem.text or ""
            
            if label:
                parts.append(f"{label}: {text}")
            else:
                parts.append(text)
        
        return " ".join(parts).strip() or None
    
    def _extract_authors(self, article_elem: ET.Element) -> list[str]:
        """
        Extract author names from Article element.
        
        Returns list of "FirstName LastName" strings.
        """
        authors = []
        
        for author_elem in article_elem.findall(".//AuthorList/Author"):
            last_name = author_elem.find("LastName")
            fore_name = author_elem.find("ForeName")
            
            if last_name is not None and last_name.text:
                name = last_name.text
                if fore_name is not None and fore_name.text:
                    name = f"{fore_name.text} {name}"
                authors.append(name)
        
        return authors
    
    def _extract_date(self, citation_elem: ET.Element) -> Optional[datetime]:
        """
        Extract publication date from MedlineCitation element.
        
        Tries multiple date fields in order of preference.
        """
        # Try different date elements in order of preference
        date_paths = [
            ".//Article/Journal/JournalIssue/PubDate",
            ".//DateCompleted",
            ".//DateRevised",
        ]
        
        for path in date_paths:
            date_elem = citation_elem.find(path)
            if date_elem is not None:
                year = date_elem.find("Year")
                month = date_elem.find("Month")
                day = date_elem.find("Day")
                
                if year is not None and year.text:
                    try:
                        y = int(year.text)
                        m = int(month.text) if month is not None and month.text.isdigit() else 1
                        d = int(day.text) if day is not None and day.text.isdigit() else 1
                        return datetime(y, m, d).date()
                    except (ValueError, TypeError):
                        continue
        
        return None
    
    # =========================================================================
    # CONVENIENCE METHOD — Search and fetch in one call
    # =========================================================================
    
    async def search_and_fetch(self, term: str, max_results: int = 100) -> list[dict]:
        """
        Search PubMed and fetch all matching abstracts in one call.
        
        WHAT IT DOES:
        1. Searches PubMed for articles matching the term
        2. Fetches full details for all matching PMIDs
        3. Returns parsed article data ready for database insertion
        
        This is the main method you'll use from the API route.
        
        Args:
            term: Search query (e.g., "ACE inhibitors heart failure")
            max_results: Maximum number of articles to return
            
        Returns:
            List of article dicts (see fetch_abstracts for structure)
            
        Example:
            client = PubMedClient()
            articles = await client.search_and_fetch(
                "diabetes type 2 treatment",
                max_results=100
            )
            for article in articles:
                print(f"{article['pmid']}: {article['title']}")
        """
        # Step 1: Search for PMIDs
        pmids = await self.search(term, max_results)
        
        if not pmids:
            logger.info(f"No results found for '{term}'")
            return []
        
        # Step 2: Fetch abstracts in batches (PubMed recommends max 200 per request)
        batch_size = 200
        all_articles = []
        
        for i in range(0, len(pmids), batch_size):
            batch = pmids[i:i + batch_size]
            articles = await self.fetch_abstracts(batch)
            all_articles.extend(articles)
        
        return all_articles
    
    async def close(self):
        """Close the HTTP client (call when done)."""
        if self._client:
            await self._client.aclose()
            self._client = None


# =============================================================================
# MODULE-LEVEL CONVENIENCE FUNCTION
# =============================================================================

async def fetch_pubmed_articles(term: str, max_results: int = 100) -> list[dict]:
    """
    Convenience function to fetch PubMed articles without managing client lifecycle.
    
    WHEN TO USE:
    - Quick one-off fetches
    - In API routes where you don't need to reuse the client
    
    Example:
        articles = await fetch_pubmed_articles("heart failure treatment", max_results=50)
    """
    client = PubMedClient()
    try:
        return await client.search_and_fetch(term, max_results)
    finally:
        await client.close()
