from pydantic import BaseModel, Field
from typing import List, Optional


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The question about F1 regulations")


class Source(BaseModel):
    section: str
    section_name: str
    doc_title: str
    article: str
    article_title: Optional[str] = None
    page: Optional[int] = None
    text: str


class QueryMetadata(BaseModel):
    model: str
    chunks_retrieved: int
    chunks_used: int
    response_time_ms: int


class QueryResponse(BaseModel):
    answer: str
    sources: List[Source]
    metadata: QueryMetadata


class IngestResponse(BaseModel):
    status: str
    message: str
    chunks_created: int
    collection: str


class HealthResponse(BaseModel):
    status: str
    profile: str
    chroma_connected: bool
