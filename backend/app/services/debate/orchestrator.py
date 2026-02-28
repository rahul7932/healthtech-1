"""
Debate Orchestrator — Coordinates the multi-agent debate process.

WHAT THIS DOES:
Main entry point for the debate system. Splits documents among advocates,
runs the debate, and returns a synthesized result.

HOW IT WORKS:
1. Split retrieved documents into N groups (round-robin by relevance)
2. Create N advocate agents, one per group
3. Run all advocates in parallel (asyncio.gather)
4. Pass advocate responses to the synthesizer
5. Build and return the DebateResult

WHY ORCHESTRATION:
- Single entry point for the pipeline to call
- Handles parallelization of advocate calls
- Builds the audit trail (transcript, metadata)
- Configurable number of advocates

USAGE:
    orchestrator = DebateOrchestrator(num_advocates=2)
    result = await orchestrator.run_debate(
        query="Do ACE inhibitors reduce mortality?",
        documents=retrieved_docs,
    )
    # result.answer contains the final synthesized answer
"""

import asyncio
import logging
import time
from typing import Optional

from app.models.schemas import DocumentWithScore
from app.services.debate.models import AdvocateResponse, DebateResult, DebateRound
from app.services.debate.advocate import DocumentAdvocate
from app.services.debate.synthesizer import AnswerSynthesizer

logger = logging.getLogger(__name__)


def _split_documents(
    documents: list[DocumentWithScore],
    num_groups: int,
) -> list[list[DocumentWithScore]]:
    """
    Split documents into groups using round-robin by relevance.
    
    Documents are already sorted by relevance score, so round-robin
    ensures each group gets a mix of high and low relevance docs.
    
    Example with 6 docs and 2 groups:
        [doc1, doc2, doc3, doc4, doc5, doc6]
        Group 1: [doc1, doc3, doc5]  (indices 0, 2, 4)
        Group 2: [doc2, doc4, doc6]  (indices 1, 3, 5)
    """
    groups = [[] for _ in range(num_groups)]
    for i, doc in enumerate(documents):
        groups[i % num_groups].append(doc)
    return groups


def _build_transcript(
    query: str,
    advocate_responses: list[AdvocateResponse],
    answer: str,
    reasoning: str,
) -> str:
    """Build a human-readable transcript of the debate."""
    lines = [
        "=" * 60,
        "DEBATE TRANSCRIPT",
        "=" * 60,
        f"\nQUERY: {query}\n",
        "-" * 40,
        "ADVOCATE ARGUMENTS",
        "-" * 40,
    ]
    
    for response in advocate_responses:
        lines.extend([
            f"\n### {response.group_id.upper()} ###",
            f"Documents: {len(response.documents)}",
            f"Confidence: {response.confidence:.2f}",
            f"PMIDs cited: {', '.join(response.cited_pmids) or 'None'}",
            f"\nArgument:\n{response.argument}",
            f"\nKey Findings:",
        ])
        for finding in response.key_findings:
            lines.append(f"  - {finding}")
    
    lines.extend([
        "\n" + "-" * 40,
        "SYNTHESIS",
        "-" * 40,
        f"\nFinal Answer:\n{answer}",
        f"\nSynthesis Reasoning:\n{reasoning}",
        "\n" + "=" * 60,
    ])
    
    return "\n".join(lines)


