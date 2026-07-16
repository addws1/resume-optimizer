"""
=============================================================================
简历优化助手 · RAG 知识库核心
=============================================================================
提供两种 Embedding 实现 + 智能文本分割 + 多路召回检索。

Embedding 后端：
  - LocalTFIDFEmbeddings：纯本地哈希向量（384维），零网络依赖
  - BGEEmbeddings：bge-small-zh 中文语义模型（512维），需首次下载

检索策略：
  - 关键词召回（BM25） + 向量语义召回 → 去重 → 简单重排序
  - 支持文档内容去重，避免重复向量化

文本分割：
  - 通用文本分割器（RecursiveCharacterTextSplitter）
  - Markdown 专用分割器（保留标题层级）

性能说明：
  重型依赖（sklearn / chromadb / langchain）均采用函数内懒加载，
  仅在实际调用 RAG 功能时才导入，不影响页面首屏加载速度。
=============================================================================
"""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path
from typing import Optional, Callable

import streamlit as st

from config import (
    CHROMA_DIR, CHROMA_COLLECTION_NAME,
    TFIDF_N_FEATURES, BGE_EMBEDDING_DIM, BGE_MODEL_NAME,
    CHUNK_SIZE, CHUNK_OVERLAP,
    MD_CHUNK_SIZE, MD_CHUNK_OVERLAP,
    TEXT_SEPARATORS, MD_SEPARATORS,
    TOP_K_RETRIEVAL, VECTOR_SEARCH_K, KEYWORD_SEARCH_K, RERANK_TOP_K,
    EMBEDDING_BACKEND, HF_ENDPOINT,
    BATCH_LOAD_SIZE,
)
from utils.logger import log_kb_operation, log_error, log_info, log_debug, log_warning


# ══════════════════════════════════════════════════════════════
# Embedding 实现 1：LocalTFIDF（离线可用）
# ══════════════════════════════════════════════════════════════

