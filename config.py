"""
=============================================================================
简历优化助手 · 全局配置文件
=============================================================================
统一管理所有硬编码常量：路径、模型参数、向量维度、chunk 策略等。
修改配置只需编辑此文件，无需深入业务代码。
=============================================================================
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── 加载 .env 文件（优先级高于系统环境变量）────────────────────────
# 优先从项目根目录加载 .env；不存在则回退到系统环境变量
ENV_PATH = Path(__file__).parent / ".env"
if ENV_PATH.exists():
    load_dotenv(ENV_PATH, override=True)

# ══════════════════════════════════════════════════════════════
# 路径常量
# ══════════════════════════════════════════════════════════════
BASE_DIR = Path(__file__).parent
CHROMA_DIR = BASE_DIR / "chroma_db"
DATA_DIR = BASE_DIR / "data"
LOG_DIR = DATA_DIR / "logs"
SURVEY_FILE = DATA_DIR / "surveys.json"

# 自动创建必要目录
for _d in (CHROMA_DIR, DATA_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════
# API / LLM 配置
# ══════════════════════════════════════════════════════════════
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
HF_ENDPOINT = os.getenv("HF_ENDPOINT", "https://hf-mirror.com")

# LLM 提供商选择：deepseek | ollama | qwen
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "deepseek")

# DeepSeek 配置
DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-chat"
DEEPSEEK_MAX_TOKENS = 4096
DEEPSEEK_TEMPERATURE = 0.7

# Ollama 配置（本地部署）
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

# 通义千问配置（阿里云）
QWEN_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"
QWEN_MODEL = "qwen-plus"
QWEN_API_KEY = os.getenv("QWEN_API_KEY", "")

# 通用 LLM 参数
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.7"))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))

# ══════════════════════════════════════════════════════════════
# RAG / 向量库配置
# ══════════════════════════════════════════════════════════════

# 向量维度
TFIDF_N_FEATURES = 384          # LocalTFIDF 哈希向量维度
BGE_EMBEDDING_DIM = 512         # bge-small-zh 输出维度

# Chunk 分割策略
CHUNK_SIZE = 500                # 通用文本分块大小
CHUNK_OVERLAP = 80              # 分块重叠字符数
MD_CHUNK_SIZE = 800             # Markdown 文本分块大小
MD_CHUNK_OVERLAP = 100          # Markdown 分块重叠字符数

# 检索配置
TOP_K_RETRIEVAL = 5             # 最终返回片段数
VECTOR_SEARCH_K = 10            # 向量检索候选数
KEYWORD_SEARCH_K = 5            # 关键词检索候选数
RERANK_TOP_K = 5               # 重排序后保留数

# Embedding 模型选择：tfidf | bge
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "tfidf")

# BGE 模型名称（可通过环境变量覆盖）
BGE_MODEL_NAME = os.getenv("BGE_MODEL_NAME", "BAAI/bge-small-zh-v1.5")

# Chroma 配置
CHROMA_COLLECTION_NAME = "resume_knowledge"

# ══════════════════════════════════════════════════════════════
# 分句分隔符（中文优先）
# ══════════════════════════════════════════════════════════════
TEXT_SEPARATORS = [
    "\n\n", "\n", "。", "！", "？", "；",
    ".", "!", "?", ";", " "
]

MD_SEPARATORS = [
    "\n## ", "\n### ", "\n#### ",
    "\n\n", "\n", "。", "！", "？", "；",
    ".", "!", "?", ";", " "
]

# ══════════════════════════════════════════════════════════════
# 批量处理配置
# ══════════════════════════════════════════════════════════════
BATCH_LOAD_SIZE = 100            # 向量库分批加载，每批最多文档数
MAX_FILE_SIZE_MB = 20            # 单文件上传上限（MB）

# ══════════════════════════════════════════════════════════════
# UI 配置
# ══════════════════════════════════════════════════════════════
PAGE_TITLE = "简历优化助手"
PAGE_ICON = "📄"
PAGE_LAYOUT = "wide"
