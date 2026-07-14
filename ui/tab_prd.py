"""
=============================================================================
简历优化助手 · Tab 2：PRD 需求文档导出
=============================================================================
基于用户项目经历 + 目标 JD，AI 自动生成标准化产品需求文档。
=============================================================================
"""

from datetime import datetime

import streamlit as st

from llm_client import get_llm_client
from utils.logger import log_error, log_info


# ══════════════════════════════════════════════════════════════
# PRD Prompt 构建
# ══════════════════════════════════════════════════════════════

def build_prd_prompt(experience: str, target_role: str, target_company: str) -> str:
    """构建 PRD 生成专用 Prompt"""
    return f"""你是一位资深 AI 产品经理，请根据以下项目经历，生成一份标准化的产品需求文档（PRD）。

## 输入信息
- 目标岗位：{target_role or "未指定"}
- 目标公司：{target_company or "未指定"}
- 项目经历参考：{experience}

## 输出要求

请严格按照以下结构输出一份完整的 PRD 文档（Markdown 格式），每个部分必须包含具体内容，不得留空：

### 1. 项目背景与目标
- 行业背景与市场痛点
- 项目核心目标（SMART 原则）
- 目标用户画像

### 2. 用户场景与需求
- 核心用户使用场景（至少 3 个）
- 用户需求优先级矩阵（P0/P1/P2）

### 3. 功能需求
- 核心功能列表（含优先级）
- 功能详细描述（每个功能 2-3 句话）
- MVP 范围界定

### 4. 验收标准
- 功能验收标准（量化指标）
- 体验验收标准
- 上线 Check List

### 5. 数据埋点与效果评估
- 核心指标定义（北极星指标 + 辅助指标）
- 数据采集方案概要

请确保内容具体、可执行、可直接用于需求评审，贴合 AI 产品规范。"""


# ══════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════

def render():
    """渲染「PRD 导出」Tab 的全部 UI"""
    st.markdown("### 📋 PRD 需求文档一键生成")
    st.caption("基于您的项目经历 + 目标 JD，AI 自动生成标准化产品需求文档")

    st.markdown('<div class="input-card">', unsafe_allow_html=True)

    prd_experience = st.text_area(
        "项目经历 / 产品想法",
        placeholder="描述您的项目经历或产品想法，越详细生成的 PRD 越精确…",
        height=180,
        key="prd_experience",
    )
    col_prd1, col_prd2 = st.columns(2)
    with col_prd1:
        prd_role = st.text_input(
            "目标岗位", placeholder="例如：AI 产品经理", key="prd_role"
        )
    with col_prd2:
        prd_company = st.text_input(
            "目标公司", placeholder="例如：字节跳动", key="prd_company"
        )

    st.markdown("</div>", unsafe_allow_html=True)

    # ── 生成按钮（防重复点击）──
    col_prd_btn1, col_prd_btn2 = st.columns([2, 1])
    with col_prd_btn1:
        btn_prd_disabled = st.session_state.get("_prd_generating", False)
        if st.button(
            "🚀 生成 PRD 文档",
            type="primary",
            use_container_width=True,
            key="btn_gen_prd",
            disabled=btn_prd_disabled,
        ):
            if not prd_experience.strip():
                st.error("⚠️ 请先输入项目经历或产品想法。")
            else:
                st.session_state._prd_generating = True
                st.rerun()

    # ── 执行生成 ──
    if st.session_state.get("_prd_generating"):
        with st.spinner("🤖 AI 正在生成 PRD 文档…"):
            try:
                llm_client = get_llm_client()
                prompt = build_prd_prompt(
                    prd_experience, prd_role or "", prd_company or ""
                )
                prd_content = llm_client.generate(prompt, max_tokens=4096)
                st.session_state.prd_content = prd_content
                st.session_state.prd_generated = True
                log_info("PRD 生成完成")
            except Exception as e:
                st.error(f"❌ PRD 生成失败: {e}")
                log_error("tab_prd", e, "PRD 生成失败")
            finally:
                st.session_state._prd_generating = False
                st.rerun()

    # ── 展示生成的 PRD ──
    if st.session_state.get("prd_generated") and st.session_state.get("prd_content"):
        st.divider()
        st.markdown("### 🎯 生成的 PRD 文档")

        prd_content = st.session_state.prd_content
        st.markdown(
            f"""
            <div class="section-card">
                <span class="section-badge badge-prd">📋 PRD 需求文档</span>
                <div class="section-content">{prd_content.replace(chr(10), '<br>')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 下载按钮
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                label="📥 下载 PRD（Markdown）",
                data=prd_content,
                file_name=f"PRD_{prd_role or 'product'}_{datetime.now().strftime('%Y%m%d')}.md",
                mime="text/markdown",
                use_container_width=True,
            )
        with col_dl2:
            st.download_button(
                label="📥 下载 PRD（TXT）",
                data=prd_content,
                file_name=f"PRD_{prd_role or 'product'}_{datetime.now().strftime('%Y%m%d')}.txt",
                mime="text/plain",
                use_container_width=True,
            )
