"""
Claim Extractor Service.

WHAT THIS DOES:
Breaks down a generated answer into atomic, verifiable claims.
This is the first step of the Trust Layer.

WHY THIS MATTERS:
You can't verify a paragraph — you verify individual claims.
By extracting claims, we can check each one against the evidence separately.

EXAMPLE:
    Answer: "ACE inhibitors reduce mortality in heart failure patients. 
             They are typically well-tolerated with few side effects."
    
    Extracted claims:
    1. "ACE inhibitors reduce mortality" (span: 0-32)
    2. "This applies to heart failure patients" (span: 33-66)  
    3. "ACE inhibitors are well-tolerated" (span: 67-102)
    4. "ACE inhibitors have few side effects" (span: 103-140)

STRUCTURED OUTPUT:
We use OpenAI's JSON mode to get properly formatted claims.
Each claim includes:
- text: The claim itself
- span_start/span_end: Character positions in the original answer
- cited_pmids: Which sources were cited for this claim

USAGE:
    extractor = ClaimExtractor()
    claims = await extractor.extract(answer_text)
"""

import json
import logging
import re
from openai import AsyncOpenAI

from app.config import get_settings

logger = logging.getLogger(__name__)

# Use gpt-4o-mini for claim extraction (cheaper, fast enough for this task)
EXTRACTION_MODEL = "gpt-4o-mini"

EXTRACTION_PROMPT = """You are a claim extraction system. Your job is to break down medical text into atomic, verifiable claims.

RULES:
1. Extract EVERY factual claim from the text
2. Each claim should be a single, verifiable statement
3. Include the character positions (span_start, span_end) where each claim appears
4. Extract any PMID citations associated with each claim
5. Claims should be complete sentences that stand alone

IMPORTANT:
- "ACE inhibitors reduce mortality in heart failure" is ONE claim
- "ACE inhibitors reduce mortality" and "this applies to heart failure patients" are TWO claims
- Be thorough — extract ALL claims, even small ones

OUTPUT FORMAT (JSON):
{
  "claims": [
    {
      "text": "The exact claim text",
      "span_start": 0,
      "span_end": 50,
      "cited_pmids": ["12345", "67890"]
    }
  ]
}

Extract claims from the following text:"""


class ExtractedClaim:
    """A claim extracted from the answer text."""
    
    def __init__(self, text: str, span_start: int, span_end: int, cited_pmids: list[str]):
        self.text = text
        self.span_start = span_start
        self.span_end = span_end
        self.cited_pmids = cited_pmids
    
    def __repr__(self):
        return f"Claim({self.text[:50]}..., pmids={self.cited_pmids})"


class ClaimExtractor:
    """
    Extracts atomic claims from generated answers.
    
    This is the first step in the Trust Layer pipeline:
    Answer → [ClaimExtractor] → Claims → AttributionScorer → ...
    """
    
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    async def extract(self, answer: str) -> list[ExtractedClaim]:
        """
        Extract claims from a generated answer.
        
        Args:
            answer: The generated answer text (with [PMID:xxxxx] citations)
            
        Returns:
            List of ExtractedClaim objects
            
        Example:
            extractor = ClaimExtractor()
            claims = await extractor.extract(
                "ACE inhibitors reduce mortality [PMID:12345]. They are well-tolerated."
            )
            # Returns:
            # [
            #   ExtractedClaim(text="ACE inhibitors reduce mortality", cited_pmids=["12345"]),
            #   ExtractedClaim(text="ACE inhibitors are well-tolerated", cited_pmids=[]),
            # ]
        """
        logger.info(f"Extracting claims from answer ({len(answer)} chars)")
        
        # Call OpenAI with JSON mode
        response = await self.client.chat.completions.create(
            model=EXTRACTION_MODEL,
            messages=[
                {"role": "system", "content": EXTRACTION_PROMPT},
                {"role": "user", "content": answer},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,  # Low temperature for consistent extraction
        )
        
        # Parse the response
        try:
            result = json.loads(response.choices[0].message.content)
            claims_data = result.get("claims", [])
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse claim extraction response: {e}")
            return []
        
        # Convert to ExtractedClaim objects
        claims = []
        for i, claim_data in enumerate(claims_data):
            claim = ExtractedClaim(
                text=claim_data.get("text", ""),
                span_start=claim_data.get("span_start", 0),
                span_end=claim_data.get("span_end", 0),
                cited_pmids=claim_data.get("cited_pmids", []),
            )
            claims.append(claim)
        
        # If LLM didn't extract PMIDs well, try to extract them ourselves
        claims = self._ensure_pmids_extracted(answer, claims)
        
        logger.info(f"Extracted {len(claims)} claims")
        return claims
    
    def _ensure_pmids_extracted(
        self, 
        answer: str, 
        claims: list[ExtractedClaim]
    ) -> list[ExtractedClaim]:
        """
        Fallback: Extract PMIDs from the answer text if the LLM missed them.
        
        Sometimes the LLM doesn't properly associate citations with claims.
        This method uses regex to find PMIDs near each claim's position.
        """
        # Find all PMIDs in the answer with their positions
        pmid_pattern = r'\[PMID:(\d+)\]'
        pmid_matches = list(re.finditer(pmid_pattern, answer))
        
        for claim in claims:
            if not claim.cited_pmids:
                # Find PMIDs near this claim's span
                nearby_pmids = []
                for match in pmid_matches:
                    pmid_pos = match.start()
                    # If PMID is within 100 chars after the claim, associate it
                    if claim.span_start <= pmid_pos <= claim.span_end + 100:
                        nearby_pmids.append(match.group(1))
                
                if nearby_pmids:
                    claim.cited_pmids = nearby_pmids
        
        return claims


# =============================================================================
# CONVENIENCE FUNCTION
# =============================================================================

async def extract_claims(answer: str) -> list[ExtractedClaim]:
    """
    Convenience function to extract claims from an answer.
    
    Example:
        claims = await extract_claims("ACE inhibitors reduce mortality [PMID:12345].")
    """
    extractor = ClaimExtractor()
    return await extractor.extract(answer)
