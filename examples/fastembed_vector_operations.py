"""FastEmbed + iris.Vector operations without SQL.

Prerequisites:
    pip install fastembed

Run from an embedded IRIS-capable environment:
    python examples/fastembed_vector_operations.py

This example does not create a table or execute SQL. FastEmbed embeddings are
wrapped as iris.Vector objects and ranked with ObjectScript $VECTOROP through
the Python Vector methods. Vector operations require embedded iris.gref and
iris.execute; they are not routed through the remote/native bridge.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import iris
from fastembed import TextEmbedding


DOCUMENTS = [
    "IRIS stores vectors in SQL VECTOR columns.",
    "FastEmbed generates local text embeddings.",
    "ByRef lets Python receive ObjectScript output arguments.",
    "VECTOR_COSINE ranks documents by embedding similarity.",
    "DB-API parameters should be cast with TO_VECTOR.",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model",
        default="BAAI/bge-small-en-v1.5",
        help="FastEmbed model name.",
    )
    parser.add_argument(
        "--query",
        default="How do I store embeddings in IRIS?",
        help="Search query to embed and rank against the example documents.",
    )
    parser.add_argument("--top-k", type=int, default=3)
    return parser.parse_args()


def embed_texts(model: TextEmbedding, texts: Iterable[str]) -> list[iris.Vector]:
    return [iris.Vector(embedding, dtype="float") for embedding in model.embed(texts)]


def rank_documents(
    query_vector: iris.Vector,
    documents: Sequence[str],
    document_vectors: Sequence[iris.Vector],
    top_k: int,
):
    scores = [
        (query_vector.cosine(document_vector), index, content)
        for index, (content, document_vector) in enumerate(
            zip(documents, document_vectors),
            start=1,
        )
    ]
    return sorted(scores, reverse=True)[: max(1, int(top_k))]


def centroid(vectors: Sequence[iris.Vector]) -> iris.Vector:
    if not vectors:
        raise ValueError("centroid requires at least one vector")

    total = vectors[0]
    for vector in vectors[1:]:
        total = total + vector
    return total / len(vectors)


def main() -> None:
    args = parse_args()
    model = TextEmbedding(model_name=args.model)

    document_vectors = embed_texts(model, DOCUMENTS)
    query_vector = embed_texts(model, [args.query])[0]
    average_document_vector = centroid(document_vectors)

    print(f"dimension: {len(query_vector)}")
    print(f"query sum: {query_vector.sum():.4f}")
    print(f"centroid cosine: {query_vector.cosine(average_document_vector):.4f}")
    print()

    for score, row_id, content in rank_documents(
        query_vector,
        DOCUMENTS,
        document_vectors,
        args.top_k,
    ):
        print(f"{score:.4f} #{row_id}: {content}")


if __name__ == "__main__":
    main()
