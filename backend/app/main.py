import os
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import desc, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .database import Document, DocumentChunk, get_database_session, initialize_database
from .embeddings import EMBEDDING_MODEL_NAME, EMBEDDING_VECTOR_DIMENSION, embed_search_query
from .ingestion import (
    AternumBulkIngestRequest,
    BulkIngestResponse,
    DocumentResponse,
    IngestDocumentRequest,
    build_ingest_request_from_aternum_node,
    document_to_response,
    ingest_document,
)
from .permissions import PERMISSION_NOTICE, apply_search_filters

CORS_ORIGINS = [origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=25)
    tag_filters: list[str] = Field(default_factory=list)
    include_answer: bool = True


class SearchHit(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    title: str | None
    content: str
    score: float
    source_system: str
    source_id: str | None
    tags: list[str]
    metadata: dict[str, Any]


class SearchResponse(BaseModel):
    query: str
    answer: str | None
    hits: list[SearchHit]
    permission_notice: str


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _ = app
    initialize_database()
    yield


app = FastAPI(
    title="Aternum RAG Sandbox",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health(database_session: Session = Depends(get_database_session)) -> dict[str, Any]:
    database_status = "ok"
    try:
        database_session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        database_status = "unavailable"

    return {
        "status": "ok" if database_status == "ok" else "degraded",
        "database": database_status,
        "embedding_model": EMBEDDING_MODEL_NAME,
        "embedding_dimension": EMBEDDING_VECTOR_DIMENSION,
    }


@app.post("/api/documents", response_model=DocumentResponse, status_code=201)
def create_document(
    ingest_request: IngestDocumentRequest,
    database_session: Session = Depends(get_database_session),
) -> DocumentResponse:
    try:
        document = ingest_document(database_session, ingest_request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    return document_to_response(document)


@app.get("/api/documents", response_model=list[DocumentResponse])
def list_documents(
    limit: int = 50,
    database_session: Session = Depends(get_database_session),
) -> list[DocumentResponse]:
    documents = database_session.scalars(select(Document).order_by(desc(Document.ingested_at)).limit(limit)).all()
    return [document_to_response(document) for document in documents]


@app.delete("/api/documents/{document_id}", status_code=204)
def delete_document(
    document_id: uuid.UUID,
    database_session: Session = Depends(get_database_session),
) -> None:
    document = database_session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    database_session.delete(document)
    database_session.commit()


@app.post("/api/rag/query", response_model=SearchResponse)
def query_rag(
    search_request: SearchRequest,
    database_session: Session = Depends(get_database_session),
) -> SearchResponse:
    query_embedding = embed_search_query(search_request.query)
    cosine_distance = DocumentChunk.embedding.cosine_distance(query_embedding).label("cosine_distance")

    search_statement = (
        select(DocumentChunk, Document, cosine_distance)
        .join(Document, Document.id == DocumentChunk.document_id)
        .order_by(cosine_distance)
        .limit(search_request.top_k)
    )
    search_statement = apply_search_filters(search_statement, search_request.tag_filters)

    search_rows = database_session.execute(search_statement).all()
    search_hits = [
        SearchHit(
            chunk_id=document_chunk.id,
            document_id=document.id,
            title=document.title,
            content=document_chunk.content,
            score=round(1.0 - float(cosine_distance_score), 4),
            source_system=document.source_system,
            source_id=document.source_id,
            tags=document.tags or [],
            metadata={
                **(document.extra_metadata or {}),
                "chunk": document_chunk.extra_metadata or {},
            },
        )
        for document_chunk, document, cosine_distance_score in search_rows
    ]

    return SearchResponse(
        query=search_request.query,
        answer=build_extractive_answer(search_hits) if search_request.include_answer else None,
        hits=search_hits,
        permission_notice=PERMISSION_NOTICE,
    )


@app.post("/api/integrations/aternum/nodes", response_model=BulkIngestResponse, status_code=201)
def ingest_aternum_nodes(
    bulk_ingest_request: AternumBulkIngestRequest,
    database_session: Session = Depends(get_database_session),
) -> BulkIngestResponse:
    documents = []
    for node in bulk_ingest_request.nodes:
        ingest_request = build_ingest_request_from_aternum_node(node)
        documents.append(document_to_response(ingest_document(database_session, ingest_request)))

    return BulkIngestResponse(documents=documents)


def build_extractive_answer(search_hits: list[SearchHit]) -> str:
    if not search_hits:
        return "No matching context found."

    answer_lines = ["Retrieved context:"]
    for hit_index, search_hit in enumerate(search_hits[:3], start=1):
        hit_label = search_hit.title or search_hit.source_id or str(search_hit.document_id)
        answer_lines.append(f"{hit_index}. {hit_label}: {search_hit.content[:500]}")

    return "\n".join(answer_lines)
