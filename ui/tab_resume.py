"""
=============================================================================
简历优化助手 · Tab 1：简历优化（核心流程）
=============================================================================
包含输入区、RAG 增强开关、LLM 调用、结果渲染、历史记录。
=============================================================================
"""

import time
from datetime import datetime

import streamlit as st

from config import TOP_K_RETRIEVAL
from rag_core import search_knowledge_base, get_kb_stats
from llm_client import get_llm_client
from utils.evaluation import evaluate_optimization, render_evaluation_scores
from utils.logger import log_error, log_info


# ══════════════════════════════════════════════════════════════
# Prompt 构建
# ══════════════════════════════════════════════════════════════

def build_prompt(
    experience: str,
    target_role: str = "",
    target_company: str = "",
    kb_context: str = "",
) -> str:
    """构建简历优化 Prompt，支持 RAG 知识增强"""
    extra_context = ""
    if target_role:
        extra_context += f"\n- 目标岗位：{target_role}"
    if target_company:
        extra_context += f"\n- 目标公司：{target_company}"

    rag_section = ""
    if kb_context.strip():
        rag_section = f"""
## 行业规范参考（来自知识库）
以下是与目标岗位相关的行业规范及写作参考，请在优化时参考这些资料，使优化结果更贴近行业标准：

{kb_context}

"""

    return f"""你是一位资深 HR 兼简历优化专家，擅长用 STAR 法则润色技术类简历。

请对以下【项目经历】进行专业优化。{extra_context}
{rag_section}
## 项目经历原文
{experience}

## 输出要求

请严格按照以下四个板块输出（用 Markdown 表格下方的标题格式），每个板块一个标题，内容详尽、具体、可直接使用：

### 📋 原句
逐条列出用户输入的原句（方便对比），编号展示。

### 🔍 问题分析
逐条指出每条经历的不足，至少覆盖：
- 是否缺少具体数据/量化指标
- 动词是否足够有力
- 是否体现个人贡献（而非团队）
- STAR 结构是否完整
- 技术栈是否突出

### ✅ 优化版本
逐条给出优化后的完整句子，要求：
- 使用强有力的动作动词开头（主导、设计、优化、重构、搭建…）
- 包含可量化的成果（百分比、用户数、QPS、响应时间等，若原文无数据则给出合理估算并用 [建议核实] 标注）
- 突出技术关键词
- 符合 STAR 法则（情境-任务-行动-结果）
- 每条控制在 1-2 句话

### 💡 优化理由
逐条解释为什么这样优化，对应指出：
- 用了什么技巧（量化、动词增强、结构重组…）
- 解决了原文的什么问题
- 预计在 HR/面试官眼中的效果提升"""


# ══════════════════════════════════════════════════════════════
# 结果解析 & 渲染
# ══════════════════════════════════════════════════════════════

def parse_result(text: str) -> dict:
    """将返回文本按四个标题拆分为 dict"""
    sections = {
        "original": "",
        "issue": "",
        "optimized": "",
        "reason": "",
    }
    current_key = None
    markers = {
        "### 📋 原句": "original",
        "### 🔍 问题分析": "issue",
        "### ✅ 优化版本": "optimized",
        "### 💡 优化理由": "reason",
    }

    for line in text.split("\n"):
        matched = False
        for marker, key in markers.items():
            if line.strip().startswith(marker):
                current_key = key
                matched = True
                break
        if matched:
            continue
        if current_key:
            sections[current_key] += line + "\n"

    return {k: v.strip() for k, v in sections.items()}


