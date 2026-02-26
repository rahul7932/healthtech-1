# Trust Layer Services
# 
# The Trust Layer is what makes this project special.
# It runs AFTER the RAG generator produces an answer, and verifies:
# - What claims were made (ClaimExtractor)
# - Which evidence supports/contradicts each claim (AttributionScorer)
# - How confident we should be (ConfidenceCalculator)
# - What evidence is missing (GapDetector)
