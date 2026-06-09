"""
向量存储 —— ChromaDB 封装
"""
import logging
from typing import Optional

import chromadb
from chromadb.config import Settings

from config import CHROMA_DIR, EMBEDDING_DIMENSION
from rag.embedder import EmbeddingService

logger = logging.getLogger(__name__)


class VectorStore:
    """ChromaDB 向量存储管理器"""

    COLLECTION_NAME = "papers"
    CHUNK_COLLECTION_NAME = "paper_chunks"

    def __init__(self, embedder: Optional[EmbeddingService] = None):
        self.embedder = embedder or EmbeddingService()
        self._client = None
        self._collection = None
        self._chunk_collection = None

    @property
    def client(self):
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=str(CHROMA_DIR),
                settings=Settings(anonymized_telemetry=False),
            )
            logger.info(f"ChromaDB 已连接: {CHROMA_DIR}")
        return self._client

    @property
    def collection(self):
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"向量集合 '{self.COLLECTION_NAME}' 已就绪, 当前文档数: {self._collection.count()}")
        return self._collection

    @property
    def chunk_collection(self):
        if self._chunk_collection is None:
            self._chunk_collection = self.client.get_or_create_collection(
                name=self.CHUNK_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"Chunk 向量集合 '{self.CHUNK_COLLECTION_NAME}' 已就绪，当前块数: {self._chunk_collection.count()}")
        return self._chunk_collection

    def add_paper(self, paper_id: str, paper: dict):
        """将论文嵌入并存入向量库"""
        embedding = self.embedder.embed_paper(paper)
        metadata = {
            "title": (paper.get("title") or "")[:500],
            "source": paper.get("source", "unknown"),
            "language": paper.get("language", "zh"),
            "publish_date": paper.get("publish_date", ""),
        }
        # 过滤 None 值
        metadata = {k: v for k, v in metadata.items() if v is not None}

        self.collection.upsert(
            ids=[paper_id],
            embeddings=[embedding],
            metadatas=[metadata],
            documents=[paper.get("abstract", "") or paper.get("title", "")],
        )

    def add_papers_batch(self, papers: list[dict]):
        """批量添加论文到向量库"""
        if not papers:
            return

        ids = []
        embeddings = []
        metadatas = []
        documents = []

        # 准备嵌入的文本
        texts = []
        for p in papers:
            parts = []
            title = p.get("title", "")
            if title:
                parts.extend([title, title])
            abstract = p.get("abstract", "")
            if abstract:
                parts.append(abstract)
            keywords = p.get("keywords", "")
            if keywords:
                parts.append(keywords)
            texts.append(" ".join(parts) if parts else "empty")

        # 批量嵌入
        batch_embeddings = self.embedder.embed_texts(texts)

        for i, p in enumerate(papers):
            paper_id = p.get("id")
            if not paper_id:
                continue
            ids.append(paper_id)
            embeddings.append(batch_embeddings[i])
            metadata = {
                "title": (p.get("title") or "")[:500],
                "source": p.get("source", "unknown"),
                "language": p.get("language", "zh"),
                "publish_date": p.get("publish_date", ""),
            }
            metadata = {k: v for k, v in metadata.items() if v is not None}
            metadatas.append(metadata)
            documents.append(p.get("abstract", "") or p.get("title", ""))

        if ids:
            # ChromaDB 批量操作限制，分批处理
            batch_size = 100
            for start in range(0, len(ids), batch_size):
                end = start + batch_size
                self.collection.upsert(
                    ids=ids[start:end],
                    embeddings=embeddings[start:end],
                    metadatas=metadatas[start:end],
                    documents=documents[start:end],
                )
            logger.info(f"批量添加 {len(ids)} 篇论文到向量库")

    def add_chunks_batch(self, chunks: list[dict]):
        """Batch add full-text chunks to the chunk vector collection."""
        if not chunks:
            return

        ids = []
        texts = []
        metadatas = []
        for chunk in chunks:
            chunk_id = chunk.get("id")
            content = chunk.get("content", "")
            if not chunk_id or not content:
                continue
            ids.append(chunk_id)
            texts.append(content)
            metadata = {
                "paper_id": chunk.get("paper_id", ""),
                "chunk_index": chunk.get("chunk_index", 0),
                "section": chunk.get("section", "body"),
                "page_start": chunk.get("page_start") or 0,
                "page_end": chunk.get("page_end") or 0,
            }
            metadatas.append(metadata)

        if not ids:
            return

        embeddings = self.embedder.embed_texts(texts)
        batch_size = 100
        for start in range(0, len(ids), batch_size):
            end = start + batch_size
            self.chunk_collection.upsert(
                ids=ids[start:end],
                embeddings=embeddings[start:end],
                metadatas=metadatas[start:end],
                documents=texts[start:end],
            )
        logger.info(f"批量添加 {len(ids)} 个全文块到向量库")

    def search(
        self,
        query: str,
        top_k: int = 20,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        """
        语义搜索论文

        Args:
            query: 查询文本
            top_k: 返回条数
            filters: ChromaDB where 过滤条件

        Returns:
            [{"id": str, "score": float, "metadata": dict, "document": str}, ...]
        """
        query_embedding = self.embedder.embed_text(query)

        search_kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k, self.collection.count() or 1),
        }
        if filters:
            search_kwargs["where"] = filters

        results = self.collection.query(**search_kwargs)

        papers = []
        if results and results["ids"] and results["ids"][0]:
            for i, paper_id in enumerate(results["ids"][0]):
                score = 1.0
                if results.get("distances") and results["distances"][0]:
                    # ChromaDB cosine 返回的是距离，转为相似度
                    score = 1 - results["distances"][0][i]
                papers.append({
                    "id": paper_id,
                    "score": score,
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                    "document": results["documents"][0][i] if results.get("documents") else "",
                })

        return papers

    def search_chunks(
        self,
        query: str,
        top_k: int = 20,
        filters: Optional[dict] = None,
    ) -> list[dict]:
        """Semantic search over full-text chunks."""
        query_embedding = self.embedder.embed_text(query)
        search_kwargs = {
            "query_embeddings": [query_embedding],
            "n_results": min(top_k, self.chunk_collection.count() or 1),
        }
        if filters:
            search_kwargs["where"] = filters

        results = self.chunk_collection.query(**search_kwargs)

        chunks = []
        if results and results["ids"] and results["ids"][0]:
            for i, chunk_id in enumerate(results["ids"][0]):
                score = 1.0
                if results.get("distances") and results["distances"][0]:
                    score = 1 - results["distances"][0][i]
                chunks.append({
                    "id": chunk_id,
                    "score": score,
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                    "content": results["documents"][0][i] if results.get("documents") else "",
                })
        return chunks

    def delete_paper(self, paper_id: str):
        """从向量库删除论文"""
        try:
            self.collection.delete(ids=[paper_id])
        except Exception as e:
            logger.warning(f"删除向量失败: {paper_id}, {e}")
        try:
            self.chunk_collection.delete(where={"paper_id": paper_id})
        except Exception as e:
            logger.warning(f"删除 chunk 向量失败: {paper_id}, {e}")

    def count(self) -> int:
        """返回向量库中的文档数量"""
        return self.collection.count()
