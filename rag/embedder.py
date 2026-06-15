"""
文本嵌入服务 —— 将论文文本转为向量
"""
import logging
import threading
import time
from typing import Union
from functools import lru_cache

import numpy as np

logger = logging.getLogger(__name__)

# 全局缓存模型实例
_model = None
_model_lock = threading.Lock()

# 嵌入模型状态追踪
_embedding_state = {
    "status": "not_loaded",
    "model_name": None,
    "load_seconds": None,
    "error": None,
}


def _get_model():
    """懒加载嵌入模型（线程安全，更新全局状态）"""
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        from sentence_transformers import SentenceTransformer
        from config import EMBEDDING_MODEL
        _embedding_state["status"] = "loading"
        _embedding_state["model_name"] = EMBEDDING_MODEL
        _embedding_state["error"] = None
        logger.info(f"正在加载嵌入模型: {EMBEDDING_MODEL}")
        t0 = time.monotonic()
        try:
            _model = SentenceTransformer(EMBEDDING_MODEL)
            _embedding_state["status"] = "ready"
            _embedding_state["load_seconds"] = round(time.monotonic() - t0, 2)
            logger.info("嵌入模型加载完成")
        except Exception as exc:
            _embedding_state["status"] = "error"
            _embedding_state["error"] = str(exc)
            _embedding_state["load_seconds"] = round(time.monotonic() - t0, 2)
            logger.exception("嵌入模型加载失败")
            raise
        return _model


def get_embedding_status() -> dict:
    """返回嵌入模型当前状态的快照"""
    return dict(_embedding_state)


def warmup_embedding_model() -> None:
    """后台预热：触发模型加载但不做大量 encode"""
    try:
        _get_model()
        logger.info("嵌入模型预热完成")
    except Exception:
        logger.exception("嵌入模型预热失败")


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
