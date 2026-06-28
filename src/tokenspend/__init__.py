"""token-spend-consolidator — what would your AI usage have cost at API rates?

Three layers (see docs/BLUEPRINT.md):
  1. collectors/  — per-source adapters that emit normalized UsageRecords
  2. valuation    — turns token counts into dollars via a pricing table
  3. consolidate  — merges + de-duplicates collector output into the headline number
"""

__version__ = "0.1.0"
