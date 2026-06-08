"""
全局配置文件
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ==================== 路径配置 ====================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "papers.db"
CHROMA_DIR = DATA_DIR / "chroma_db"
LOG_DIR = DATA_DIR / "logs"

# 确保数据目录存在
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# ==================== 嵌入模型配置 ====================
# 本地模型（免费，中文优化）
EMBEDDING_MODEL = "shibing624/text2vec-base-chinese"
# 备选：多语言模型
# EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"

EMBEDDING_DIMENSION = 768  # text2vec-base-chinese 的维度

# ==================== 数据库配置 ====================
DB_POOL_SIZE = 5
FTS_TOKENIZER = "unicode61"  # SQLite FTS5 分词器

# ==================== 爬虫配置 ====================
CRAWLER_CONFIG = {
    "arxiv": {
        "enabled": True,
        "base_url": "http://export.arxiv.org/api/query",
        "max_results_per_query": 50,
        "rate_limit_seconds": 3,  # arXiv 要求至少 3 秒间隔
        # 文科相关分类
        "default_categories": [
            "econ",      # 经济学
            "q-fin",     # 量化金融
            "cs.CY",     # 计算与社会
            "cs.DL",     # 数字图书馆
            "cs.SI",     # 社会与信息网络
            "stat.AP",   # 统计应用
        ],
    },
    "semantic_scholar": {
        "enabled": True,
        "base_url": "https://api.semanticscholar.org/graph/v1",
        "api_key": os.getenv("S2_API_KEY", ""),  # 可选 API Key
        "max_results_per_query": 100,
        "rate_limit_seconds": 1,
    },
    "crossref": {
        "enabled": True,
        "base_url": "https://api.crossref.org/works",
        "mailto": os.getenv("CROSSREF_EMAIL", "user@example.com"),  # 礼貌池
        "max_results_per_query": 50,
        "rate_limit_seconds": 1,
    },
    "cnki": {
        "enabled": True,
        "base_url": "https://kns.cnki.net",
        "max_results_per_query": 20,
        "rate_limit_seconds": 5,  # 知网限制更严格
    },
    "rss": {
        "enabled": True,
        "feeds": [
            # 社科/人文相关 RSS 源
            "http://feeds.nature.com/nathumbehav",          # Nature Human Behaviour
            "http://rss.sciencedirect.com/publication/science/0049089X",  # Social Science Research
            "https://academic.oup.com/rss/site_6024/3981.xml",  # Social Forces
        ],
        "check_interval_hours": 6,
    },
}

# ==================== 调度配置 ====================
SCHEDULER_CONFIG = {
    "auto_crawl_interval_hours": 6,    # 自动爬取间隔
    "rss_check_interval_hours": 4,     # RSS 检查间隔
    "cleanup_interval_days": 30,       # 清理 30 天前的爬取日志
    "default_keywords": [
        # 文科热门关键词
        "社会学", "教育学", "哲学", "历史学", "文学批评",
        "政治学", "传播学", "心理学", "人类学", "法学",
        "sociology", "education", "philosophy", "history",
        "political science", "communication", "psychology",
    ],
}

# ==================== 搜索配置 ====================
SEARCH_CONFIG = {
    "default_top_k": 20,
    "max_top_k": 100,
    "semantic_weight": 0.6,    # 语义搜索权重
    "keyword_weight": 0.4,     # 关键词搜索权重
    "min_relevance_score": 0.3,
}

# ==================== 服务配置 ====================
SERVER_HOST = "0.0.0.0"
SERVER_PORT = 8000
CORS_ORIGINS = ["*"]

# ==================== DeepSeek Agent 配置 ====================
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
