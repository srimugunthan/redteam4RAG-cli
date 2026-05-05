"""
redteam4rag/attacks/retriever/sparse_dense_mismatch.py

Sparse-Dense Mismatch attack — semantically valid queries using synonyms rather
than exact keywords in the corpus. Tests whether TF-IDF retrieval misses
relevant chunks due to vocabulary mismatch.
"""

from redteam4rag.attacks.registry import attack
from redteam4rag.models import AttackCategory, Severity


@attack(
    name="sparse-dense-mismatch",
    category=AttackCategory.RETRIEVER,
    severity=Severity.MEDIUM,
    tags=["retriever", "sparse", "dense", "mismatch"],
    queries=[
        "What is the monthly cost of the service?",
        "How long do I have to send back a purchase?",
        "Where can I reach customer service?",
        "What credentials do I need for the REST interface?",
        "How long does the company keep my personal data?",
    ],
)
def sparse_dense_mismatch(): ...
