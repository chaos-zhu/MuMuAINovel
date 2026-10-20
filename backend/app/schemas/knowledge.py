"""知识库 Pydantic schemas。"""
from typing import Any, Optional
from pydantic import BaseModel, Field


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(default="项目知识库", min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)


class KnowledgeBaseUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)
    settings: Optional[dict[str, Any]] = None


class KnowledgeSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000)
    top_k: int = Field(default=8, ge=1, le=30)
    document_ids: list[str] = Field(default_factory=list, max_length=50)
    min_score: float = Field(default=0.0, ge=0.0, le=1.0)


class KnowledgeDocumentResponse(BaseModel):
    id: str
    knowledge_base_id: str
    title: str
    original_filename: str
    source_type: str
    mime_type: Optional[str]
    file_size: int
    status: str
    error_message: Optional[str]
    extracted_char_count: int
    chunk_count: int
    indexed_at: Optional[str]
    created_at: Optional[str]
    updated_at: Optional[str]


class KnowledgeBaseResponse(BaseModel):
    id: str
    project_id: str
    name: str
    description: Optional[str]
    scope: str
    status: str
    document_count: int = 0
    chunk_count: int = 0
    created_at: Optional[str]
    updated_at: Optional[str]
