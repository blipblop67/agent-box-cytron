"""
One Chroma collection per knowledge base - keeps deletion, per-KB stats, and
access control simple, since we never have to filter a shared collection by KB.
"""
import chromadb

from . import config

_client = chromadb.PersistentClient(path=str(config.CHROMA_DIR))


def _collection_name(kb_id: str) -> str:
    return f"kb_{kb_id}"


def get_or_create_collection(kb_id: str):
    return _client.get_or_create_collection(name=_collection_name(kb_id))


def add_chunks(kb_id: str, doc_id: str, filename: str, chunks: list[str], embeddings: list[list[float]]) -> None:
    collection = get_or_create_collection(kb_id)
    ids = [f"{doc_id}:{i}" for i in range(len(chunks))]
    metadatas = [
        {"document_id": doc_id, "filename": filename, "chunk_index": i}
        for i in range(len(chunks))
    ]
    collection.add(ids=ids, embeddings=embeddings, documents=chunks, metadatas=metadatas)


def query(kb_id: str, query_embedding: list[float], top_k: int) -> list[dict]:
    collection = get_or_create_collection(kb_id)
    if collection.count() == 0:
        return []
    result = collection.query(query_embeddings=[query_embedding], n_results=min(top_k, collection.count()))

    out = []
    docs = result["documents"][0]
    metas = result["metadatas"][0]
    distances = result["distances"][0]
    for text, meta, distance in zip(docs, metas, distances):
        out.append({
            "document_id": meta["document_id"],
            "filename": meta["filename"],
            "chunk_index": meta["chunk_index"],
            "text": text,
            # Chroma returns a distance (lower = closer); flip to a 0-1 "similarity"
            # score, which is more intuitive to show in the UI.
            "score": 1.0 / (1.0 + distance),
        })
    return out


def delete_document_chunks(kb_id: str, doc_id: str) -> None:
    collection = get_or_create_collection(kb_id)
    collection.delete(where={"document_id": doc_id})


def delete_collection(kb_id: str) -> None:
    try:
        _client.delete_collection(name=_collection_name(kb_id))
    except Exception:
        pass  # collection may never have been created if no docs were added