class LocalTFIDFEmbeddings:
    """
    基于 sklearn HashingVectorizer 的中文文本向量化类。

    特性：
    - 纯本地计算，零网络依赖
    - 字符级 n-gram（2-4 字），适配中文
    - 384 维固定输出
    - 实现 LangChain 兼容的 embed_documents / embed_query 接口
    """

    def __init__(self, n_features: int = TFIDF_N_FEATURES):
        from sklearn.feature_extraction.text import HashingVectorizer
        self.vectorizer = HashingVectorizer(
            n_features=n_features,
            analyzer="char",          # 字符级 n-gram，适配中文
            ngram_range=(2, 4),       # 2-4 字组合
            lowercase=False,
            alternate_sign=False,
        )
        self._n_features = n_features

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量向量化文档"""
        if not texts:
            return []
        from sklearn.preprocessing import normalize
        X = self.vectorizer.transform(texts)
        X = normalize(X, norm="l2")
        return X.toarray().tolist()

    def embed_query(self, text: str) -> list[float]:
        """向量化查询文本"""
        return self.embed_documents([text])[0]


# ══════════════════════════════════════════════════════════════
# Embedding 实现 2：BGE 中文语义模型（需联网下载一次）
# ══════════════════════════════════════════════════════════════

class BGEEmbeddings:
    """
    基于 BAAI/bge-small-zh-v1.5 的中文语义向量类。

    特性：
    - 512 维语义向量，中文场景效果优于 TF-IDF
    - 支持 HF 镜像（国内可正常下载）
    - 兼容 LangChain embedding 接口
    - 首次使用自动下载模型（约 100MB），后续从缓存加载

    注意：需要在环境中设置 HF_ENDPOINT=https://hf-mirror.com（国内）
    """

    def __init__(self, model_name: str = ""):
        self._model_name = model_name or BGE_MODEL_NAME
        self._model = None
        self._load_model()

    def _load_model(self):
        """懒加载模型，设置 HF 镜像"""
        # 设置镜像（必须在 import sentence_transformers 之前）
        if HF_ENDPOINT:
            os.environ.setdefault("HF_ENDPOINT", HF_ENDPOINT)

        try:
            from sentence_transformers import SentenceTransformer
            log_info(f"正在加载 BGE 模型: {self._model_name} ...")
            self._model = SentenceTransformer(self._model_name)
            log_info(f"BGE 模型加载完成，向量维度: {self._model.get_sentence_embedding_dimension()}")
        except Exception as e:
            log_error("bge_embeddings", e, f"模型 {self._model_name} 加载失败，回退到 TF-IDF")
            self._model = None

    @property
    def is_available(self) -> bool:
        return self._model is not None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts or not self._model:
            return LocalTFIDFEmbeddings().embed_documents(texts)
        embeddings = self._model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]


# ══════════════════════════════════════════════════════════════
# Embedding 工厂（带缓存）
# ══════════════════════════════════════════════════════════════

@st.cache_resource
def get_embeddings(backend: str = ""):
    """
    获取 Embedding 实例（Streamlit 缓存，全局复用）。

    Args:
        backend: "tfidf" | "bge"，留空则使用配置文件设置

    Returns:
        LocalTFIDFEmbeddings 或 BGEEmbeddings 实例
    """
    target = backend or get_current_emb_backend()

    if target == "bge":
        bge = BGEEmbeddings()
        if bge.is_available:
            log_info("使用 BGE 语义向量模型")
            return bge
        else:
            log_warning("BGE 模型不可用，回退到 TF-IDF")
            return LocalTFIDFEmbeddings()

    # 默认使用 TF-IDF
    log_info("使用 LocalTFIDF 哈希向量模型")
    return LocalTFIDFEmbeddings()


# ══════════════════════════════════════════════════════════════
# 文本分割器
# ══════════════════════════════════════════════════════════════

def get_text_splitter(is_markdown: bool = False):
    """
    获取文本分割器。首次调用时懒加载 langchain 分割器。

    Args:
        is_markdown: 是否使用 Markdown 专用分割策略

    Returns:
        RecursiveCharacterTextSplitter 实例
    """
    from langchain_text_splitters import RecursiveCharacterTextSplitter

    if is_markdown:
        return RecursiveCharacterTextSplitter(
            chunk_size=MD_CHUNK_SIZE,
            chunk_overlap=MD_CHUNK_OVERLAP,
            separators=MD_SEPARATORS,
        )
    else:
        return RecursiveCharacterTextSplitter(
            chunk_size=CHUNK_SIZE,
            chunk_overlap=CHUNK_OVERLAP,
            separators=TEXT_SEPARATORS,
        )


def detect_is_markdown(content: str) -> bool:
    """
    检测文本内容是否为 Markdown 格式。

    判断依据：
    - 包含 # 标题行
    - 包含 ``` 代码块
    - 包含 **加粗** 或 *斜体*
    - 包含 [链接](url) 语法
    """
    md_patterns = [
        r'^#{1,6}\s+\S',     # 标题
        r'```',               # 代码块
        r'\*\*[^*]+\*\*',     # 加粗
        r'\[.+?\]\(.+?\)',    # 链接
        r'^\s*[-*+]\s+',      # 无序列表
        r'^\s*\d+\.\s+',      # 有序列表
    ]
    score = 0
    for pat in md_patterns:
        if re.search(pat, content, re.MULTILINE):
            score += 1
    return score >= 2


# ══════════════════════════════════════════════════════════════
# 向量存储
# ══════════════════════════════════════════════════════════════

@st.cache_resource
def _get_cached_vectorstore(embedding_backend: str):
    """缓存 Chroma vectorstore 实例（首次调用时懒加载 chromadb）"""
    from langchain_community.vectorstores import Chroma

    embeddings = get_embeddings(embedding_backend)
    try:
        vectorstore = Chroma(
            persist_directory=str(CHROMA_DIR),
            embedding_function=embeddings,
            collection_name=CHROMA_COLLECTION_NAME,
        )
        return vectorstore
    except Exception as e:
        log_error("chroma_init", e, "向量库初始化失败")
        return None


