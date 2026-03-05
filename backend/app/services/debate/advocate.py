"""
Document Advocate — An agent that argues for its assigned documents.

WHAT THIS DOES:
Each advocate receives a subset of retrieved documents and constructs
an argument for why those documents best answer the user's query.

HOW IT WORKS:
1. Advocate receives a group of documents
2. Analyzes each document for relevant findings
3. Constructs a coherent argument with citations
4. Reports confidence in its argument

WHY ADVOCATES:
- Forces deep engagement with fewer documents (vs. skimming all)
- Multiple perspectives surface conflicting evidence
- Explicit reasoning about why evidence matters
- Natural audit trail of how answer was derived

USAGE:
    advocate = DocumentAdvocate(group_id="group_1")
    response = await advocate.argue(
        query="Do ACE inhibitors reduce mortality?",
        documents=docs_subset,
    )
"""

import json
import logging
import re
from typing import Literal

from openai import AsyncOpenAI

from app.config import get_settings
from app.models.schemas import DocumentWithScore
from app.services.debate.models import AdvocateResponse

logger = logging.getLogger(__name__)

ADVOCATE_MODEL = "gpt-4o"

ClinicalPersona = Literal["clinical"]
MethodologistPersona = Literal["methodologist"]
SafetyPersona = Literal["safety"]
PatientPersona = Literal["patient"]
AdvocatePersona = Literal[ClinicalPersona, MethodologistPersona, SafetyPersona, PatientPersona]

CLINICAL_SYSTEM_PROMPT = """You are a practicing clinician interpreting a set of research papers for direct patient care.

YOUR ROLE:
- Focus on practical, bedside-relevant conclusions for the clinical question.
- Emphasize magnitude of benefit, absolute vs relative risk, typical patient profiles, and how this would change management.
- Highlight which populations the evidence applies to (age, comorbidities, disease severity, setting).

RULES:
1. ONLY use evidence from the documents provided to you.
2. Cite every clinical claim using [PMID:xxxxx] format.
3. Be concrete: absolute risk reductions, NNT/NNH when possible, time horizons.
4. Acknowledge clinical uncertainty, grey zones, and when “it depends”.
5. Do NOT make up information or cite documents you weren't given.

OUTPUT FORMAT (JSON):
{
  "argument": "2-3 paragraphs on what this means for clinical practice",
  "key_findings": [
    "Practical takeaway 1 with key numbers [PMID:xxxxx]",
    "Practical takeaway 2 with key numbers [PMID:xxxxx]"
  ],
  "confidence": 0.0-1.0,
  "cited_pmids": ["12345", "67890"]
}"""

METHODOLOGIST_SYSTEM_PROMPT = """You are a clinical trial methodologist evaluating the strength and limitations of the evidence.

YOUR ROLE:
- Critically appraise study design, risk of bias, sample size, endpoints, and statistical robustness.
- Focus on internal validity, external validity, and consistency across studies.
- Explain how strong or weak the causal inference is.

RULES:
1. ONLY use evidence from the documents provided to you.
2. Cite every methodological claim using [PMID:xxxxx] format.
3. Call out major biases (selection, confounding, measurement, publication).
4. Distinguish between high-certainty vs low-certainty findings.
5. Do NOT make up information or cite documents you weren't given.

OUTPUT FORMAT (JSON):
{
  "argument": "2-3 paragraphs on evidence quality and reliability of conclusions",
  "key_findings": [
    "Methodological strength or weakness 1 [PMID:xxxxx]",
    "Methodological strength or weakness 2 [PMID:xxxxx]"
  ],
  "confidence": 0.0-1.0,
  "cited_pmids": ["12345", "67890"]
}"""

SAFETY_SYSTEM_PROMPT = """You are a safety and pharmacovigilance expert focusing on harms, tolerability, and risk management.

YOUR ROLE:
- Identify adverse effects, serious harms, discontinuation rates, and safety signals in the evidence.
- Consider short- and long-term safety, vulnerable populations, and monitoring needs.
- Weigh benefit vs harm where possible.

RULES:
1. ONLY use evidence from the documents provided to you.
2. Cite every safety-related claim using [PMID:xxxxx] format.
3. Be specific about rates and severity of adverse effects when reported.
4. Highlight important unknowns or under-reported safety issues.
5. Do NOT make up information or cite documents you weren't given.

OUTPUT FORMAT (JSON):
{
  "argument": "2-3 paragraphs summarizing safety, harms, and monitoring considerations",
  "key_findings": [
    "Key harm or safety consideration 1 [PMID:xxxxx]",
    "Key harm or safety consideration 2 [PMID:xxxxx]"
  ],
  "confidence": 0.0-1.0,
  "cited_pmids": ["12345", "67890"]
}"""

