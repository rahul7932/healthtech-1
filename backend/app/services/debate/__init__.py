"""
Debate Module — Multi-agent debate system for answer generation.

This module provides an alternative to single-pass RAG generation.
Multiple advocate agents argue for their assigned documents, then
a synthesizer combines their arguments into a final answer.

COMPONENTS:
- DebateOrchestrator: Main entry point, coordinates the debate
- DocumentAdvocate: Agent that argues for its documents
- AnswerSynthesizer: Combines advocate arguments into final answer
- DebateResult: Contains answer + full audit trail

USAGE:
    from app.services.debate import run_debate, DebateResult
    
    result: DebateResult = await run_debate(
        query="Do ACE inhibitors reduce mortality?",
        documents=retrieved_docs,
        num_advocates=2,
    )
    
    print(result.answer)  # The synthesized answer
    print(result.debate_transcript)  # Full audit trail

TOGGLE:
    Enable via config: USE_AGENTIC_DEBATE=true
    The pipeline automatically uses debate when enabled.
"""

# Main entry points
from app.services.debate.orchestrator import (
    DebateOrchestrator,
    run_debate,
)

# Data models
from app.services.debate.models import (
    AdvocateResponse,
    DebateResult,
    DebateRound,
)

# Components (for advanced usage)
from app.services.debate.advocate import DocumentAdvocate
from app.services.debate.synthesizer import AnswerSynthesizer

# Phase 2 protocols (for extensibility)
from app.services.debate.protocols import (
    BaseAdvocate,
    BaseDebateProtocol,
    BaseSynthesizer,
)

__all__ = [
    # Main entry points
    "DebateOrchestrator",
    "run_debate",
    # Data models
    "AdvocateResponse",
    "DebateResult",
    "DebateRound",
    # Components
    "DocumentAdvocate",
    "AnswerSynthesizer",
    # Abstract bases
    "BaseAdvocate",
    "BaseDebateProtocol",
    "BaseSynthesizer",
]
