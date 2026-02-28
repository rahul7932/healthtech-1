"""
Debate Protocols — Abstract base classes for extensible debate patterns.

WHAT THIS IS:
Scaffolding for Phase 2 of the debate system. Defines abstract interfaces
that allow different debate strategies to be implemented.

WHY ABSTRACT CLASSES:
- Enable swapping debate strategies without changing orchestration
- Support future debate patterns (cross-examination, rebuttals)
- Allow A/B testing of different advocate strategies
- Clean separation of concerns

PHASE 2 POSSIBILITIES:
- CrossExaminationProtocol: Advocates can challenge each other
- RebuttalRound: Advocates respond to criticism
- JuryProtocol: Multiple synthesizers vote on best answer
- IterativeRefinement: Multiple rounds of improvement

USAGE (Phase 2):
    class MyCustomAdvocate(BaseAdvocate):
        async def argue(self, query, docs) -> AdvocateResponse:
            # Custom logic
            pass
    
    class MyDebateProtocol(BaseDebateProtocol):
        async def run(self, query, docs, advocates) -> DebateResult:
            # Custom debate flow
            pass
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from app.models.schemas import DocumentWithScore
from app.services.debate.models import AdvocateResponse, DebateResult

if TYPE_CHECKING:
    pass


class BaseAdvocate(ABC):
    """
    Abstract base class for document advocates.
    
    Implement this to create custom advocate strategies.
    The default DocumentAdvocate in advocate.py implements this interface.
    """
    
    @property
    @abstractmethod
    def group_id(self) -> str:
        """Unique identifier for this advocate."""
        pass
    
    @abstractmethod
    async def argue(
        self,
        query: str,
        documents: list[DocumentWithScore],
    ) -> AdvocateResponse:
        """
        Construct an argument for the given documents.
        
        Args:
            query: The user's question
            documents: Documents assigned to this advocate
            
        Returns:
            AdvocateResponse with the argument and metadata
        """
        pass


class BaseDebateProtocol(ABC):
    """
    Abstract base class for debate protocols.
    
    Implement this to create custom debate flows.
    Examples: single-round, cross-examination, iterative refinement.
    """
    
    @property
    @abstractmethod
    def protocol_name(self) -> str:
        """Human-readable name for this protocol."""
        pass
    
    @abstractmethod
    async def run(
        self,
        query: str,
        documents: list[DocumentWithScore],
        advocates: list[BaseAdvocate],
    ) -> DebateResult:
        """
        Run the debate protocol.
        
        Args:
            query: The user's question
            documents: All retrieved documents
            advocates: The advocates participating in the debate
            
        Returns:
            DebateResult with the final answer and audit trail
        """
        pass


class BaseSynthesizer(ABC):
    """
    Abstract base class for answer synthesizers.
    
    Implement this to create custom synthesis strategies.
    Examples: majority vote, confidence-weighted, iterative refinement.
    """
    
    @abstractmethod
    async def synthesize(
        self,
        query: str,
        advocate_responses: list[AdvocateResponse],
    ) -> tuple[str, str]:
        """
        Synthesize advocate arguments into a final answer.
        
        Args:
            query: The original question
            advocate_responses: Arguments from all advocates
            
        Returns:
            Tuple of (answer, reasoning)
        """
        pass


# =============================================================================
# PHASE 2 PROTOCOL STUBS (Not yet implemented)
# =============================================================================

class CrossExaminationProtocol(BaseDebateProtocol):
    """
    Phase 2: Cross-examination debate protocol.
    
    After initial arguments, advocates can challenge each other's claims.
    The challenged advocate must defend or concede.
    
    NOT YET IMPLEMENTED - placeholder for Phase 2.
    """
    
    @property
    def protocol_name(self) -> str:
        return "cross_examination"
    
    async def run(
        self,
        query: str,
        documents: list[DocumentWithScore],
        advocates: list[BaseAdvocate],
    ) -> DebateResult:
        raise NotImplementedError(
            "CrossExaminationProtocol is a Phase 2 feature. "
            "Use DebateOrchestrator for Phase 1 single-round debates."
        )


class RebuttalAdvocate(BaseAdvocate):
    """
    Phase 2: An advocate that responds to other advocates' arguments.
    
    Used in later rounds of a debate to refine positions.
    
    NOT YET IMPLEMENTED - placeholder for Phase 2.
    """
    
    def __init__(self, group_id: str, original_response: AdvocateResponse):
        self._group_id = group_id
        self.original_response = original_response
    
    @property
    def group_id(self) -> str:
        return self._group_id
    
    async def argue(
        self,
        query: str,
        documents: list[DocumentWithScore],
    ) -> AdvocateResponse:
        raise NotImplementedError(
            "RebuttalAdvocate is a Phase 2 feature."
        )
    
    async def rebut(
        self,
        query: str,
        challenges: list[str],
    ) -> AdvocateResponse:
        """
        Respond to challenges from other advocates.
        
        Args:
            query: The original question
            challenges: Challenges raised by other advocates
            
        Returns:
            Updated AdvocateResponse defending or conceding points
        """
        raise NotImplementedError(
            "RebuttalAdvocate.rebut is a Phase 2 feature."
        )