def get_current_emb_backend() -> str:
    """
    获取当前会话选择的 Embedding 后端。
    优先读侧边栏的会话级选择（config.EMBEDDING_BACKEND 是 import 时定死的，
    切换后端必须走 session_state 才能生效），回退到 .env 配置。
    """
    try:
        backend = st.session_state.get("sidebar_emb_backend")
    except Exception:
        backend = None
    return backend or EMBEDDING_BACKEND


def get_vector_store(embedding_backend: str = "") -> Optional[Chroma]:
    """
    获取或创建 Chroma 向量存储。

    Args:
        embedding_backend: embedding 后端名称

    Returns:
        Chroma 实例或 None
    """
    target = embedding_backend or get_current_emb_backend()
    return _get_cached_vectorstore(target)


def reset_vector_store_cache():
    """清除向量存储缓存（切换 embedding 后端后使用）"""
    _get_cached_vectorstore.clear()
    get_embeddings.clear()


# ══════════════════════════════════════════════════════════════
# 文档去重
# ══════════════════════════════════════════════════════════════

def _compute_chunk_hash(text: str) -> str:
    """计算文本块的 MD5 哈希"""
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()


def _get_existing_hashes(vectorstore: Chroma) -> set:
    """获取向量库中已有文档的哈希集合（用于去重）"""
    try:
        collection = vectorstore._collection
        results = collection.get()
        if results and results.get("metadatas"):
            return {m.get("chunk_hash", "") for m in results["metadatas"] if m}
        return set()
    except Exception:
        return set()


# ══════════════════════════════════════════════════════════════
# 文档添加（去重 + 分批）
# ══════════════════════════════════════════════════════════════

def add_documents_to_kb(
    uploaded_files,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
) -> int:
    """
    将上传的文档分块并向量化存入 Chroma。

    特性：
    - 自动检测 Markdown / 普通文本，使用对应分割器
    - chunk 内容去重（避免重复向量化）
    - 分批加载，限制内存占用
    - 通过 progress_callback 反馈进度

    Args:
        uploaded_files: Streamlit UploadedFile 列表
        progress_callback: 可选进度回调 (current, total, filename)

    Returns:
        成功处理的文件数
    """
    vectorstore = get_vector_store()
    if vectorstore is None:
        return 0

    # 获取已存在的 hash 集合（用于跨文件去重）
    existing_hashes = _get_existing_hashes(vectorstore)
    total_added = 0
    file_count = 0
    total_files = len(uploaded_files)

    for idx, uploaded_file in enumerate(uploaded_files):
        fname = uploaded_file.name

        # 进度回调
        if progress_callback:
            progress_callback(idx, total_files, f"正在处理 {fname} ...")

        # 读取文件
        try:
            from utils.file_utils import read_uploaded_file
            content = read_uploaded_file(uploaded_file)
        except Exception as e:
            log_warning(f"跳过无法读取的文件: {fname}, 原因: {e}")
            continue

        if not content.strip():
            log_warning(f"跳过空文件: {fname}")
            continue

        # 选择分割器
        is_md = detect_is_markdown(content)
        splitter = get_text_splitter(is_markdown=is_md)
        split_type = "Markdown分割器" if is_md else "通用分割器"
        log_debug(f"{fname}: 使用 {split_type}")

        # 分块
        chunks = splitter.create_documents(
            texts=[content],
            metadatas=[{"source": fname}],
        )

        # 去重 + 添加 chunk_hash
        batch = []
        batch_hashes = set()
        skipped_dup = 0
        for chunk in chunks:
            h = _compute_chunk_hash(chunk.page_content)
            if h in existing_hashes or h in batch_hashes:
                skipped_dup += 1
                continue
            chunk.metadata["chunk_hash"] = h
            batch.append(chunk)
            batch_hashes.add(h)

        if skipped_dup > 0:
            log_debug(f"{fname}: 跳过 {skipped_dup} 个重复 chunk")

        # 分批加载到向量库（每批 BATCH_LOAD_SIZE）
        if batch:
            try:
                for i in range(0, len(batch), BATCH_LOAD_SIZE):
                    sub_batch = batch[i:i + BATCH_LOAD_SIZE]
                    vectorstore.add_documents(sub_batch)

                vectorstore.persist()
                existing_hashes.update(batch_hashes)
                total_added += len(batch)
                file_count += 1

                # 更新 session_state
                if fname not in st.session_state.get("kb_doc_names", []):
                    st.session_state.setdefault("kb_doc_names", []).append(fname)

                log_kb_operation(
                    "import",
                    doc_count=len(batch),
                    doc_name=fname,
                    detail=f"chunk数={len(chunks)}, 去重跳过={skipped_dup}, 类型={split_type}",
                )

            except Exception as e:
                log_error("kb_add", e, f"向量化失败: {fname}")
                continue

    # 最终进度
    if progress_callback:
        progress_callback(total_files, total_files, f"完成！共导入 {file_count} 个文件，新增 {total_added} 个片段")

    log_kb_operation("import_summary", doc_count=total_added,
                     detail=f"成功文件数={file_count}/{total_files}")
    return file_count