def render_result(parsed: dict):
    """渲染四栏优化结果（两列布局）"""
    config = [
        ("📋 原句", "badge-original", parsed["original"]),
        ("🔍 问题分析", "badge-issue", parsed["issue"]),
        ("✅ 优化版本", "badge-optimized", parsed["optimized"]),
        ("💡 优化理由", "badge-reason", parsed["reason"]),
    ]

    cols = st.columns(2)
    for i, (title, badge_cls, content) in enumerate(config):
        target_col = cols[0] if i in (0, 2) else cols[1]
        with target_col:
            st.markdown(
                f"""
                <div class="section-card">
                    <span class="section-badge {badge_cls}">{title}</span>
                    <div class="section-content">{content.replace(chr(10), '<br>')}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # 一键下载优化版本
    with cols[0]:
        if parsed["optimized"]:
            st.download_button(
                label="📥 下载优化版本（Markdown）",
                data=parsed["optimized"],
                file_name="optimized_resume.md",
                mime="text/markdown",
                use_container_width=True,
            )


# ══════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════

def render():
    """渲染「简历优化」Tab 的全部 UI"""

    # ── 示例文本 ──
    EXAMPLE_TEXT = """用 Python + Django 写了一个电商网站的后台管理系统。
负责用户模块的CRUD功能开发。
参与了数据库设计和优化，提升了系统性能。
使用Redis做缓存，减少了数据库的压力。"""

    # ── 处理"填入示例"按钮的逻辑（必须在 text_area 之前执行）──
    # Streamlit 不允许在 widget 实例化后修改其 session_state key，
    # 所以通过 _fill_example 标记位，在 widget 创建之前完成赋值。
    if st.session_state.get("_fill_example"):
        st.session_state.main_experience_input = EXAMPLE_TEXT
        st.session_state._fill_example = False

    # ── 输入区 ──
    st.markdown('<div class="input-card">', unsafe_allow_html=True)
    st.markdown("### ✍️ 输入项目经历")
    st.caption("把简历中需要优化的项目经历粘贴在下方。每行一条，或整段粘贴均可。")

    col_input, col_preview = st.columns([3, 1])

    with col_input:
        experience = st.text_area(
            "项目经历",
            placeholder="把简历中的项目经历贴在这里...\n\n示例：\n" + EXAMPLE_TEXT,
            height=300,
            label_visibility="collapsed",
            key="main_experience_input",
        )

    with col_preview:
        st.markdown("**💡 写作技巧**")
        st.caption("""
        - 用**动作动词**开头（主导、设计、优化）
        - 加上**量化数据**（提升了 30%）
        - 突出**个人贡献**（而非「参与」）
        - 遵循 **STAR 法则**
        """)
        st.divider()
        st.markdown("**📝 填入示例**")
        if st.button("📝 填入示例", use_container_width=True, key="btn_example_main"):
            # 设置标记位 → rerun → 在 text_area 渲染前完成赋值（见上方逻辑）
            st.session_state._fill_example = True
            st.rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    # ── RAG 增强开关 ──
    use_rag = False
    kb_stats = get_kb_stats()
    if kb_stats["collection_count"] > 0:
        use_rag = st.checkbox(
            f"🔍 启用 RAG 知识增强（当前知识库：{kb_stats['collection_count']} 条向量）",
            value=True,
            help="将自动从知识库检索相关行业规范，注入优化 Prompt",
        )

    # ── 操作按钮（带防重复点击锁）──
    col_btn1, col_btn2, col_btn3 = st.columns([2, 1, 1])
    with col_btn1:
        # 按钮在 LLM 请求期间禁用
        btn_disabled = st.session_state.get("optimizing", False)
        optimize_clicked = st.button(
            "🚀 开始优化",
            type="primary",
            use_container_width=True,
            key="btn_optimize",
            disabled=btn_disabled,
        )

    # ── 获取必要数据 ──
    target_role = st.session_state.get("_target_role", "")
    target_company = st.session_state.get("_target_company", "")

    # ── 执行优化 ──
    if optimize_clicked:
        if not experience.strip():
            st.error("⚠️ 请先输入项目经历再优化。")
        else:
            try:
                llm_client = get_llm_client()
                st.session_state.optimizing = True
            except ValueError as e:
                st.error(f"⚠️ {e}")

    if st.session_state.get("optimizing"):
        with st.status("🤖 AI 正在优化你的简历…", expanded=True) as status:
            try:
                llm_client = get_llm_client()

                # Step 1: RAG 检索
                kb_context = ""
                if use_rag:
                    st.write("🔍 检索知识库…")
                    query = experience + " " + (target_role or "") + " " + (target_company or "")
                    kb_context = search_knowledge_base(query, k=TOP_K_RETRIEVAL)
                    if kb_context:
                        st.write("✅ 已匹配知识库参考资料")

                # Step 2: 调用 LLM 优化
                st.write("📤 发送到 LLM …")
                prompt = build_prompt(
                    experience, target_role or "", target_company or "", kb_context
                )
                raw = llm_client.generate(prompt, max_tokens=4096)
                parsed = parse_result(raw)

                # Step 3: 效果评估
                st.write("📊 生成质量评估…")
                eval_scores = evaluate_optimization(
                    experience,
                    parsed.get("optimized", ""),
                    target_role or "",
                    llm_client,
                )

                # 保存到 history
                record = {
                    "experience": experience,
                    "role": target_role,
                    "company": target_company,
                    "parsed": parsed,
                    "eval_scores": eval_scores,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "use_rag": use_rag,
                }
                st.session_state.history.append(record)
                st.session_state.result = parsed
                st.session_state.eval_scores = eval_scores

                status.update(label="✅ 优化完成！", state="complete")
                log_info("简历优化完成")

            except Exception as e:
                status.update(label=f"❌ 出错: {e}", state="error")
                st.session_state.result = None
                st.session_state.eval_scores = None
                log_error("tab_resume", e, "优化流程失败")
            finally:
                st.session_state.optimizing = False
                st.rerun()

    # ── 展示优化结果 ──
    if st.session_state.get("result"):
        st.divider()
        st.markdown("### 🎯 优化结果")
        render_result(st.session_state.result)

        # ── 展示评分 ──
        if st.session_state.get("eval_scores"):
            render_evaluation_scores(st.session_state.eval_scores)

    # ── 历史记录 ──
    history = st.session_state.get("history", [])
    if history:
        with st.expander(
            f"📜 优化历史（{len(history)} 条）", expanded=False
        ):
            for i, h in enumerate(reversed(history)):
                idx = len(history) - i
                preview = h["experience"].replace("\n", " ")[:80] + "…"
                role_tag = f" → {h['role']}" if h.get("role") else ""
                rag_tag = " [RAG]" if h.get("use_rag") else ""
                scores = h.get("eval_scores")
                score_tag = ""
                if scores:
                    avg = (float(scores.get("completeness", 0))
                           + float(scores.get("job_match", 0))
                           + float(scores.get("format_quality", 0))) / 3
                    score_tag = f" ⭐{avg:.1f}"
                st.markdown(f"**{idx}.** {preview} `{role_tag}`{rag_tag}{score_tag}")
