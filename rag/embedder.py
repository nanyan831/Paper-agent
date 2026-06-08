"""
文本嵌入服务 —— 将论文文本转为向量
"""
import logging
from typing import Union
from functools import lru_cache

import numpy as np

logger = logging.getLogger(__name__)

# 全局缓存模型实例
_model = None


def _get_model():
    """懒加载嵌入模型"""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        from config import EMBEDDING_MODEL
        logger.info(f"正在加载嵌入模型: {EMBEDDING_MODEL}")
        _model = SentenceTransformer(EMBEDDING_MODEL)
        logger.info("嵌入模型加载完成")
    return _model


class EmbeddingService:
    """文本嵌入服务"""

    def __init__(self):
        self._model = None

    @property
    def model(self):
        if self._model is None:
            self._model = _get_model()
        return self._model

    def embed_text(self, text: str) -> list[float]:
        """将单条文本转为向量"""
        if not text or not text.strip():
            from config import EMBEDDING_DIMENSION
            return [0.0] * EMBEDDING_DIMENSION
        embedding = self.model.encode(text, normalize_embeddings=True)
        return embedding.tolist()

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """批量嵌入"""
        if not texts:
            return []
        # 过滤空文本
        cleaned = [t if t and t.strip() else "empty" for t in texts]
        embeddings = self.model.encode(
            cleaned,
            normalize_embeddings=True,
            batch_size=32,
            show_progress_bar=len(cleaned) > 50,
        )
        return embeddings.tolist()

    def embed_paper(self, paper: dict) -> list[float]:
        """
        将论文信息组合后嵌入。
        组合策略：title(权重2) + abstract + keywords
        """
        parts = []
        title = paper.get("title", "")
        if title:
            parts.append(title)
            parts.append(title)  # 标题重复一次提升权重
        abstract = paper.get("abstract", "")
        if abstract:
            parts.append(abstract)
        keywords = paper.get("keywords", "")
        if keywords:
            parts.append(keywords)

        combined = " ".join(parts)
        return self.embed_text(combined)

    def similarity(self, vec_a: list[float], vec_b: list[float]) -> float:
        """计算两个向量的余弦相似度"""
        a = np.array(vec_a)
        b = np.array(vec_b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