# ══════════════════════════════════════════════════════════════
# 示例知识库（一键加载，用于演示 / 首次使用）
# ══════════════════════════════════════════════════════════════

# 预置的简历写作规范文档，用户可一键导入向量库，
# 无需自己准备文件就能体验 RAG 增强效果。
SAMPLE_KNOWLEDGE = {
    "STAR法则写作指南.md": """# STAR 法则简历写作指南

## 什么是 STAR 法则
STAR 是 Situation（情境）、Task（任务）、Action（行动）、Result（结果）四个单词的首字母缩写，
是 HR 筛选简历时最常用的评估框架。

## 四个要素详解

### S - 情境
描述项目发生的背景和环境。回答"在什么情况下？"
- 正确示例：在公司从单体架构向微服务迁移的大背景下……
- 错误示例：我参与了一个项目……

### T - 任务
你在该项目中承担的具体职责和目标。回答"要做什么？"
- 正确示例：负责设计并实现用户认证模块，要求 QPS 达到 1000+
- 错误示例：负责开发工作

### A - 行动
你采取了哪些具体措施来完成任务。回答"怎么做的？"
- 正确示例：选用 JWT + Redis 方案，设计令牌刷新机制，编写单元测试覆盖 90% 场景
- 错误示例：写了一些代码

### R - 结果
你的行动带来了什么可量化的成果。回答"做到了什么效果？"
- 正确示例：系统响应时间从 500ms 降至 80ms，日均支撑 10 万次认证请求
- 错误示例：效果很好，得到了领导认可

## 常见错误
1. 只写"参与"而不写具体做了什么
2. 用"我们"代替"我"，无法区分个人贡献
3. 缺少数据支撑，全是形容词（"显著提升""大幅优化"）
4. 技术栈一笔带过，不体现技术深度
""",

    "技术简历高频关键词.md": """# 技术简历高频关键词与写法

## 后端开发关键词
- 高并发、分布式、微服务、RESTful API、gRPC
- MySQL 优化、索引优化、慢查询分析、分库分表
- Redis 缓存策略、缓存穿透/击穿/雪崩
- 消息队列（Kafka、RabbitMQ）、异步任务
- Docker、Kubernetes、CI/CD、DevOps

## AI/算法关键词
- 模型训练、特征工程、数据清洗、A/B 测试
- NLP、CV、推荐系统、大模型微调（LoRA、P-Tuning）
- RAG、向量数据库、Embedding、Prompt Engineering
- 模型部署（TensorRT、ONNX）、推理加速

## 产品经理关键词
- 用户调研、需求分析、PRD 撰写、竞品分析
- 数据分析（SQL、埋点、漏斗分析）、A/B 实验
- 敏捷开发、Scrum、迭代规划、跨部门协作
- 用户留存、DAU/MAU、LTV、CAC

## 写作原则
1. 每个关键词都要有具体经历支撑，不要堆砌
2. 优先写和目标岗位 JD 重合的关键词
3. 技术栈写清楚版本和规模（如 Python 3.11 / MySQL 8.0 / 10万+ QPS）
""",

    "简历优化常见误区.md": """# 简历优化十大常见误区

## 1. 罗列职责而非成果
错误：负责用户管理系统的开发和维护
正确：主导用户管理系统重构，接口响应速度提升 40%，支撑 50 万日活用户

## 2. 缺少量化数据
错误：大幅提升了系统性能
正确：通过索引优化和缓存策略，查询耗时从 2.3s 降至 120ms（提升 95%）

## 3. 技术栈模糊
错误：使用多种数据库技术
正确：MySQL 8.0（主库）+ Redis 7.0（缓存）+ Elasticsearch 8.x（搜索）

## 4. 动词选择无力
避免使用：参与、协助、帮忙、做了、负责日常
推荐使用：主导、设计、搭建、重构、优化、从零构建

## 5. 忽略业务价值
错误：写了 3 万行代码
正确：独立交付支付中台，支撑 3 条业务线接入，日均交易额 200 万

## 6. 团队成果写成个人成果
如果你在 5 人团队中做了一部分工作，请写清楚你的分工和独立产出

## 7. 一段话写完所有经历
每条经历控制在 1-2 句话，用项目符号分行，方便 HR 快速扫描

## 8. 不匹配目标岗位
投 AI 岗位就突出数据和算法经历，投后端岗位就突出架构和高并发经历

## 9. 使用第一人称
不要写"我"、"我们"，直接用动词开头

## 10. 忽略软技能
适当体现跨部门协作、技术分享、新人指导等软实力
""",
}


