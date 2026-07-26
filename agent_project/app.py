"""
=============================================================================
简历优化 Agent · Streamlit 主页面
=============================================================================
独立应用，不依赖旧项目任何文件。

启动：streamlit run app.py
=============================================================================
"""

import os
import tempfile
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

# ⚠️ 必须在 import config 之前加载 .env，否则 config 读不到环境变量
_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)

from config import MAX_FILE_SIZE_MB, ALLOWED_EXTENSIONS, FREE_QUOTA_PER_DAY
from parser import parse_resume_file, ParseError, read_text_with_encoding_fallback
from section_parser import parse_sections as robust_parse_sections
from docx_gen import generate_docx, generate_clean_resume_docx
from agent import ResumeAgent, AgentError
from quota import (
    get_user_id, get_remaining, get_byok_key, is_quota_exempt,
    check_quota, consume_quota,
)

# ── 页面配置 ──
st.set_page_config(
    page_title="简历优化 Agent",
    page_icon="🤖",
    layout="wide",
)

# ── 自定义样式 ──
st.markdown("""
<style>
    .main-header { text-align: center; padding: 1rem 0 2rem 0; }
    .main-header h1 { font-size: 2.2rem; margin-bottom: 0.3rem; }
    .main-header p { color: #8b949e; font-size: 1rem; }
    .section-card {
        background: #f6f8fa;
        border-radius: 8px;
        padding: 1rem;
        margin-bottom: 0.8rem;
        border-left: 4px solid #1a56db;
    }
    .section-card h4 { margin-top: 0; color: #1a56db; }
    .review-box {
        background: #fff8e1;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
        border-left: 4px solid #f0a030;
    }
    .assessment-box {
        background: #e8f5e9;
        border-radius: 8px;
        padding: 1rem;
        margin: 1rem 0;
        border-left: 4px solid #2e7d32;
    }
    .error-box {
        background: #ffebee;
        border-radius: 8px;
        padding: 1rem;
        border-left: 4px solid #d32f2f;
    }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# 工具函数
# ══════════════════════════════════════════════════════════════

def parse_result_sections(text: str) -> dict:
    """将 LLM 输出按板块标题拆分为四个板块（健壮版，支持多种格式变体）"""
    return robust_parse_sections(text)


def render_results(result: dict):
    """渲染四栏结果 + 自审痕迹 + 自评总结 + 评分卡 + 下载"""
    parsed = parse_result_sections(result["round2"])
    review = result.get("review", "")
    assessment = result.get("assessment", "")
    round1 = result.get("round1", "")
    scores = result.get("scores", {})
    score_raw = result.get("score_raw", "")

    # ── 评分卡（放在最前面，用户先看分数再深入细节）──
    render_score_card(scores, score_raw)

    # ── LLM 调用指标 ──
    metrics = result.get("metrics", {})
    if metrics:
        render_metrics_bar(metrics)

    # ── 原始简历（可折叠）──
    original_text = st.session_state.get("_saved_resume_text", "")
    if original_text:
        with st.expander("📄 查看原始简历", expanded=False):
            st.text_area(
                "原始简历内容",
                value=original_text,
                height=200,
                disabled=True,
            )

    st.markdown("### 🎯 优化结果")

    items = [
        ("📋 原句", parsed.get("original", "")),
        ("🔍 问题分析", parsed.get("issue", "")),
        ("✅ 优化版本", parsed.get("optimized", "")),
        ("💡 优化理由", parsed.get("reason", "")),
    ]

    cols = st.columns(2)
    for i, (title, content) in enumerate(items):
        with cols[i % 2]:
            st.markdown(f"""
            <div class="section-card">
                <h4>{title}</h4>
                <div style="white-space: pre-wrap; font-size: 0.9rem;">{content or '（无内容）'}</div>
            </div>
            """, unsafe_allow_html=True)

    # ── 最终简历（合成后的干净版本）──
    final_resume = result.get("final_resume", "")
    clean_docx_path = st.session_state.get("clean_docx_path", "")
    if final_resume:
        st.divider()
        st.markdown("### 📄 最终简历（可直接投递）")
        st.caption("Agent 将优化后的条目按模板结构合成为完整简历，可直接复制使用或下载。")
        with st.expander("查看最终简历", expanded=True):
            st.markdown(final_resume)
            col_md, col_docx = st.columns(2)
            with col_md:
                st.download_button(
                    label="📥 下载简历（Markdown）",
                    data=final_resume,
                    file_name="简历_优化版.md",
                    mime="text/markdown",
                    use_container_width=True,
                )
            with col_docx:
                if clean_docx_path and os.path.exists(clean_docx_path):
                    with open(clean_docx_path, "rb") as f:
                        st.download_button(
                            label="📥 下载简历（DOCX）",
                            data=f,
                            file_name=os.path.basename(clean_docx_path),
                            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True,
                            type="primary",
                        )

    # ── Agent 自审痕迹 ──
    if review:
        st.markdown("### 🔍 Agent 自审过程")
        with st.expander("查看 Agent 自审详情", expanded=False):
            st.markdown(f"""
            <div class="review-box">
                <h4>🔍 Agent 自审发现</h4>
                <div style="white-space: pre-wrap; font-size: 0.9rem;">{review}</div>
            </div>
            """, unsafe_allow_html=True)

    # ── Agent 自评总结 ──
    if assessment and "失败" not in assessment:
        st.markdown(f"""
        <div class="assessment-box">
            <h4>🤖 Agent 自评总结</h4>
            <div style="font-size: 0.95rem;">{assessment}</div>
        </div>
        """, unsafe_allow_html=True)

    # ── 第 1 轮优化对照（可折叠）──
    if round1:
        with st.expander("📝 查看第 1 轮优化（Agent 改进前）", expanded=False):
            st.caption("以下是 Agent 自审前的初版优化，第 2 轮在此基础上根据自审意见改进。")
            st.markdown(round1)

    # ── DOCX 下载 ──
    docx_path = st.session_state.get("docx_path", "")
    if docx_path and os.path.exists(docx_path):
        with open(docx_path, "rb") as f:
            st.download_button(
                label="📥 下载优化结果（DOCX）",
                data=f,
                file_name=os.path.basename(docx_path),
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
                type="primary",
            )


def render_step_status(status_widget, step: str, status: str):
    """根据 Agent 进度回调更新 st.status 内的文字"""
    labels = {
        "optimize": "✍️ 正在优化（第 1 轮）…",
        "review": "🔍 Agent 正在自审…",
        "improve": "🔧 正在改进（第 2 轮）…",
        "assess": "📊 正在评分 + 自评总结…",
        "synthesize": "📄 正在合成最终简历…",
    }
    icon = {"running": "⏳", "done": "✅", "error": "❌"}.get(status, "⏳")
    status_widget.write(f"{icon} {labels.get(step, step)}")


def render_metrics_bar(metrics: dict):
    """渲染 LLM 调用指标概览条（轻量，不抢眼）"""
    calls = metrics.get("calls", 0)
    total_tokens = metrics.get("total_tokens", 0)
    elapsed = metrics.get("elapsed_seconds", 0)
    cost_rmb = metrics.get("cost_rmb", 0)

    # 格式化
    if total_tokens >= 1000:
        token_str = f"{total_tokens / 1000:.1f}K"
    else:
        token_str = str(total_tokens)

    st.markdown(f"""
    <div style="display:flex; gap:1.5rem; align-items:center; padding:0.5rem 1rem;
                border-radius:8px; background:#f0f4ff; border:1px solid #d0d8f0;
                font-size:0.8rem; color:#555; margin-bottom:1rem;">
        <span>🔢 <b>{calls}</b> 次 LLM 调用</span>
        <span>🪙 <b>{token_str}</b> tokens</span>
        <span>⏱ <b>{elapsed:.1f}s</b></span>
        <span>💰 ¥<b>{cost_rmb:.4f}</b></span>
    </div>
    """, unsafe_allow_html=True)


def _score_color(score: int) -> str:
    """根据分数返回颜色（绿/橙/红）"""
    if score >= 80:
        return "#2e7d32"
    elif score >= 60:
        return "#e65100"
    else:
        return "#c62828"


def _parse_score_sections(raw_text: str) -> dict:
    """从评分原始输出中提取评价文字"""
    result = {"evaluation": ""}
    if not raw_text:
        return result

    import re as _re
    # 匹配 💬 优化总结 或 💬 总体评价
    m = _re.search(r'###\s*💬\s*(?:优化总结|总体评价)\s*\n(.*?)(?=###|\Z)', raw_text, _re.DOTALL)
    if m:
        result["evaluation"] = m.group(1).strip()

    return result


def render_score_card(scores: dict, score_raw: str = ""):
    """渲染多维度评分卡片"""
    if not scores:
        return

    # 提取原始分、优化分、提升值
    before_score = scores.pop("原始综合分", None)
    after_score = scores.pop("优化综合分", None)
    delta_score = scores.pop("△提升", None)
    # 如果没提取到"提升"键，尝试计算
    if delta_score is None and before_score is not None and after_score is not None:
        delta_score = after_score - before_score

    # 分离综合评分和其他维度
    overall_keys = ["综合评分", "总分"]
    overall = None
    for k in overall_keys:
        if k in scores:
            overall = scores.pop(k)
            break

    # 维度显示顺序和简称
    dim_order = [
        ("STAR完整度", "STAR 完整度"),
        ("量化率", "量化率"),
        ("动词力度", "动词力度"),
        ("技术关键词密度", "技术关键词"),
        ("个人贡献清晰度", "个人贡献"),
        ("表达简洁度", "表达简洁度"),
        ("JD匹配度", "JD 匹配度"),
    ]

    display_dims = []
    for key, label in dim_order:
        if key in scores:
            display_dims.append((label, scores[key]))

    if not display_dims and overall is None and before_score is None:
        return

    st.markdown("### 📊 简历质量评分")

    # ── 优化前后对比条 ──
    if before_score is not None and after_score is not None:
        before_color = _score_color(before_score)
        after_color = _score_color(after_score)
        delta_str = f"+{delta_score}" if delta_score and delta_score > 0 else str(delta_score or "")
        st.markdown(f"""
        <div style="display:flex; align-items:center; gap:0.8rem; margin-bottom:1rem;
                    padding:0.8rem 1.2rem; border-radius:10px; background:#f6f8fa;">
            <div style="text-align:center; flex-shrink:0;">
                <div style="font-size:0.7rem; color:#8b949e;">优化前</div>
                <div style="font-size:1.4rem; font-weight:700; color:{before_color};">{before_score}</div>
            </div>
            <div style="flex:1; height:6px; background:linear-gradient(90deg, {before_color}40, {after_color}40);
                        border-radius:3px; position:relative;">
                <div style="position:absolute; left:0; top:-8px; font-size:1.2rem;">→</div>
            </div>
            <div style="text-align:center; flex-shrink:0;">
                <div style="font-size:0.7rem; color:#8b949e;">优化后</div>
                <div style="font-size:1.4rem; font-weight:700; color:{after_color};">{after_score}</div>
            </div>
            <div style="text-align:center; flex-shrink:0; padding:0.3rem 0.6rem; border-radius:6px;
                        background:{after_color}15; border:1px solid {after_color}35;">
                <div style="font-size:0.65rem; color:#8b949e;">提升</div>
                <div style="font-size:1.1rem; font-weight:700; color:{after_color};">△ {delta_str}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 综合评分大卡片
    if overall is not None:
        ov_color = _score_color(overall)
        st.markdown(f"""
        <div style="text-align:center; padding:1.2rem; border-radius:12px;
                    background:linear-gradient(135deg, {ov_color}18, {ov_color}08);
                    border:2px solid {ov_color}50; margin-bottom:1rem;">
            <div style="font-size:0.85rem; color:#8b949e; margin-bottom:0.3rem;">综合评分</div>
            <div style="font-size:3rem; font-weight:700; color:{ov_color}; line-height:1;">
                {overall}<span style="font-size:1rem; font-weight:400;"> / 100</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # 各维度分数卡片（每行最多 4 个）
    if display_dims:
        cols_per_row = 4
        for row_start in range(0, len(display_dims), cols_per_row):
            row_dims = display_dims[row_start:row_start + cols_per_row]
            cols = st.columns(len(row_dims))
            for i, (label, score) in enumerate(row_dims):
                color = _score_color(score)
                with cols[i]:
                    st.markdown(f"""
                    <div style="text-align:center; padding:0.6rem 0.3rem; border-radius:8px;
                                background:{color}10; border:1px solid {color}35;">
                        <div style="font-size:0.75rem; color:#8b949e; margin-bottom:0.2rem;">{label}</div>
                        <div style="font-size:1.6rem; font-weight:600; color:{color};">{score}</div>
                    </div>
                    """, unsafe_allow_html=True)

    # 评价文字
    if score_raw:
        sections = _parse_score_sections(score_raw)
        if sections["evaluation"]:
            st.markdown(f"""
            <div class="review-box">
                <h4>💬 优化总结</h4>
                <div style="white-space: pre-wrap; font-size: 0.9rem;">{sections["evaluation"]}</div>
            </div>
            """, unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# 主页面
# ══════════════════════════════════════════════════════════════

def main():
    # ── Header ──
    st.markdown("""
    <div class="main-header">
        <h1>🤖 简历优化 Agent</h1>
        <p>上传简历或粘贴经历 → Agent 自动优化 + 自我审查 + 改进 → 一键下载 DOCX</p>
    </div>
    """, unsafe_allow_html=True)

    # ════════════════════════════════════════════════════════
    # 输入区
    # ════════════════════════════════════════════════════════

    st.markdown("### 📎 上传简历或粘贴内容")

    col_file, col_text = st.columns(2)

    with col_file:
        uploaded_file = st.file_uploader(
            "拖拽 PDF 或 DOCX 文件到此处",
            type=ALLOWED_EXTENSIONS,
            help=f"支持 PDF / DOCX，最大 {MAX_FILE_SIZE_MB}MB",
            key="file_uploader",
        )

    with col_text:
        st.text_area(
            "或直接粘贴简历文本",
            placeholder="把简历内容粘贴在这里…\n\n（有文件上传则优先使用文件）",
            height=200,
            key="paste_input",
        )

    # ── 目标岗位（可选）──
    st.markdown("### 🎯 目标岗位（可选）")
    st.caption("填写后优化更定向，不填也能优化")

    col_role, col_company = st.columns(2)
    with col_role:
        target_role = st.text_input("目标岗位", placeholder="例如：AI 产品实习生", key="target_role")
    with col_company:
        target_company = st.text_input("目标公司", placeholder="例如：字节跳动", key="target_company")

    jd_text = st.text_area(
        "📋 目标 JD（岗位描述，可选）",
        placeholder="粘贴完整的岗位描述，Agent 会对照 JD 分析差距、优化简历关键词匹配度…",
        height=120,
        key="jd_text",
    )

    # ── 模板选择 ──
    st.markdown("### 📋 简历模板（可选）")
    st.caption("模板用于指导 Agent 的优化方向和最终输出结构")

    template_mode = st.radio(
        "选择模板模式",
        options=["none", "builtin", "custom"],
        format_func=lambda x: {
            "none": "🚫 不用模板（保留原简历结构）— 推荐",
            "builtin": "📌 使用内置模板（AI 产品实习生方向）",
            "custom": "📎 上传自定义模板",
        }[x],
        horizontal=True,
        key="template_mode",
    )

    custom_template_text = ""
    if template_mode == "custom":
        custom_template_file = st.file_uploader(
            "上传模板文件（.md / .txt / .docx）",
            type=["md", "txt", "docx"],
            key="custom_template_uploader",
            help="上传一份你认为完美的简历作为优化模板",
        )
        if custom_template_file is not None:
            try:
                if custom_template_file.name.endswith(".docx"):
                    from docx import Document as DocxDocument
                    doc = DocxDocument(custom_template_file)
                    custom_template_text = "\n".join(
                        p.text for p in doc.paragraphs if p.text.strip()
                    )
                else:
                    custom_template_text = read_text_with_encoding_fallback(custom_template_file.read())
                st.info(f"✅ 已读取模板（{len(custom_template_text)} 字符）")
            except Exception as e:
                st.warning(f"⚠️ 模板解析失败：{e}")

    # ════════════════════════════════════════════════════════
    # 额度 & BYOK
    # ════════════════════════════════════════════════════════

    st.divider()
    st.markdown("### 💰 免费额度")

    if is_quota_exempt():
        st.success("🔑 已使用您自己的 API Key，不限次数")
    else:
        user_id = get_user_id()
        remaining = get_remaining(user_id)
        col_q1, col_q2 = st.columns([2, 1])
        with col_q1:
            if remaining > 0:
                st.info(f"🎫 今日剩余免费次数：**{remaining} / {FREE_QUOTA_PER_DAY}**")
            else:
                st.error(f"⚠️ 今日免费次数已用完（{FREE_QUOTA_PER_DAY} 次/天）")
        with col_q2:
            st.text_input(
                "🔐 使用自己的 API Key（可选）",
                type="password",
                key="_byok_api_key",
                placeholder="sk-...",
                help="填入后不限次数。Key 仅存当前会话内存，刷新页面即失效，永不写入磁盘或日志。",
                label_visibility="collapsed",
            )

    # ════════════════════════════════════════════════════════
    # 操作按钮
    # ════════════════════════════════════════════════════════

    st.divider()

    col_btn, _ = st.columns([1, 3])
    with col_btn:
        btn_disabled = st.session_state.get("agent_running", False)
        optimize_clicked = st.button(
            "🚀 开始优化",
            type="primary",
            use_container_width=True,
            disabled=btn_disabled,
        )

    # ════════════════════════════════════════════════════════
    # 执行优化
    # ════════════════════════════════════════════════════════

    if optimize_clicked:
        # ── 解析输入来源 ──
        resume_text = ""
        error_occurred = False

        if uploaded_file is not None:
            file_size_mb = uploaded_file.size / (1024 * 1024)
            if file_size_mb > MAX_FILE_SIZE_MB:
                st.error(f"❌ 文件过大（{file_size_mb:.1f}MB），请压缩到 {MAX_FILE_SIZE_MB}MB 以内。")
                error_occurred = True
            else:
                try:
                    # 写临时文件
                    suffix = os.path.splitext(uploaded_file.name)[1]
                    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                        tmp.write(uploaded_file.getbuffer())
                        tmp_path = tmp.name

                    parse_result = parse_resume_file(tmp_path)
                    resume_text = parse_result[0]
                    file_label = parse_result[1]
                    docx_template = parse_result[2] if len(parse_result) > 2 else None

                    # DOCX 文件保留作为模板（生成 DOCX 后删除）；PDF 立即清理
                    if docx_template is None:
                        os.unlink(tmp_path)
                    else:
                        st.session_state._saved_docx_template = tmp_path

                    st.info(f"✅ 已读取 {file_label} 文件（{file_size_mb:.1f}MB，{len(resume_text)} 字符）")
                except ParseError as e:
                    st.error(e.user_msg)
                    error_occurred = True

        elif st.session_state.get("paste_input", "").strip():
            resume_text = st.session_state.paste_input.strip()
        else:
            st.error("⚠️ 请上传简历文件或粘贴简历文本。")
            error_occurred = True

        if not error_occurred and resume_text:
            # ── 输入长度验证 ──
            # 有效简历至少需要一定长度（姓名 + 联系方式 + 教育背景 + 经历描述）
            MIN_RESUME_CHARS = 50
            # 纯中文/纯数字/单字重复等明显无效输入也要拦住
            stripped = resume_text.strip()
            unique_chars = len(set(stripped.replace("\n", "").replace(" ", "")))
            if len(stripped) < MIN_RESUME_CHARS:
                st.error(
                    f"⚠️ 输入内容过短（{len(stripped)} 字符），不像一份完整的简历。"
                    f"请粘贴完整的简历文本（至少 {MIN_RESUME_CHARS} 字符）。"
                )
                error_occurred = True
            elif unique_chars < 5:
                # 去重后字符数极少 = 明显是乱输入（如 "1111111"）
                st.error(
                    "⚠️ 输入内容无效（字符过于单一），请粘贴完整的简历文本。"
                )
                error_occurred = True

        if not error_occurred and resume_text:
            # ── 额度检查 ──
            allowed, quota_msg = check_quota()
            if not allowed:
                st.error(quota_msg)
                error_occurred = True

        if not error_occurred and resume_text:
            # 保存到 session_state 供后续步骤使用（用 _saved_ 前缀避免与 widget key 冲突）
            st.session_state._saved_resume_text = resume_text
            st.session_state._saved_target_role = target_role
            st.session_state._saved_target_company = target_company
            st.session_state._saved_jd_text = jd_text
            st.session_state._saved_template_mode = template_mode
            st.session_state._saved_custom_template = custom_template_text
            st.session_state.agent_running = True
            st.session_state.current_result = None
            st.session_state.docx_path = None
            st.session_state.clean_docx_path = None
            st.rerun()

    # ════════════════════════════════════════════════════════
    # Agent 执行中
    # ════════════════════════════════════════════════════════

    if st.session_state.get("agent_running"):
        resume_text = st.session_state.get("_saved_resume_text", "")
        target_role = st.session_state.get("_saved_target_role", "")
        target_company = st.session_state.get("_saved_target_company", "")
        jd_text = st.session_state.get("_saved_jd_text", "")

        with st.status("🤖 Agent 正在优化你的简历…", expanded=True) as status:
            try:
                agent = ResumeAgent(api_key=get_byok_key())

                def on_progress(step, sts):
                    render_step_status(status, step, sts)

                template_mode = st.session_state.get("_saved_template_mode", "builtin")
                custom_template = st.session_state.get("_saved_custom_template", "")
                result = agent.run(
                    resume_text=resume_text,
                    target_role=target_role,
                    target_company=target_company,
                    template_mode=template_mode,
                    custom_template=custom_template,
                    jd_text=jd_text,
                    progress_callback=on_progress,
                )

                # 生成 DOCX
                status.write("📥 正在生成 DOCX…")
                docx_path = generate_docx(
                    result["round2"],
                    result["assessment"],
                    resume_text,
                    template_path=st.session_state.get("_saved_docx_template"),
                )
                status.write("✅ DOCX 已生成")

                # 生成干净简历 DOCX
                clean_docx_path = ""
                final_resume = result.get("final_resume", "")
                if final_resume:
                    try:
                        clean_docx_path = generate_clean_resume_docx(final_resume)
                        status.write("✅ 干净简历 DOCX 已生成")
                    except Exception:
                        pass

                # 清理 DOCX 模板临时文件
                if st.session_state.get("_saved_docx_template"):
                    try:
                        os.unlink(st.session_state._saved_docx_template)
                    except OSError:
                        pass
                    st.session_state._saved_docx_template = None

                # 保存结果
                st.session_state.current_result = result
                st.session_state.docx_path = docx_path
                st.session_state.clean_docx_path = clean_docx_path
                st.session_state._saved_round2_output = result.get("round2", "")
                st.session_state._followup_round = 0
                st.session_state._followup_history = []
                st.session_state.agent_running = False

                # ── 保存到优化历史 ──
                from datetime import datetime as _dt
                history = st.session_state.get("_optimization_history", [])
                history.append({
                    "timestamp": _dt.now().strftime("%m-%d %H:%M"),
                    "target_role": st.session_state.get("_saved_target_role", "") or "未指定",
                    "target_company": st.session_state.get("_saved_target_company", "") or "",
                    "scores": result.get("scores", {}),
                    "metrics": result.get("metrics", {}),
                    "round2": result.get("round2", ""),
                    "final_resume": result.get("final_resume", ""),
                    "assessment": result.get("assessment", ""),
                    "score_raw": result.get("score_raw", ""),
                    "docx_path": docx_path,
                    "clean_docx_path": clean_docx_path,
                })
                st.session_state._optimization_history = history

                # ── 扣减免费额度（BYOK 用户不扣）──
                consume_quota()

                status.update(label="✅ 优化完成！", state="complete")

                st.rerun()

            except AgentError as e:
                st.session_state.agent_running = False
                status.update(label=f"❌ {e.step} 失败", state="error")
                st.markdown(f"""
                <div class="error-box">
                    <strong>出错了</strong><br>{e.user_msg}
                </div>
                """, unsafe_allow_html=True)

            except Exception as e:
                st.session_state.agent_running = False
                status.update(label="❌ 未知错误", state="error")
                st.error(f"发生未知错误：{str(e)[:200]}")

    # ════════════════════════════════════════════════════════
    # 展示结果
    # ════════════════════════════════════════════════════════

    result = st.session_state.get("current_result")
    docx_path = st.session_state.get("docx_path")

    if result and docx_path:
        st.divider()
        render_results(result)

    # ════════════════════════════════════════════════════════
    # 优化历史（版本选择器）
    # ════════════════════════════════════════════════════════

    history = st.session_state.get("_optimization_history", [])
    if len(history) > 1:
        st.divider()
        with st.expander(f"📚 优化历史（{len(history)} 个版本）", expanded=False):
            for i, h in enumerate(reversed(history)):
                idx = len(history) - 1 - i
                is_current = (h["round2"] == result.get("round2", "")) if result else False
                prefix = "📍 " if is_current else ""
                role_label = f"{h['target_role']}"
                if h.get("target_company"):
                    role_label += f" @ {h['target_company']}"
                score_summary = f" | 综合 {h['scores'].get('综合评分', '?')}分" if h.get("scores") else ""

                col_info, col_btn = st.columns([3, 1])
                with col_info:
                    st.markdown(f"{prefix}**v{idx + 1}** · {h['timestamp']} · {role_label}{score_summary}")
                with col_btn:
                    if not is_current and st.button(f"查看", key=f"hist_view_{idx}", use_container_width=True):
                        st.session_state.current_result = {
                            "round1": "", "review": "",
                            "round2": h["round2"],
                            "assessment": h["assessment"],
                            "final_resume": h["final_resume"],
                            "scores": h["scores"],
                            "score_raw": h.get("score_raw", ""),
                        }
                        st.session_state.docx_path = h.get("docx_path", "")
                        st.session_state.clean_docx_path = h.get("clean_docx_path", "")
                        st.session_state._saved_round2_output = h["round2"]
                        st.rerun()

    # ════════════════════════════════════════════════════════
    # 多轮追问功能（显示在结果下方）
    # ════════════════════════════════════════════════════════

    if result and docx_path:
        st.divider()
        followup_round = st.session_state.get("_followup_round", 0)
        round_label = f"第 {followup_round + 1} 轮修改" if followup_round > 0 else "对结果不满意？"
        st.markdown(f"### 💬 {round_label}")
        st.caption("告诉 Agent 怎么改，可持续迭代多轮。")

        col_fb, col_btn = st.columns([3, 1])
        with col_fb:
            feedback = st.text_input(
                "修改意见",
                placeholder="例如：第三段偏产品方向、整体太长了、动词不够有力…",
                key="followup_input",
                label_visibility="collapsed",
            )
        with col_btn:
            followup_clicked = st.button(
                "🔧 再次优化" if followup_round == 0 else f"🔧 第 {followup_round + 1} 轮修改",
                use_container_width=True,
                key="btn_followup",
            )

        if followup_clicked and feedback.strip():
            with st.spinner("🔧 Agent 正在调整…"):
                try:
                    agent = ResumeAgent(api_key=get_byok_key())
                    # 使用 _saved_round2_output 作为当前版本（支持多轮迭代）
                    current_output = st.session_state.get("_saved_round2_output", result.get("round2", ""))
                    new_result = agent.followup(
                        feedback.strip(),
                        st.session_state.get("_saved_resume_text", ""),
                        current_output=current_output,
                        template_mode=st.session_state.get("_saved_template_mode", "builtin"),
                        custom_template=st.session_state.get("_saved_custom_template", ""),
                        jd_text=st.session_state.get("_saved_jd_text", ""),
                    )
                    # 更新追问链状态
                    st.session_state._saved_round2_output = new_result["round2"]
                    st.session_state._followup_round = followup_round + 1
                    history = st.session_state.get("_followup_history", [])
                    history.append({
                        "round": followup_round + 1,
                        "feedback": feedback.strip(),
                        "round2_snippet": new_result["round2"][:200] + "…",
                    })
                    st.session_state._followup_history = history

                    st.session_state.current_result = new_result
                    st.session_state.docx_path = generate_docx(
                        new_result["round2"],
                        new_result["assessment"],
                        st.session_state.get("_saved_resume_text", ""),
                        template_path=st.session_state.get("_saved_docx_template"),
                    )
                    # 生成干净简历 DOCX
                    final_resume = new_result.get("final_resume", "")
                    if final_resume:
                        try:
                            st.session_state.clean_docx_path = generate_clean_resume_docx(final_resume)
                        except Exception:
                            st.session_state.clean_docx_path = ""
                    st.rerun()
                except AgentError as e:
                    st.error(e.user_msg)
                except Exception as e:
                    st.error(f"调整失败：{str(e)[:200]}")

        # ── 追问历史（可折叠）──
        history = st.session_state.get("_followup_history", [])
        if history:
            with st.expander(f"📝 修改记录（{len(history)} 轮）", expanded=False):
                for h in reversed(history):
                    st.markdown(f"**第 {h['round']} 轮**：{h['feedback'][:80]}")
                    st.caption(f"修改后前 200 字：{h['round2_snippet']}")
                    st.divider()

    # ════════════════════════════════════════════════════════
    # 面试题生成
    # ════════════════════════════════════════════════════════

    if result and docx_path:
        st.divider()
        st.markdown("### 🎯 面试准备")
        st.caption("根据优化后的简历生成针对性面试题，帮你提前准备。")

        gen_clicked = st.button("🎯 生成面试题", use_container_width=True, key="btn_interview")

        if gen_clicked:
            with st.spinner("🤔 面试官正在出题…"):
                try:
                    agent = ResumeAgent(api_key=get_byok_key())
                    final_resume = result.get("final_resume", "")
                    resume_to_use = final_resume or result.get("round2", "")
                    questions = agent.generate_questions(
                        resume_to_use,
                        st.session_state.get("_saved_jd_text", ""),
                    )
                    st.session_state._interview_questions = questions
                    st.rerun()
                except AgentError as e:
                    st.error(e.user_msg)
                except Exception as e:
                    st.error(f"生成失败：{str(e)[:200]}")

        # 展示已生成的面试题
        questions = st.session_state.get("_interview_questions", "")
        if questions:
            with st.expander("📝 查看面试题", expanded=True):
                st.markdown(questions)


if __name__ == "__main__":
    main()
