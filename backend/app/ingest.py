"""
Runs after a file is saved to disk: extract -> chunk -> embed -> store -> mark ready.
Called as a FastAPI BackgroundTask so the upload request returns immediately and
the UI can poll document status while a big PDF is still processing.
"""
from pathlib import Path

from . import chunking, config, db, embeddings, loaders, vector_store


def ingest_document(doc_id: str, kb_id: str, file_path: Path) -> None:
    db.update_document_status(doc_id, status="processing")
    try:
        text = loaders.load_text(file_path)
        if not text.strip():
            raise ValueError("No extractable text found in this file")

        chunks = chunking.split_text(text, config.CHUNK_SIZE, config.CHUNK_OVERLAP)
        if not chunks:
            raise ValueError("Document produced no chunks after splitting")

        provider = embeddings.get_embedding_provider()
        vectors = provider.embed(chunks)

        doc = db.get_document(doc_id)
        vector_store.add_chunks(kb_id, doc_id, doc["filename"], chunks, vectors)

        db.update_document_status(doc_id, status="ready", chunk_count=len(chunks))
    except Exception as exc:  # noqa: BLE001 - want to record *any* failure on the doc
        db.update_document_status(doc_id, status="failed", error_message=str(exc))