def load_sample_knowledge(progress_callback=None) -> int:
    """
    将预置的简历写作规范导入向量库。

    用于演示场景：用户无需自己准备文档，点击按钮即可体验 RAG 增强。
    已存在的文档（按文件名去重）会被跳过，不会重复导入。

    Args:
        progress_callback: 可选进度回调

    Returns:
        成功导入的文档片段总数
    """
    vectorstore = get_vector_store()
    if vectorstore is None:
        return 0

    # 获取已导入的源文件名，避免重复
    existing_names = set(st.session_state.get("kb_doc_names", []))
    total_added = 0
    filenames = list(SAMPLE_KNOWLEDGE.keys())

    for idx, (fname, content) in enumerate(SAMPLE_KNOWLEDGE.items()):
        if fname in existing_names:
            if progress_callback:
                progress_callback(idx + 1, len(filenames), f"⏭ {fname} 已存在，跳过")
            continue

        if progress_callback:
            progress_callback(idx, len(filenames), f"正在导入 {fname} ...")

        is_md = detect_is_markdown(content)
        splitter = get_text_splitter(is_markdown=is_md)
        chunks = splitter.create_documents(
            texts=[content],
            metadatas=[{"source": fname}],
        )

        # 计算 chunk 哈希
        batch = []
        for chunk in chunks:
            h = _compute_chunk_hash(chunk.page_content)
            chunk.metadata["chunk_hash"] = h
            batch.append(chunk)

        if batch:
            try:
                for i in range(0, len(batch), BATCH_LOAD_SIZE):
                    sub_batch = batch[i:i + BATCH_LOAD_SIZE]
                    vectorstore.add_documents(sub_batch)
                vectorstore.persist()

                if fname not in st.session_state.get("kb_doc_names", []):
                    st.session_state.setdefault("kb_doc_names", []).append(fname)

                total_added += len(batch)
                log_kb_operation("sample_import", doc_count=len(batch), doc_name=fname)

            except Exception as e:
                log_error("sample_kb", e, f"导入示例文档失败: {fname}")
                continue

    if progress_callback:
        progress_callback(len(filenames), len(filenames),
                          f"完成！共导入 {total_added} 条示例知识")

    log_kb_operation("sample_import_summary", doc_count=total_added)
    return total_added


# ══════════════════════════════════════════════════════════════
# 多路召回检索
# ══════════════════════════════════════════════════════════════

