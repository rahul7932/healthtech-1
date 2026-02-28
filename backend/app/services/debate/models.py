"""
Debate Models — Data structures for the multi-agent debate system.

These dataclasses define the contract between debate components:
- AdvocateResponse: What each advocate produces
- DebateResult: The final output of a debate session
"""

from dataclasses import dataclass, field
from typing import Optional

from app.models.schemas import DocumentWithScore


@dataclass
class AdvocateResponse:
    """
    Response from a document advocate agent.
    
    Each advocate receives a subset of documents and argues
    why they best answer the query.
    """
    
    group_id: str
    """Identifier for this advocate group (e.g., 'group_1', 'group_2')"""
    
    documents: list[DocumentWithScore]
    """The documents this advocate was assigned"""
    
    argument: str
    """The advocate's argument for why these documents answer the query"""
    
    key_findings: list[str]
    """Bullet-point summary of key evidence from the documents"""
    
    confidence: float
    """Self-assessed confidence in this argument (0.0 to 1.0)"""
    
    cited_pmids: list[str]
    """PMIDs explicitly cited in the argument"""


@dataclass
class DebateRound:
    """
    A single round in a multi-round debate (Phase 2 scaffold).
    
    For Phase 1, we only have one round. Phase 2 will add
    cross-examination and rebuttal rounds.
    """
    
    round_number: int
    """Which round this is (1-indexed)"""
    
    round_type: str
    """Type of round: 'initial', 'cross_examination', 'rebuttal', 'closing'"""
    
    advocate_responses: list[AdvocateResponse]
    """Responses from all advocates in this round"""


@dataclass
class DebateResult:
    """
    Final result of a debate session.
    
    Contains the synthesized answer plus full audit trail
    of the debate process.
    """
    
    answer: str
    """The final synthesized answer with citations"""
    
    advocate_responses: list[AdvocateResponse]
    """All advocate responses from the debate"""
    
    synthesis_reasoning: str
    """Explanation of how the final answer was synthesized"""
    
    debate_transcript: str = ""
    """Full transcript of the debate (for audit/debugging)"""
    
    rounds: list[DebateRound] = field(default_factory=list)
    """All debate rounds (Phase 2 scaffold - Phase 1 has single round)"""
    
    metadata: dict = field(default_factory=dict)
    """Additional metadata (timing, token counts, etc.)"""
    
    @property
    def num_advocates(self) -> int:
        """Number of advocates that participated."""
        return len(self.advocate_responses)
    
    @property
    def all_cited_pmids(self) -> list[str]:
        """All unique PMIDs cited across all advocates."""
        pmids = set()
        for response in self.advocate_responses:
            pmids.update(response.cited_pmids)
        return sorted(pmids)
    
    @property
    def average_confidence(self) -> float:
        """Average confidence across all advocates."""
        if not self.advocate_responses:
            return 0.0
        return sum(r.confidence for r in self.advocate_responses) / len(self.advocate_responses)
