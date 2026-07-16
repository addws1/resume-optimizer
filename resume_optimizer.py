"""
=============================================================================
简历优化助手 · Resume Optimizer
=============================================================================
AI 驱动的项目经历优化工具，支持：
  - DeepSeek / Ollama / 通义千问 多模型切换
  - 本地 RAG 知识库增强（TF-IDF / BGE 双方案）
  - PRD 需求文档一键生成
  - 模型效果量化评估（打分 + 折线图 + CSV）
  - 标准化用户调研（问卷 + NPS + 痛点报告）
  - PDF / DOCX 简历批量优化

架构：主文件仅做页面路由与全局初始化，业务逻辑拆分至各模块。
=============================================================================
"""

import os
import sys

# 确保项目根目录在 Python 路径中
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

# ── 项目模块 ──────────────────────────────────
from config import PAGE_TITLE, PAGE_ICON, PAGE_LAYOUT, DEEPSEEK_API_KEY
from rag_core import (
    get_kb_stats, add_documents_to_kb,
    clear_knowledge_base, delete_kb_by_filename,
    load_sample_knowledge,
)
from llm_client import reset_llm_client
from utils.logger import get_logger, log_info
from utils.stats import log_visit, get_optimization_stats
from ui import tab_resume, tab_prd, tab_eval, tab_survey, tab_stats

# ══════════════════════════════════════════════════════════════
# 初始化日志
# ══════════════════════════════════════════════════════════════
get_logger("resume_optimizer")  # 初始化日志器（创建日志文件）
log_info("===== 简历优化助手启动 =====")

# ══════════════════════════════════════════════════════════════
# 页面配置
# ══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout=PAGE_LAYOUT,
    initial_sidebar_state="expanded",
)

# ══════════════════════════════════════════════════════════════
# 暗色主题 CSS
# ══════════════════════════════════════════════════════════════
st.markdown(
    """
<style>
    /* 全局 */
    .stApp { background: #0d1117; }
    header[data-testid="stHeader"] { background: transparent; }

    /* 标题区 */
    .main-title {
        font-size: 2.4rem; font-weight: 800; text-align: center;
        background: linear-gradient(135deg, #58a6ff, #3fb950);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        margin-bottom: 0;
    }
    .sub-title {
        text-align: center; color: #8b949e; font-size: 0.95rem;
        margin-bottom: 2rem;
    }

    /* 输入卡片 */
    .input-card {
        background: #161b22; border: 1px solid #30363d;
        border-radius: 12px; padding: 24px; margin-bottom: 20px;
    }

    /* 主按钮 */
    div.stButton > button {
        width: 100%; background: linear-gradient(135deg, #238636, #2ea043);
        color: #fff; border: none; border-radius: 10px; padding: 12px;
        font-size: 1.1rem; font-weight: 700; letter-spacing: 1px;
        transition: all 0.2s;
    }
    div.stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 24px rgba(35, 134, 54, 0.35);
    }
    div.stButton > button:disabled {
        background: #30363d !important; color: #6e7681 !important;
        transform: none !important; box-shadow: none !important;
    }

    /* 次要按钮 */
    .sec-btn > button {
        background: #21262d !important;
        border: 1px solid #30363d !important;
        color: #c9d1d9 !important;
    }

    /* 导出按钮 */
    .export-btn > button {
        background: linear-gradient(135deg, #1f6feb, #58a6ff) !important;
    }

    /* 结果卡片 */
    .section-card {
        background: #161b22; border: 1px solid #30363d;
        border-radius: 10px; padding: 20px; margin-bottom: 16px;
    }
    .section-badge {
        display: inline-block; padding: 4px 14px; border-radius: 20px;
        font-size: 0.85rem; font-weight: 700; margin-bottom: 12px;
    }
    .badge-original { background: #1f2a37; color: #79c0ff; border: 1px solid #1f6feb; }
    .badge-issue    { background: #2d1f1f; color: #ff7b72; border: 1px solid #da3633; }
    .badge-optimized{ background: #1a2e1f; color: #7ee787; border: 1px solid #238636; }
    .badge-reason   { background: #2a2618; color: #e3b341; border: 1px solid #9e6a03; }
    .badge-score    { background: #1a1e2f; color: #a371f7; border: 1px solid #8250df; }
    .badge-prd      { background: #1f2a37; color: #79c0ff; border: 1px solid #1f6feb; }

    .section-content {
        color: #c9d1d9; line-height: 1.8; font-size: 0.95rem;
    }

    /* 评分卡片 */
    .score-card {
        background: #161b22; border: 1px solid #30363d;
        border-radius: 10px; padding: 16px; margin-bottom: 12px;
        text-align: center;
    }
    .score-value {
        font-size: 2rem; font-weight: 800;
        background: linear-gradient(135deg, #a371f7, #58a6ff);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .score-label {
        color: #8b949e; font-size: 0.8rem; margin-top: 4px;
    }

    /* 知识库卡片 */
    .kb-card {
        background: #161b22; border: 1px solid #30363d;
        border-radius: 8px; padding: 12px; margin-bottom: 8px;
    }

    /* 分割线 */
    .section-divider {
        border: none; border-top: 1px solid #30363d;
        margin: 20px 0;
    }
</style>
""",
    unsafe_allow_html=True,
)