def _keyword_search(query: str, docs_meta: list[dict], k: int = KEYWORD_SEARCH_K) -> list[str]:
    """
    基于 TF-IDF 关键词的快速检索（BM25 简化版）。
    首次调用时懒加载 sklearn。

    Args:
        query: 查询文本
        docs_meta: 候选文档元数据列表，每个包含 "id" 和 "content"
        k: 返回数量

    Returns:
        匹配的文档 ID 列表
    """
    if not docs_meta:
        return []

    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    contents = [d["content"] for d in docs_meta]

    # 使用 TfidfVectorizer 进行关键词匹配
    try:
        vectorizer = TfidfVectorizer(
            analyzer="char",
            ngram_range=(2, 3),
            max_features=5000,
        )
        tfidf_matrix = vectorizer.fit_transform(contents)
        query_vec = vectorizer.transform([query])

        # 余弦相似度
        scores = cosine_similarity(query_vec, tfidf_matrix).flatten()
        top_indices = np.argsort(scores)[::-1][:k]

        return [docs_meta[i]["id"] for i in top_indices if scores[i] > 0]
    except Exception as e:
        log_error("keyword_search", e, "关键词检索失败，返回空")
        return []


def _deduplicate_docs(docs: list, by_content: bool = True) -> list:
    """
    对检索结果列表去重。

    Args:
        docs: Document 列表
        by_content: True=按内容去重，False=按 ID 去重

    Returns:
        去重后的 Document 列表（保持原始顺序）
    """
    seen = set()
    unique = []
    for doc in docs:
        key = doc.page_content if by_content else doc.metadata.get("chunk_hash", id(doc))
        if key not in seen:
            seen.add(key)
            unique.append(doc)
    return unique


def _simple_rerank(
    docs: list,
    query: str,
    top_k: int = RERANK_TOP_K,
) -> list:
    """
    简单重排序：使用 TF-IDF 向量对候选文档重新打分排序。
    首次调用时懒加载 sklearn。

    Args:
        docs: 候选 Document 列表
        query: 查询文本
        top_k: 最终返回数量

    Returns:
        重排序后的 Document 列表
    """
    if len(docs) <= top_k:
        return docs

    try:
        import numpy as np
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        contents = [doc.page_content for doc in docs]
        vectorizer = TfidfVectorizer(
            analyzer="char",
            ngram_range=(2, 3),
            max_features=3000,
        )
        tfidf_matrix = vectorizer.fit_transform(contents)
        query_vec = vectorizer.transform([query])

        scores = cosine_similarity(query_vec, tfidf_matrix).flatten()
        top_indices = np.argsort(scores)[::-1][:top_k]

        return [docs[i] for i in top_indices]
    except Exception as e:
        log_error("rerank", e, "重排序失败，返回前 top_k 条")
        return docs[:top_k]


def search_knowledge_base(
    query: str,
    k: int = TOP_K_RETRIEVAL,
    use_multi_recall: bool = True,
) -> str:
    """
    多路召回知识库检索。

    流程：
    1. 向量语义召回（Chroma similarity_search）
    2. 关键词召回（TF-IDF BM25）
    3. 合并去重
    4. 简单重排序
    5. 格式化返回

    Args:
        query: 查询文本
        k: 最终返回片段数
        use_multi_recall: 是否启用多路召回（False 则仅用向量检索）

    Returns:
        格式化后的参考资料文本
    """
    vectorstore = get_vector_store()
    if vectorstore is None:
        return ""

    try:
        # Step 1: 向量语义召回
        vector_k = VECTOR_SEARCH_K if use_multi_recall else k
        vector_docs = vectorstore.similarity_search(query, k=vector_k)

        if not vector_docs:
            return ""

        # Step 2: 关键词召回
        if use_multi_recall:
            # 获取全部候选文档（限制数量避免性能问题）
            try:
                all_results = vectorstore._collection.get(limit=2000)
                if all_results and all_results.get("ids"):
                    docs_meta = [
                        {"id": rid, "content": rdoc}
                        for rid, rdoc in zip(all_results["ids"], all_results["documents"])
                    ]
                    keyword_ids = _keyword_search(query, docs_meta, k=KEYWORD_SEARCH_K)

                    # 获取关键词命中的文档
                    if keyword_ids:
                        keyword_docs = [
                            doc for doc in vector_docs
                            if doc.metadata.get("chunk_hash") in keyword_ids
                        ]
                        # 合并
                        combined = vector_docs + keyword_docs
                    else:
                        combined = vector_docs
                else:
                    combined = vector_docs
            except Exception:
                combined = vector_docs
        else:
            combined = vector_docs

        # Step 3: 去重
        unique_docs = _deduplicate_docs(combined, by_content=True)

        # Step 4: 重排序
        final_docs = _simple_rerank(unique_docs, query, top_k=k)

        # Step 5: 格式化
        snippets = []
        for i, doc in enumerate(final_docs, 1):
            src = doc.metadata.get("source", "未知来源")
            snippets.append(f"【参考资料 {i}】（来源：{src}）\n{doc.page_content}")

        log_kb_operation(
            "search",
            doc_count=len(final_docs),
            detail=f"query_len={len(query)}, multi_recall={use_multi_recall}, "
                   f"vector={len(vector_docs)}, final={len(final_docs)}",
        )
        return "\n\n".join(snippets)

    except Exception as e:
        log_error("kb_search", e, f"检索异常: query={query[:50]}...")
        return ""


