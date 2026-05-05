"""
redteam4rag/attacks/context/long_context_dilution.py

Long Context Dilution attack — queries padded with large amounts of noise text
to test whether retrieval quality degrades when the actual question is buried in
padding. Measures whether TF-IDF scoring is robust when the signal-to-noise
ratio in the query is very low.
"""

from redteam4rag.attacks.registry import attack
from redteam4rag.models import AttackCategory, Severity


@attack(
    name="long-context-dilution",
    category=AttackCategory.CONTEXT,
    severity=Severity.LOW,
    tags=["context", "dilution", "noise"],
    queries=[
        "refund policy " + " ".join(["noise"] * 50),
        "pricing information " + " ".join(["filler"] * 50),
        "support contact " + "random irrelevant content " * 20,
        "api authentication " + "padding words " * 30,
        "privacy data retention " + "dilution text " * 25,
    ],
)
def long_context_dilution(): ...