# ══════════════════════════════════════════════════════════════
# 标题
# ══════════════════════════════════════════════════════════════
st.markdown('<div class="main-title">📄 简历优化助手</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">AI 驱动的项目经历优化 · RAG 知识库增强 · 多模型切换 · 效果量化评估</div>',
    unsafe_allow_html=True,
)

# ══════════════════════════════════════════════════════════════
# 初始化 session_state
# ══════════════════════════════════════════════════════════════
_defaults = {
    "result": None,
    "optimizing": False,
    "history": [],
    # RAG
    "kb_ready": False,
    "kb_doc_names": [],
    "kb_error": None,
    # 评估
    "eval_scores": None,
    # 调研
    "survey_submitted": False,
    "survey_report": None,
    # PRD
    "prd_content": None,
    "prd_generated": False,
    # UI 状态
    "_fill_example": False,
    "_prd_generating": False,
    "_target_role": "",
    "_target_company": "",
}
for key, default in _defaults.items():
    if key not in st.session_state:
        st.session_state[key] = default

# ── 记录本次访问（持久化统计）──
log_visit()

# ══════════════════════════════════════════════════════════════
# 侧边栏：设置 + 知识库管理
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### ⚙️ 设置")

    # ── LLM 提供商选择 ──
    st.markdown("**🤖 LLM 后端**")
    from config import LLM_PROVIDER
    provider_options = ["deepseek", "ollama", "qwen"]
    current_provider_idx = provider_options.index(LLM_PROVIDER) if LLM_PROVIDER in provider_options else 0
    selected_provider = st.selectbox(
        "选择模型后端",
        provider_options,
        index=current_provider_idx,
        help="DeepSeek=云端API | Ollama=本地部署 | Qwen=阿里云",
        key="sidebar_llm_provider",
    )
    # 如果用户切换了后端，重置客户端缓存
    # 注意：不能与 config.LLM_PROVIDER 比较（import 时定死，永不变化，
    # 会导致无限 rerun）；也无需手动 st.rerun()——selectbox 变化本身就会 rerun
    if st.session_state.get("_last_llm_provider") != selected_provider:
        st.session_state["_last_llm_provider"] = selected_provider
        reset_llm_client()

    # ── API Key 状态 ──
    st.markdown("**🔑 API Key 状态**")
    if selected_provider == "deepseek":
        api_key = DEEPSEEK_API_KEY
        if api_key:
            masked = api_key[:6] + "****" + api_key[-4:] if len(api_key) > 10 else "****"
            st.success(f"✓ DeepSeek: `{masked}`")
        else:
            st.error("✗ 未设置 DEEPSEEK_API_KEY")
            st.caption("在项目 .env 文件中设置：")
            st.code('DEEPSEEK_API_KEY="sk-xxx"', language="bash")
    elif selected_provider == "ollama":
        st.info("ℹ️ 使用本地 Ollama，无需 API Key")
        st.caption("确保 Ollama 服务已启动：`ollama serve`")
    elif selected_provider == "qwen":
        from config import QWEN_API_KEY
        if QWEN_API_KEY:
            st.success("✓ 通义千问 API Key 已配置")
        else:
            st.warning("⚠️ 未设置 QWEN_API_KEY")

    # ── 免费额度 / BYOK ──
    from utils.quota import (
        get_user_id, get_remaining, get_byok_key, is_quota_exempt,
    )
    from config import FREE_QUOTA_PER_FEATURE

    if selected_provider != "ollama":
        st.text_input(
            "🔐 使用自己的 API Key（可选）",
            type="password",
            key=f"byok_{selected_provider}",
            help="填写后不消耗免费额度、不限次数；仅保存在当前会话内存中，"
                 "刷新页面即失效，永不写入服务器磁盘或日志。",
        )

    if is_quota_exempt():
        if selected_provider != "ollama" and get_byok_key(selected_provider):
            st.success("✓ 已使用您自己的 Key，不限次数")
    else:
        _uid = get_user_id()
        _remain_resume = get_remaining(_uid, "resume")
        _remain_prd = get_remaining(_uid, "prd")
        st.caption(
            f"🎫 免费额度 — 简历优化：剩 {_remain_resume}/{FREE_QUOTA_PER_FEATURE} 次 · "
            f"PRD 生成：剩 {_remain_prd}/{FREE_QUOTA_PER_FEATURE} 次"
        )
        if _remain_resume == 0 or _remain_prd == 0:
            st.warning("部分功能免费额度已用完，填入自己的 API Key 可继续使用")

    st.divider()

    # ── Embedding 后端选择 ──
    st.markdown("**🧠 Embedding 后端**")
    from config import EMBEDDING_BACKEND
    emb_options = ["tfidf", "bge"]
    current_emb_idx = emb_options.index(EMBEDDING_BACKEND) if EMBEDDING_BACKEND in emb_options else 0
    selected_emb = st.selectbox(
        "向量模型",
        emb_options,
        index=current_emb_idx,
        help="TF-IDF=纯离线 | BGE=中文语义（需首次下载约100MB）",
        key="sidebar_emb_backend",
    )
    # 如果用户切换了向量后端，清除向量库缓存
    # 注意：不能与 config.EMBEDDING_BACKEND 比较（import 时定死，会无限 rerun）；
    # 会话级选择由 rag_core 读取 session_state["sidebar_emb_backend"] 生效
    # BGE 模型加载较慢，选中时先预热并给出明确提示。
    # 注意：get_embeddings / 向量库缓存均按后端名分键（tfidf/bge 实例可共存），
    # 切换无需清缓存——模型加载过一次后来回切换即时生效，页面不再长时间变暗
    if selected_emb == "bge":
        from rag_core import is_bge_model_cached, get_embeddings
        if not is_bge_model_cached():
            st.info("⏳ 首次使用 BGE 需下载模型（约 100MB），请耐心等待…")
        with st.spinner("正在加载 BGE 语义模型…"):
            get_embeddings("bge")  # 命中缓存时瞬时返回，spinner 不可见

    st.divider()

    # ── 可选信息（同步到 session_state）──
    st.markdown("**🎯 可选信息** （让优化更有针对性）")
    target_role = st.text_input(
        "🎯 目标岗位", placeholder="例如：Python 后端开发",
        key="sidebar_target_role",
        value=st.session_state.get("_target_role", ""),
    )
    target_company = st.text_input(
        "🏢 目标公司", placeholder="例如：字节跳动",
        key="sidebar_target_company",
        value=st.session_state.get("_target_company", ""),
    )
    st.session_state._target_role = target_role
    st.session_state._target_company = target_company

    st.divider()

    # ── 知识库管理 ──
    st.markdown("### 📚 知识库管理")
    st.caption("上传 HR 规范 / JD 模板 / 写作话术（md/txt/pdf/docx）")

    # 知识库状态
    stats = get_kb_stats()
    if stats["collection_count"] > 0:
        st.success(f"✓ {stats['collection_count']} 条知识向量已就绪")
        if stats.get("doc_names"):
            doc_list = stats["doc_names"]
            display_docs = doc_list[:5]
            suffix = "…" if len(doc_list) > 5 else ""
            st.caption(f"来源文件：{', '.join(display_docs)}{suffix}")
    else:
        st.info("ℹ️ 知识库为空，上传文档激活 RAG 增强")

        # ── 一键加载示例知识库（演示 / 首次使用）──
        if st.button("📥 加载示例知识库", use_container_width=True,
                     key="btn_load_sample_kb",
                     help="导入 STAR 法则、技术关键词、常见误区等写作指南，立即体验 RAG 增强效果"):
            with st.spinner("正在导入示例知识库…"):
                progress_bar = st.progress(0)
                progress_text = st.empty()

                def _sample_progress(current, total, msg):
                    progress_bar.progress(min(current / total, 1.0))
                    progress_text.caption(msg)

                added = load_sample_knowledge(progress_callback=_sample_progress)

            if added > 0:
                st.success(f"✅ 已导入 {added} 条示例知识（3 篇写作指南）")
                st.rerun()
            else:
                st.warning("⚠️ 导入失败，请检查向量库状态。")

    # 上传文档（支持更多格式）
    uploaded_files = st.file_uploader(
        "上传知识文档",
        type=["md", "txt", "pdf", "docx"],
        accept_multiple_files=True,
        label_visibility="collapsed",
        key="kb_uploader",
    )

    if uploaded_files:
        if st.button("📤 导入知识库", use_container_width=True, key="btn_import_kb"):
            with st.spinner("正在向量化文档…"):
                # 进度条占位
                progress_bar = st.progress(0)
                progress_text = st.empty()

                def update_progress(current, total, msg):
                    pct = min(current / max(total, 1), 1.0)
                    progress_bar.progress(pct)
                    progress_text.caption(msg)

                count = add_documents_to_kb(uploaded_files, progress_callback=update_progress)

            if count > 0:
                st.success(f"✅ 成功导入 {count} 个文件到知识库")
                st.rerun()
            else:
                st.warning("⚠️ 未能导入任何文件，请检查文件格式。")

    # 知识库操作按钮
    col_kb1, col_kb2 = st.columns(2)
    with col_kb1:
        if st.button("🗑️ 清空知识库", use_container_width=True, key="btn_clear_kb"):
            deleted = clear_knowledge_base()
            st.success(f"✅ 知识库已清空（删除 {deleted} 条向量）")
            st.rerun()
    with col_kb2:
        if st.button("📋 刷新状态", use_container_width=True, key="btn_refresh_kb"):
            st.rerun()

    # 按文件名删除（兼容旧接口）
    kb_doc_names = st.session_state.get("kb_doc_names", [])
    if kb_doc_names:
        doc_to_del = st.selectbox(
            "选择要删除的文档",
            options=[""] + list(kb_doc_names),
            key="kb_del_select",
        )
        if doc_to_del and st.button("❌ 删除选中文档", use_container_width=True, key="btn_del_doc"):
            deleted = delete_kb_by_filename(doc_to_del)
            if deleted > 0:
                st.success(f"✅ 已删除 {doc_to_del}（{deleted} 条向量）")
                st.rerun()
            else:
                st.warning(f"⚠️ 未找到文档 {doc_to_del}")

    st.divider()

    # 优化记录（session + 持久化双数据源）
    opt_stats = get_optimization_stats()
    total_opts = max(len(st.session_state.history), opt_stats.get("total_count", 0))
    if total_opts > 0:
        st.markdown(f"**📊 已优化：{total_opts} 条**")
        if opt_stats.get("avg_score_all"):
            st.caption(f"平均评分：⭐{opt_stats['avg_score_all']}/5.0")

    if st.button("🔄 清空历史记录", use_container_width=True):
        st.session_state.history = []
        st.session_state.result = None
        st.session_state.eval_scores = None
        st.rerun()


# ══════════════════════════════════════════════════════════════
# 主界面 - 使用 Tabs 组织功能模块
# ══════════════════════════════════════════════════════════════

tab_main, tab_prd_ui, tab_eval_ui, tab_survey_ui, tab_stats_ui = st.tabs([
    "📄 简历优化",
    "📋 PRD 导出",
    "📊 效果评估",
    "📝 用户调研",
    "📈 数据看板",
])

# Tab 1：简历优化
with tab_main:
    tab_resume.render()

# Tab 2：PRD 导出
with tab_prd_ui:
    tab_prd.render()

# Tab 3：效果评估
with tab_eval_ui:
    tab_eval.render()

# Tab 4：用户调研
with tab_survey_ui:
    tab_survey.render()

# Tab 5：数据看板
with tab_stats_ui:
    tab_stats.render()


# ══════════════════════════════════════════════════════════════
# 底部
# ══════════════════════════════════════════════════════════════
st.divider()
st.caption(
    "💡 提示：优化结果仅供参考，请根据实际情况调整数据。| "
    "在 .env 文件中配置 API Key | "
    "RAG 知识库支持 md/txt/pdf/docx | "
    "所有数据本地存储，不涉及云端上传 | "
    f"日志目录: data/logs/"
)
