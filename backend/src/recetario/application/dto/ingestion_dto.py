"""DTOs for the LLM-assisted ingestion boundary.

`ResolvedIngredient` is the LLM's USDA-match decision for a single ingredient
line, referenced by its position in the input list. A null `fdc_id` (or a
`confidence` below the use case's threshold) means "no confident match" — the
line is left unlinked for the user to confirm via the manual-link UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class ResolvedIngredient:
    index: int
    fdc_id: int | None = None
    gram_weight: Decimal | None = None
    confidence: float = 0.0
