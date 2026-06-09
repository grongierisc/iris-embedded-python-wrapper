"""FastEmbed + iris.Vector semantic search example.

Prerequisites:
    pip install fastembed

Run from an environment that can connect to IRIS:
    python examples/fastembed_vector_search.py

By default this uses embedded DB-API mode. Pass --hostname/--namespace/etc. to
use a remote Native API DB-API connection instead.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import iris
from fastembed import TextEmbedding


TABLE_NAME = "Demo.FastEmbedVectorExample"

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
    parser.add_argument("--hostname", default=os.getenv("IRIS_HOSTNAME"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("IRIS_PORT", "1972")),
    )
    parser.add_argument("--namespace", default=os.getenv("IRIS_NAMESPACE", "USER"))
    parser.add_argument("--username", default=os.getenv("IRIS_USERNAME"))
    parser.add_argument("--password", default=os.getenv("IRIS_PASSWORD"))
    return parser.parse_args()


def connect(args: argparse.Namespace):
    if args.hostname:
        return iris.dbapi.connect(
            mode="native",
            hostname=args.hostname,
            port=args.port,
            namespace=args.namespace,
            username=args.username,
            password=args.password,
        )
    return iris.dbapi.connect(mode="embedded", namespace=args.namespace)


def embed_texts(model: TextEmbedding, texts: Iterable[str]) -> list[iris.Vector]:
    return [iris.Vector(embedding, dtype="float") for embedding in model.embed(texts)]


def recreate_table(cur, dimension: int) -> None:
    try:
        cur.execute(f"DROP TABLE {TABLE_NAME}")
    except Exception as exc:
        if "SQLCODE -30" not in str(exc) and "does not exist" not in str(exc):
            raise

    cur.execute(
        f"""
        CREATE TABLE {TABLE_NAME} (
            id INTEGER,
            content VARCHAR(1000),
            embedding VECTOR(FLOAT, {dimension})
        )
        """
    )


def insert_documents(cur, documents: Sequence[str], vectors: Sequence[iris.Vector]) -> None:
    for index, (content, embedding) in enumerate(zip(documents, vectors), start=1):
        cur.execute(
            f"""
            INSERT INTO {TABLE_NAME} (id, content, embedding)
            VALUES (?, ?, {embedding.to_sql()})
            """,
            (index, content, embedding),
        )


def search(cur, query_vector: iris.Vector, top_k: int):
    top_k = max(1, int(top_k))
    cur.execute(
        f"""
        SELECT TOP {top_k}
            id,
            content,
            VECTOR_COSINE(embedding, {query_vector.to_sql()}) AS score
        FROM {TABLE_NAME}
        ORDER BY score DESC
        """,
        (query_vector,),
    )
    return [
        (row_id, content, float(score))
        for row_id, content, score in cur.fetchall()
    ]


def main() -> None:
    args = parse_args()
    model = TextEmbedding(model_name=args.model)

    document_vectors = embed_texts(model, DOCUMENTS)
    dimension = len(document_vectors[0])

    conn = connect(args)
    cur = conn.cursor()
    try:
        recreate_table(cur, dimension)
        insert_documents(cur, DOCUMENTS, document_vectors)
        if hasattr(conn, "commit"):
            conn.commit()

        query_vector = embed_texts(model, [args.query])[0]
        for row_id, content, score in search(cur, query_vector, args.top_k):
            print(f"{score:.4f} #{row_id}: {content}")
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
