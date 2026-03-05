"""
Answer Synthesizer — Combines advocate arguments into a final answer.

WHAT THIS DOES:
Takes arguments from multiple advocates and synthesizes them into
a single, coherent answer that weighs all perspectives.

HOW IT WORKS:
1. Receives arguments from all advocates
2. Identifies areas of agreement and disagreement
3. Weighs evidence quality and confidence
4. Produces a balanced synthesis with citations from all sources
5. Explains the reasoning behind the synthesis

WHY SYNTHESIS:
- Combines insights from multiple advocates
- Surfaces and addresses contradictions explicitly
- Produces more balanced answers than single-pass generation
- Provides transparency into how the answer was derived

USAGE:
    synthesizer = AnswerSynthesizer()
    answer, reasoning = await synthesizer.synthesize(
        query="Do ACE inhibitors reduce mortality?",
        advocate_responses=responses,
    )
"""

import logging
from openai import AsyncOpenAI

from app.config import get_settings
from app.services.debate.models import AdvocateResponse

logger = logging.getLogger(__name__)

SYNTHESIZER_MODEL = "gpt-4o"

SYNTHESIZER_SYSTEM_PROMPT = """You are a medical synthesis expert who evaluates complementary perspectives and produces balanced, evidence-based answers.

YOUR ROLE:
Four distinct agents have analyzed the same set of research papers:
- CLINICAL: focuses on bedside decisions and what to tell patients.
- METHODOLOGIST: focuses on study design, bias, and strength of evidence.
- SAFETY: focuses on harms, adverse effects, and monitoring.
- PATIENT / QUALITY-OF-LIFE: focuses on symptoms, functioning, treatment burden, and outcomes that matter most to patients.

Each advocate has argued from their own perspective. Your job is to:
1. Evaluate all arguments fairly.
2. Identify where the perspectives agree and where they differ.
3. Synthesize the best overall answer for the clinical question.
4. Be transparent about conflicts or uncertainties and how they affect practice.

RULES:
1. Consider ALL advocate arguments - don't favor any single perspective by default.
2. Evidence corroborated across perspectives (e.g., strong methods + clinical benefit + acceptable safety + patient-important benefits) should be weighted higher.
3. When perspectives conflict, explain the trade-offs (e.g., promising benefit but weak methods, safety concerns, or poor quality-of-life impact).
4. Use [PMID:xxxxx] citations from the advocates' arguments.
5. Be honest about limitations in the overall evidence base and where more research is needed.

OUTPUT FORMAT:
Write your response in two parts:
1. ANSWER: A clear, well-structured answer (2-4 paragraphs) with citations, suitable for a clinician.
2. REASONING: Brief explanation of how you synthesized the clinical, methodological, safety, and patient / quality-of-life arguments.

Structure as:
---ANSWER---
[Your synthesized answer with [PMID:xxxxx] citations]

---REASONING---
[Your synthesis reasoning - how you combined clinical / methodological / safety / patient-quality-of-life views, where they agreed or conflicted, and why you weighted evidence as you did]"""


def _format_advocate_arguments(responses: list[AdvocateResponse]) -> str:
    """Format advocate responses for the synthesis prompt."""
    formatted = []
    for response in responses:
        findings_text = "\n".join(f"  - {f}" for f in response.key_findings)
        doc_summaries = ", ".join(
            f"PMID:{d.pmid}" for d in response.documents
        )
        
        formatted.append(f"""
=== {response.group_id.upper()} ===
Documents analyzed: {doc_summaries}
Self-assessed confidence: {response.confidence:.2f}

ARGUMENT:
{response.argument}

KEY FINDINGS:
{findings_text}
""")
    return "\n".join(formatted)


class AnswerSynthesizer:
    """
    Synthesizes advocate arguments into a final answer.
    
    Evaluates multiple competing arguments and produces a balanced
    synthesis that draws from all available evidence.
    """
    
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    async def synthesize(
        self,
        query: str,
        advocate_responses: list[AdvocateResponse],
    ) -> tuple[str, str]:
        """
        Synthesize advocate arguments into a final answer.
        
        Args:
            query: The original user question
            advocate_responses: Arguments from all advocates
            
        Returns:
            Tuple of (answer, reasoning)
        """
        if not advocate_responses:
            return (
                "No advocate arguments were provided to synthesize.",
                "No arguments to evaluate."
            )
        
        # Check if all advocates failed
        valid_responses = [r for r in advocate_responses if r.argument and r.confidence > 0]
        if not valid_responses:
            return (
                "The advocates were unable to construct valid arguments from the available documents.",
                "All advocate arguments were empty or had zero confidence."
            )
        
        logger.info(f"Synthesizing {len(advocate_responses)} advocate arguments")
        
        # Collect all available PMIDs for reference
        all_pmids = set()
        for response in advocate_responses:
            all_pmids.update(response.cited_pmids)
        
        # Format arguments for the prompt
        arguments_text = _format_advocate_arguments(advocate_responses)
        
        user_prompt = f"""QUERY: {query}

ADVOCATE ARGUMENTS:
{arguments_text}

All available PMIDs for citation: {', '.join(sorted(all_pmids)) if all_pmids else 'None cited'}

Synthesize these arguments into a final answer. Consider where advocates agree and disagree."""

        try:
            response = await self.client.chat.completions.create(
                model=SYNTHESIZER_MODEL,
                messages=[
                    {"role": "system", "content": SYNTHESIZER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
            )
            
            content = response.choices[0].message.content
            
            # Parse the response into answer and reasoning
            answer, reasoning = self._parse_response(content)
            
            return answer, reasoning
            
        except Exception as e:
            logger.error(f"Synthesis failed: {e}")
            return (
                f"Error synthesizing answer: {str(e)}",
                "Synthesis encountered an error."
            )
    
    def _parse_response(self, content: str) -> tuple[str, str]:
        """Parse the synthesizer response into answer and reasoning."""
        # Try to split on our markers
        if "---ANSWER---" in content and "---REASONING---" in content:
            parts = content.split("---REASONING---")
            answer_part = parts[0].replace("---ANSWER---", "").strip()
            reasoning_part = parts[1].strip() if len(parts) > 1 else ""
            return answer_part, reasoning_part
        
        # Fallback: try to find any section markers
        if "REASONING:" in content or "Reasoning:" in content:
            for marker in ["REASONING:", "Reasoning:", "**Reasoning**"]:
                if marker in content:
                    parts = content.split(marker)
                    return parts[0].strip(), parts[1].strip() if len(parts) > 1 else ""
        
        # Last resort: return everything as the answer
        return content.strip(), "No explicit reasoning section provided."


async def synthesize_debate(
    query: str,
    advocate_responses: list[AdvocateResponse],
) -> tuple[str, str]:
    """Convenience function to synthesize advocate arguments."""
    synthesizer = AnswerSynthesizer()
    return await synthesizer.synthesize(query, advocate_responses)
