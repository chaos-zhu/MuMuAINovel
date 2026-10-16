"""本地知识库 API（第一阶段：项目级 TXT/Markdown/JSON）。"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.common import verify_project_access
from app.database import get_db
from app.logger import get_logger
from app.models.knowledge import KnowledgeBase, KnowledgeDocument
from app.schemas.knowledge import KnowledgeBaseCreate, KnowledgeBaseUpdate, KnowledgeSearchRequest
from app.services.knowledge_service import knowledge_service

router = APIRouter(prefix="/api", tags=["本地知识库"])
logger = get_logger(__name__)


def _user_id(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")
    return user_id


@router.get("/projects/{project_id}/knowledge-bases")
async def list_knowledge_bases(project_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = _user_id(request)
    await verify_project_access(project_id, user_id, db)
    return {"success": True, "items": await knowledge_service.list_bases(user_id, project_id, db)}


@router.post("/projects/{project_id}/knowledge-bases")
async def create_knowledge_base(project_id: str, payload: KnowledgeBaseCreate, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = _user_id(request)
    await verify_project_access(project_id, user_id, db)
    base = KnowledgeBase(user_id=user_id, project_id=project_id, name=payload.name, description=payload.description, scope="project", status="active", settings={"retrieval_enabled": True, "top_k": 8, "min_score": 0.25, "max_context_chars": 6000})
    db.add(base)
    await db.commit()
    await db.refresh(base)
    return {"success": True, "item": knowledge_service._base_dict(base, 0, 0)}


@router.patch("/knowledge-bases/{knowledge_base_id}")
async def update_knowledge_base(knowledge_base_id: str, payload: KnowledgeBaseUpdate, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = _user_id(request)
    base = await knowledge_service.get_base(knowledge_base_id, user_id, db)
    if not base:
        raise HTTPException(status_code=404, detail="知识库不存在")
    updates = payload.model_dump(exclude_unset=True)
    if "settings" in updates:
        current = knowledge_service.retrieval_settings(base)
        requested = updates["settings"] or {}
        current.update({key: value for key, value in requested.items() if key in {"retrieval_enabled", "top_k", "min_score", "max_context_chars"}})
        current["top_k"] = max(1, min(30, int(current["top_k"])))
        current["min_score"] = max(0.0, min(1.0, float(current["min_score"])))
        current["max_context_chars"] = max(1000, min(20000, int(current["max_context_chars"])))
        updates["settings"] = current
    for key, value in updates.items():
        setattr(base, key, value)
    await db.commit()
    await db.refresh(base)
    return {"success": True, "item": knowledge_service._base_dict(base, 0, 0)}


@router.get("/knowledge-bases/{knowledge_base_id}/documents")
async def list_documents(knowledge_base_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = _user_id(request)
    base = await knowledge_service.get_base(knowledge_base_id, user_id, db)
    if not base:
        raise HTTPException(status_code=404, detail="知识库不存在")
    return {"success": True, "items": [knowledge_service.document_dict(item) for item in await knowledge_service.list_documents(knowledge_base_id, user_id, db)]}


@router.post("/knowledge-bases/{knowledge_base_id}/documents")
async def upload_document(knowledge_base_id: str, request: Request, file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    user_id = _user_id(request)
    base = await knowledge_service.get_base(knowledge_base_id, user_id, db)
    if not base:
        raise HTTPException(status_code=404, detail="知识库不存在")
    content = await file.read()
    try:
        document, action = await knowledge_service.save_document(base, user_id, file.filename or "document.txt", file.content_type, content, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if action == "created":
        task_id = await knowledge_service.enqueue_index(document, db)
    else:
        task_id = None
    return {"success": True, "action": action, "document": knowledge_service.document_dict(document), "task_id": task_id}


async def _get_document(document_id: str, user_id: str, db: AsyncSession) -> KnowledgeDocument:
    document = (await db.execute(select(KnowledgeDocument).where(KnowledgeDocument.id == document_id, KnowledgeDocument.user_id == user_id))).scalar_one_or_none()
    if not document:
        raise HTTPException(status_code=404, detail="知识库文档不存在")
    return document


@router.get("/knowledge-documents/{document_id}")
async def get_document(document_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    return {"success": True, "item": knowledge_service.document_dict(await _get_document(document_id, _user_id(request), db))}


@router.delete("/knowledge-documents/{document_id}")
async def remove_document(document_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    document = await _get_document(document_id, _user_id(request), db)
    await knowledge_service.delete_document(document, db)
    return {"success": True, "message": "文档已删除"}


@router.post("/knowledge-documents/{document_id}/reindex")
async def reindex_document(document_id: str, request: Request, db: AsyncSession = Depends(get_db)):
    document = await _get_document(document_id, _user_id(request), db)
    document.status = "pending"
    document.error_message = None
    await db.commit()
    task_id = await knowledge_service.enqueue_index(document, db)
    return {"success": True, "task_id": task_id}


@router.post("/knowledge-bases/{knowledge_base_id}/search")
async def search_knowledge(knowledge_base_id: str, payload: KnowledgeSearchRequest, request: Request, db: AsyncSession = Depends(get_db)):
    user_id = _user_id(request)
    base = await knowledge_service.get_base(knowledge_base_id, user_id, db)
    if not base:
        raise HTTPException(status_code=404, detail="知识库不存在")
    hits = await knowledge_service.search(base, payload.query, payload.top_k, payload.document_ids, payload.min_score)
    return {"success": True, "query": payload.query, "items": hits, "total": len(hits)}