PATIENT_SYSTEM_PROMPT = """You are a patient-centered outcomes and quality-of-life advocate.

YOUR ROLE:
- Focus on outcomes that matter most to patients: symptoms, functional status, daily life, treatment burden, convenience, and long-term quality of life.
- Highlight when studies report surrogate endpoints (e.g., biomarkers) instead of patient-important outcomes.
- Consider how different patients might value trade-offs between benefit, risk, and burden.

RULES:
1. ONLY use evidence from the documents provided to you.
2. Cite every patient-important outcome using [PMID:xxxxx] format.
3. Be explicit about changes in symptoms, functioning, and quality-of-life scores when reported.
4. Call out where patient-important outcomes are missing or under-reported.
5. Do NOT make up information or cite documents you weren't given.

OUTPUT FORMAT (JSON):
{
  "argument": "2-3 paragraphs describing patient-important benefits, burdens, and quality-of-life trade-offs",
  "key_findings": [
    "Patient-relevant finding 1 [PMID:xxxxx]",
    "Patient-relevant finding 2 [PMID:xxxxx]"
  ],
  "confidence": 0.0-1.0,
  "cited_pmids": ["12345", "67890"]
}"""


def _format_documents_for_advocate(documents: list[DocumentWithScore]) -> str:
    """Format documents for the advocate prompt."""
    formatted = []
    for i, doc in enumerate(documents, 1):
        formatted.append(f"""
=== DOCUMENT {i} ===
PMID: {doc.pmid}
Title: {doc.title}
Journal: {doc.journal or 'Unknown'}
Relevance Score: {doc.relevance_score:.3f}

Abstract:
{doc.abstract}
""")
    return "\n".join(formatted)


class DocumentAdvocate:
    """
    An agent that argues for a specific set of documents.
    
    Each advocate is assigned a subset of retrieved documents and must
    construct the best possible argument for how those documents
    answer the user's query.
    """
    
    def __init__(self, group_id: str, persona: AdvocatePersona):
        """
        Initialize an advocate for a document group.
        
        Args:
            group_id: Identifier for this advocate (e.g., "clinical")
            persona: The perspective this advocate should take
        """
        self.group_id = group_id
        self.persona: AdvocatePersona = persona
        if persona == "clinical":
            self._system_prompt = CLINICAL_SYSTEM_PROMPT
        elif persona == "methodologist":
            self._system_prompt = METHODOLOGIST_SYSTEM_PROMPT
        elif persona == "safety":
            self._system_prompt = SAFETY_SYSTEM_PROMPT
        else:
            self._system_prompt = PATIENT_SYSTEM_PROMPT
        settings = get_settings()
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)
    
    async def argue(
        self,
        query: str,
        documents: list[DocumentWithScore],
    ) -> AdvocateResponse:
        """
        Construct an argument for why these documents answer the query.
        
        Args:
            query: The user's medical question
            documents: The documents assigned to this advocate
            
        Returns:
            AdvocateResponse with argument, findings, confidence, and citations
        """
        if not documents:
            return AdvocateResponse(
                group_id=self.group_id,
                documents=documents,
                argument="No documents were assigned to this advocate.",
                key_findings=[],
                confidence=0.0,
                cited_pmids=[],
            )
        
        logger.info(f"Advocate {self.group_id} arguing for {len(documents)} documents")
        
        # Format documents for the prompt
        docs_text = _format_documents_for_advocate(documents)
        available_pmids = [doc.pmid for doc in documents]
        
        user_prompt = f"""QUERY: {query}

YOUR ASSIGNED DOCUMENTS:
{docs_text}

Available PMIDs for citation: {', '.join(available_pmids)}

Construct your argument for why these documents best answer the query.
Return your response as JSON."""

        try:
            response = await self.client.chat.completions.create(
                model=ADVOCATE_MODEL,
                messages=[
                    {"role": "system", "content": self._system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.3,
            )
            
            result = json.loads(response.choices[0].message.content)
            
            # Extract and validate PMIDs
            cited_pmids = result.get("cited_pmids", [])
            # Also extract any PMIDs from the argument text
            argument_pmids = re.findall(r'\[PMID:(\d+)\]', result.get("argument", ""))
            all_cited = list(set(cited_pmids + argument_pmids))
            # Filter to only PMIDs we actually have
            valid_pmids = [p for p in all_cited if p in available_pmids]
            
            return AdvocateResponse(
                group_id=self.group_id,
                documents=documents,
                argument=result.get("argument", ""),
                key_findings=result.get("key_findings", []),
                confidence=min(1.0, max(0.0, float(result.get("confidence", 0.5)))),
                cited_pmids=valid_pmids,
            )
            
        except Exception as e:
            logger.error(f"Advocate {self.group_id} failed: {e}")
            return AdvocateResponse(
                group_id=self.group_id,
                documents=documents,
                argument=f"Error generating argument: {str(e)}",
                key_findings=[],
                confidence=0.0,
                cited_pmids=[],
            )


async def create_advocate_response(
    group_id: str,
    persona: AdvocatePersona,
    query: str,
    documents: list[DocumentWithScore],
) -> AdvocateResponse:
    """Convenience function to create an advocate and get its response."""
    advocate = DocumentAdvocate(group_id, persona)
    return await advocate.argue(query, documents)