# ══════════════════════════════════════════════════════════════
# 知识库管理
# ══════════════════════════════════════════════════════════════

def get_kb_stats() -> dict:
    """获取知识库统计信息"""
    vectorstore = get_vector_store()
    if vectorstore is None:
        return {"collection_count": 0, "doc_names": []}
    try:
        collection = vectorstore._collection
        return {
            "collection_count": collection.count(),
            "doc_names": st.session_state.get("kb_doc_names", []),
        }
    except Exception as e:
        log_error("kb_stats", e, "获取统计失败")
        return {"collection_count": 0, "doc_names": []}


def delete_kb_by_doc_id(doc_id: str) -> bool:
    """
    按唯一文档 ID（chunk_hash）删除知识库中的文档。

    相比按文件名过滤，此方法精准删除，不会误删同名文档。

    Args:
        doc_id: 文档的 chunk_hash（唯一标识）

    Returns:
        True 表示删除成功
    """
    vectorstore = get_vector_store()
    if vectorstore is None:
        return False
    try:
        collection = vectorstore._collection
        # 按 metadata.chunk_hash 精确查找
        results = collection.get(where={"chunk_hash": doc_id})
        if results and results.get("ids"):
            collection.delete(ids=results["ids"])
            vectorstore.persist()
        log_kb_operation("delete_by_id", doc_name=doc_id[:16])
        return True
    except Exception as e:
        log_error("kb_delete_by_id", e, f"doc_id={doc_id[:16]}")
        return False


def delete_kb_by_filename(doc_name: str) -> int:
    """
    按文件名删除知识库中的所有关联文档（兼容旧接口）。

    Args:
        doc_name: 源文件名

    Returns:
        删除的 chunk 数量
    """
    vectorstore = get_vector_store()
    if vectorstore is None:
        return 0
    try:
        collection = vectorstore._collection
        results = collection.get(where={"source": doc_name})
        deleted = 0
        if results and results.get("ids"):
            deleted = len(results["ids"])
            collection.delete(ids=results["ids"])
            vectorstore.persist()
        # 更新 session_state
        names = st.session_state.get("kb_doc_names", [])
        if doc_name in names:
            names.remove(doc_name)
            st.session_state.kb_doc_names = names
        log_kb_operation("delete_by_filename", doc_count=deleted, doc_name=doc_name)
        return deleted
    except Exception as e:
        log_error("kb_delete_by_filename", e, f"doc_name={doc_name}")
        return 0


def clear_knowledge_base() -> int:
    """
    清空整个知识库。

    Returns:
        删除的文档数量
    """
    vectorstore = get_vector_store()
    if vectorstore is None:
        return 0
    try:
        collection = vectorstore._collection
        results = collection.get()
        deleted = 0
        if results and results.get("ids"):
            deleted = len(results["ids"])
            collection.delete(ids=results["ids"])
            vectorstore.persist()
        st.session_state.kb_doc_names = []
        log_kb_operation("clear", doc_count=deleted)
        return deleted
    except Exception as e:
        log_error("kb_clear", e, "清空失败")
        return 0
