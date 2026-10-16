"""知识库向量存储适配器，复用现有 ChromaDB 与 ONNX Embedding。"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.services.memory_service import memory_service


class KnowledgeVectorStore:
    def __init__(self) -> None:
        self.client = memory_service.client
        self.embedding_model = memory_service.embedding_model

    def _collection_name(self, user_id: str) -> str:
        user_hash = hashlib.sha256(user_id.encode()).hexdigest()[:12]
        return f"knowledge_u_{user_hash}"

    def collection(self, user_id: str):
        return self.client.get_or_create_collection(
            name=self._collection_name(user_id),
            configuration={"hnsw": {"space": "cosine"}},
            metadata={"kind": "knowledge", "user_id": user_id},
        )

    def upsert(self, user_id: str, items: list[dict[str, Any]]) -> None:
        if not items:
            return
        collection = self.collection(user_id)
        contents = [item["content"] for item in items]
        embeddings = self.embedding_model.encode(contents).tolist()
        metadatas = []
        for item in items:
            metadata = {
                "user_id": user_id,
                "project_id": item["project_id"],
                "knowledge_base_id": item["knowledge_base_id"],
                "document_id": item["document_id"],
                "chunk_index": int(item["chunk_index"]),
                "title": item.get("title", "")[:200],
                "original_filename": item.get("original_filename", "")[:500],
                "section_title": item.get("section_title") or "",
                "heading_path": json.dumps(item.get("heading_path") or [], ensure_ascii=False),
            }
            metadatas.append(metadata)
        collection.upsert(
            ids=[item["id"] for item in items],
            documents=contents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def delete_document(self, user_id: str, document_id: str) -> None:
        self.collection(user_id).delete(where={"document_id": document_id})

    def search(
        self,
        user_id: str,
        knowledge_base_id: str,
        query: str,
        top_k: int,
        document_ids: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        collection = self.collection(user_id)
        # Chroma rejects queries whose n_results exceeds the number of stored
        # vectors.  A newly-created knowledge base has an empty collection,
        # so return no hits instead of failing generation requests.
        count = collection.count()
        if count == 0:
            return []
        top_k = min(top_k, count)
        conditions: list[dict[str, Any]] = [{"knowledge_base_id": knowledge_base_id}]
        if document_ids:
            conditions.append({"document_id": {"$in": document_ids}})
        where = conditions[0] if len(conditions) == 1 else {"$and": conditions}
        query_embedding = self.embedding_model.encode(query).tolist()
        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        hits: list[dict[str, Any]] = []
        ids = result.get("ids", [[]])[0]
        documents = result.get("documents", [[]])[0]
        metadatas = result.get("metadatas", [[]])[0]
        distances = result.get("distances", [[]])[0]
        for index, chunk_id in enumerate(ids):
            distance = float(distances[index]) if index < len(distances) else 1.0
            score = max(0.0, min(1.0, 1.0 - distance / 2.0))
            hits.append({
                "chunk_id": chunk_id,
                "content": documents[index] if index < len(documents) else "",
                "score": score,
                "distance": distance,
                "metadata": metadatas[index] if index < len(metadatas) else {},
            })
        return hits


knowledge_vector_store = KnowledgeVectorStore()
