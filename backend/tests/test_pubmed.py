"""
Sanity check tests for the PubMed service.

These tests actually call the PubMed API to verify our parsing works.
Run with: pytest tests/test_pubmed.py -v

Note: These are integration tests that require internet access.
"""

import pytest
from app.services.pubmed import PubMedClient, fetch_pubmed_articles


# =============================================================================
# SANITY CHECK: Fetch one real abstract and verify parsing
# =============================================================================

@pytest.mark.asyncio
async def test_fetch_single_abstract():
    """
    Fetch a single well-known article and verify all fields are parsed correctly.
    
    We use a specific PMID that we know exists and has all fields populated.
    PMID 11015613 is a classic paper: "Effect of ACE inhibitors on mortality..."
    """
    client = PubMedClient()
    
    try:
        # Fetch a specific known article
        articles = await client.fetch_abstracts(["11015613"])
        
        # Should get exactly one article back
        assert len(articles) == 1, f"Expected 1 article, got {len(articles)}"
        
        article = articles[0]
        
        # Verify all required fields are present and non-empty
        assert article["pmid"] == "11015613", f"Wrong PMID: {article['pmid']}"
        assert article["title"], "Title should not be empty"
        assert article["abstract"], "Abstract should not be empty"
        assert len(article["abstract"]) > 100, "Abstract seems too short"
        
        # Verify optional fields exist (may be None, but key should exist)
        assert "authors" in article, "Authors field missing"
        assert "journal" in article, "Journal field missing"
        assert "publication_date" in article, "Publication date field missing"
        
        # Print for manual verification
        print(f"\n✅ Successfully fetched article:")
        print(f"   PMID: {article['pmid']}")
        print(f"   Title: {article['title'][:80]}...")
        print(f"   Abstract length: {len(article['abstract'])} chars")
        print(f"   Authors: {len(article.get('authors', []))} authors")
        print(f"   Journal: {article.get('journal', 'N/A')}")
        print(f"   Date: {article.get('publication_date', 'N/A')}")
        
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_search_returns_pmids():
    """
    Test that search returns a list of PMIDs.
    """
    client = PubMedClient()
    
    try:
        # Search for a common medical term
        pmids = await client.search("hypertension treatment", max_results=5)
        
        # Should get some results
        assert len(pmids) > 0, "Search returned no results"
        assert len(pmids) <= 5, f"Got more results than requested: {len(pmids)}"
        
        # PMIDs should be numeric strings
        for pmid in pmids:
            assert pmid.isdigit(), f"Invalid PMID format: {pmid}"
        
        print(f"\n✅ Search returned {len(pmids)} PMIDs: {pmids}")
        
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_search_and_fetch_integration():
    """
    Test the full search_and_fetch flow with a small query.
    """
    client = PubMedClient()
    
    try:
        # Search and fetch a small number of articles
        articles = await client.search_and_fetch(
            "ACE inhibitors heart failure",
            max_results=3
        )
        
        # Should get some articles (might be less than 3 if some lack abstracts)
        assert len(articles) > 0, "No articles returned"
        
        # Verify each article has required fields
        for article in articles:
            assert article["pmid"], "PMID missing"
            assert article["title"], "Title missing"
            assert article["abstract"], "Abstract missing"
        
        print(f"\n✅ search_and_fetch returned {len(articles)} articles:")
        for a in articles:
            print(f"   - {a['pmid']}: {a['title'][:60]}...")
        
    finally:
        await client.close()


@pytest.mark.asyncio
async def test_convenience_function():
    """
    Test the module-level convenience function.
    """
    articles = await fetch_pubmed_articles("diabetes mellitus", max_results=2)
    
    assert len(articles) > 0, "No articles returned"
    
    print(f"\n✅ Convenience function returned {len(articles)} articles")


@pytest.mark.asyncio
async def test_empty_search_returns_empty_list():
    """
    Test that a search with no results returns an empty list (not an error).
    """
    client = PubMedClient()
    
    try:
        # Search for something that won't exist
        pmids = await client.search("xyznonexistentterm12345", max_results=10)
        
        # Should return empty list, not raise an error
        assert pmids == [], f"Expected empty list, got: {pmids}"
        
        print("\n✅ Empty search correctly returned empty list")
        
    finally:
        await client.close()


# =============================================================================
# Run directly for quick sanity check
# =============================================================================

if __name__ == "__main__":
    import asyncio
    
    async def run_sanity_check():
        """Quick sanity check without pytest."""
        print("=" * 60)
        print("PubMed Service Sanity Check")
        print("=" * 60)
        
        client = PubMedClient()
        
        try:
            # Test 1: Fetch known article
            print("\n1. Fetching known article (PMID 11015613)...")
            articles = await client.fetch_abstracts(["11015613"])
            
            if articles:
                a = articles[0]
                print(f"   ✅ Got article: {a['title'][:60]}...")
                print(f"   ✅ Abstract: {len(a['abstract'])} chars")
            else:
                print("   ❌ Failed to fetch article")
                return
            
            # Test 2: Search
            print("\n2. Searching for 'heart failure treatment'...")
            pmids = await client.search("heart failure treatment", max_results=5)
            print(f"   ✅ Found {len(pmids)} PMIDs")
            
            # Test 3: Full flow
            print("\n3. Running search_and_fetch...")
            articles = await client.search_and_fetch("ACE inhibitors", max_results=3)
            print(f"   ✅ Got {len(articles)} complete articles")
            
            print("\n" + "=" * 60)
            print("All sanity checks passed! ✅")
            print("=" * 60)
            
        finally:
            await client.close()
    
    asyncio.run(run_sanity_check())
