from pydantic import BaseModel, Field
from typing import List, Optional


class QueryRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The question about F1 regulations")


class Paragraph(BaseModel):
    text: str
    highlight: bool = False  # True = this paragraph is what the answer relies on


class Source(BaseModel):
    ref: int                         # matches [1], [2] ... in the answer
    label: str                       # "Article C4.1 – Minimum Mass"
    section: str
    section_name: str
    doc_title: str
    article: str
    article_title: Optional[str] = None
    page: Optional[int] = None
    issue: Optional[str] = None
    date: Optional[str] = None
    similarity: Optional[float] = None
    match: str = "semantic"          # "semantic" or "article_number"
    cited: bool = False              # the answer cites this source as [ref]
    truncated: bool = False          # a very long clause was shortened
    paragraphs: List[Paragraph]


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