class DebateOrchestrator:
    """
    Orchestrates the multi-agent debate process.
    
    Coordinates advocates, manages parallelization, and produces
    the final synthesized result with full audit trail.
    """
    
    def __init__(self, num_advocates: int = 2):
        """
        Initialize the orchestrator.
        
        Args:
            num_advocates: Number of advocate agents to use (default 2)
        """
        self.num_advocates = max(1, num_advocates)  # At least 1
        self.synthesizer = AnswerSynthesizer()
    
    async def run_debate(
        self,
        query: str,
        documents: list[DocumentWithScore],
    ) -> DebateResult:
        """
        Run a debate and return the synthesized result.
        
        Args:
            query: The user's medical question
            documents: Retrieved documents to debate over
            
        Returns:
            DebateResult with answer, advocate responses, and audit trail
        """
        start_time = time.time()
        
        if not documents:
            return DebateResult(
                answer="No documents were provided for the debate.",
                advocate_responses=[],
                synthesis_reasoning="Cannot debate without documents.",
                debate_transcript="No documents provided.",
                rounds=[],
                metadata={"error": "no_documents"},
            )
        
        logger.info(
            f"Starting debate: {len(documents)} documents, "
            f"{self.num_advocates} advocates"
        )
        
        # Step 1: Split documents among advocates
        doc_groups = _split_documents(documents, self.num_advocates)
        logger.info(
            f"Document split: {[len(g) for g in doc_groups]} docs per advocate"
        )
        
        # Step 2: Run advocates in parallel
        advocate_responses = await self._run_advocates(query, doc_groups)
        advocate_time = time.time() - start_time
        logger.info(f"Advocates completed in {advocate_time:.2f}s")
        
        # Step 3: Synthesize the responses
        synthesis_start = time.time()
        answer, reasoning = await self.synthesizer.synthesize(query, advocate_responses)
        synthesis_time = time.time() - synthesis_start
        logger.info(f"Synthesis completed in {synthesis_time:.2f}s")
        
        # Step 4: Build the result
        total_time = time.time() - start_time
        
        # Create the debate round (Phase 1 has single round)
        debate_round = DebateRound(
            round_number=1,
            round_type="initial",
            advocate_responses=advocate_responses,
        )
        
        # Build transcript for audit
        transcript = _build_transcript(query, advocate_responses, answer, reasoning)
        
        result = DebateResult(
            answer=answer,
            advocate_responses=advocate_responses,
            synthesis_reasoning=reasoning,
            debate_transcript=transcript,
            rounds=[debate_round],
            metadata={
                "num_advocates": self.num_advocates,
                "num_documents": len(documents),
                "docs_per_advocate": [len(g) for g in doc_groups],
                "advocate_time_seconds": round(advocate_time, 2),
                "synthesis_time_seconds": round(synthesis_time, 2),
                "total_time_seconds": round(total_time, 2),
            },
        )
        
        logger.info(
            f"Debate complete: {result.num_advocates} advocates, "
            f"{len(result.all_cited_pmids)} unique PMIDs cited, "
            f"avg confidence {result.average_confidence:.2f}, "
            f"total time {total_time:.2f}s"
        )
        
        return result
    
    async def _run_advocates(
        self,
        query: str,
        doc_groups: list[list[DocumentWithScore]],
    ) -> list[AdvocateResponse]:
        """Run all advocates in parallel."""
        # Create advocate tasks
        tasks = []
        for i, docs in enumerate(doc_groups):
            group_id = f"group_{i + 1}"
            advocate = DocumentAdvocate(group_id)
            tasks.append(advocate.argue(query, docs))
        
        # Run in parallel
        responses = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Handle any exceptions
        valid_responses = []
        for i, response in enumerate(responses):
            if isinstance(response, Exception):
                logger.error(f"Advocate group_{i + 1} failed: {response}")
                valid_responses.append(AdvocateResponse(
                    group_id=f"group_{i + 1}",
                    documents=doc_groups[i],
                    argument=f"Advocate failed: {str(response)}",
                    key_findings=[],
                    confidence=0.0,
                    cited_pmids=[],
                ))
            else:
                valid_responses.append(response)
        
        return valid_responses


async def run_debate(
    query: str,
    documents: list[DocumentWithScore],
    num_advocates: int = 2,
) -> DebateResult:
    """
    Convenience function to run a debate.
    
    Example:
        result = await run_debate(
            "Do ACE inhibitors reduce mortality?",
            retrieved_docs,
            num_advocates=2,
        )
    """
    orchestrator = DebateOrchestrator(num_advocates=num_advocates)
    return await orchestrator.run_debate(query, documents)
