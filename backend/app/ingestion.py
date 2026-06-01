import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .chunking import TextChunk, split_text_into_chunks
from .database import Document, DocumentChunk
from .embeddings import EMBEDDING_MODEL_NAME, embed_passages


class IngestDocumentRequest(BaseModel):
    title: str | None = None
    text: str = Field(min_length=1)
    source_system: str = "manual"
    source_id: str | None = None
    source_type: str = "document"
    user_id: uuid.UUID | None = None
    profile_id: uuid.UUID | None = None
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentResponse(BaseModel):
    id: uuid.UUID
    title: str | None
    source_system: str
    source_id: str | None
    source_type: str
    user_id: uuid.UUID | None
    profile_id: uuid.UUID | None
    tags: list[str]
    metadata: dict[str, Any]
    chunk_count: int
    ingested_at: datetime | None


class AternumTagPayload(BaseModel):
    name: str
    type: str | None = None


class AternumBlockPayload(BaseModel):
    type: str = "text"
    content: Any = None
    order: int = 0


class AternumNodePayload(BaseModel):
    id: str
    user_id: uuid.UUID | None = None
    profile_id: uuid.UUID | None = None
    name: str | None = None
    title: str | None = None
    type: str = "node"
    blocks: list[AternumBlockPayload] = Field(default_factory=list)
    tags: list[AternumTagPayload | str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AternumBulkIngestRequest(BaseModel):
    nodes: list[AternumNodePayload] = Field(min_length=1)


class BulkIngestResponse(BaseModel):
    documents: list[DocumentResponse]


def ingest_document(database_session: Session, ingest_request: IngestDocumentRequest) -> Document:
    existing_document = find_existing_source_document(database_session, ingest_request)
    if existing_document is not None:
        replace_existing_document(database_session, existing_document)

    text_chunks = split_text_into_chunks(ingest_request.text)
    if not text_chunks:
        raise ValueError("Document text must contain at least one word")

    chunk_embeddings = embed_passages([text_chunk.content for text_chunk in text_chunks])
    document = create_document_record(database_session, ingest_request)

    for chunk_index, (text_chunk, chunk_embedding) in enumerate(zip(text_chunks, chunk_embeddings, strict=True)):
        database_session.add(
            create_document_chunk_record(
                document_id=document.id,
                chunk_index=chunk_index,
                text_chunk=text_chunk,
                chunk_embedding=chunk_embedding,
            )
        )

    database_session.commit()
    database_session.refresh(document)
    return document


def find_existing_source_document(
    database_session: Session,
    ingest_request: IngestDocumentRequest,
) -> Document | None:
    if ingest_request.source_id is None:
        return None

    return database_session.scalar(
        select(Document).where(
            Document.source_system == ingest_request.source_system,
            Document.source_id == ingest_request.source_id,
        )
    )


def replace_existing_document(database_session: Session, existing_document: Document) -> None:
    database_session.execute(delete(DocumentChunk).where(DocumentChunk.document_id == existing_document.id))
    database_session.delete(existing_document)
    database_session.flush()


def create_document_record(database_session: Session, ingest_request: IngestDocumentRequest) -> Document:
    document = Document(
        title=ingest_request.title,
        body=ingest_request.text,
        source_system=ingest_request.source_system,
        source_id=ingest_request.source_id,
        source_type=ingest_request.source_type,
        user_id=ingest_request.user_id,
        profile_id=ingest_request.profile_id,
        tags=sorted(set(ingest_request.tags)),
        extra_metadata=ingest_request.metadata,
    )
    database_session.add(document)
    database_session.flush()
    return document


def create_document_chunk_record(
    document_id: uuid.UUID,
    chunk_index: int,
    text_chunk: TextChunk,
    chunk_embedding: list[float],
) -> DocumentChunk:
    token_estimate = max(1, len(text_chunk.content.split()))
    return DocumentChunk(
        document_id=document_id,
        chunk_index=chunk_index,
        content=text_chunk.content,
        embedding=chunk_embedding,
        token_estimate=token_estimate,
        extra_metadata={
            "chunk_index": chunk_index,
            "word_start": text_chunk.word_start,
            "word_end": text_chunk.word_end,
            "token_estimate": token_estimate,
            "embedding_model": EMBEDDING_MODEL_NAME,
        },
    )


def document_to_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=document.id,
        title=document.title,
        source_system=document.source_system,
        source_id=document.source_id,
        source_type=document.source_type,
        user_id=document.user_id,
        profile_id=document.profile_id,
        tags=document.tags or [],
        metadata=document.extra_metadata or {},
        chunk_count=len(document.chunks),
        ingested_at=document.ingested_at,
    )


def build_ingest_request_from_aternum_node(node: AternumNodePayload) -> IngestDocumentRequest:
    text_sections = [text_value for text_value in [node.title, node.name] if text_value]

    for block in sorted(node.blocks, key=lambda block_payload: block_payload.order):
        block_text = extract_text_from_aternum_block(block)
        if block_text:
            text_sections.append(block_text)

    return IngestDocumentRequest(
        title=node.title or node.name,
        text="\n\n".join(text_sections).strip() or node.id,
        source_system="aternum",
        source_id=node.id,
        source_type=node.type,
        user_id=node.user_id,
        profile_id=node.profile_id,
        tags=normalize_aternum_tag_names(node.tags),
        metadata={**node.metadata, "node_id": node.id, "node_type": node.type},
    )


def extract_text_from_aternum_block(block: AternumBlockPayload) -> str:
    if isinstance(block.content, str):
        return block.content.strip()
    if not isinstance(block.content, dict):
        return ""

    text_values: list[str] = []
    for content_key in ("text", "body", "caption", "alt", "description", "transcript", "url", "path"):
        content_value = block.content.get(content_key)
        if isinstance(content_value, str) and content_value.strip():
            text_values.append(content_value.strip())

    return "\n".join(text_values)


def normalize_aternum_tag_names(tags: list[AternumTagPayload | str]) -> list[str]:
    tag_names = [tag if isinstance(tag, str) else tag.name for tag in tags]
    return sorted({tag_name.strip() for tag_name in tag_names if tag_name.strip()})
