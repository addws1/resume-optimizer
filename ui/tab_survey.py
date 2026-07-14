"""
=============================================================================
简历优化助手 · Tab 4：用户调研
=============================================================================
标准化问卷录入、NPS 评分、痛点汇总报告生成。
数据本地存储至 data/surveys.json，不涉及云端上传。
=============================================================================
"""

import json
from datetime import datetime

import streamlit as st

from config import SURVEY_FILE, DATA_DIR
from utils.logger import log_error, log_info


# ══════════════════════════════════════════════════════════════
# 数据持久化
# ══════════════════════════════════════════════════════════════

def load_surveys() -> list:
    """从本地 JSON 加载调研数据"""
    if SURVEY_FILE.exists():
        try:
            with open(SURVEY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def save_survey(entry: dict) -> bool:
    """
    保存一条调研记录到本地 JSON。

    自动分配递增 ID 和时间戳。
    """
    surveys = load_surveys()
    entry["id"] = len(surveys) + 1
    entry["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    surveys.append(entry)
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        with open(SURVEY_FILE, "w", encoding="utf-8") as f:
            json.dump(surveys, f, ensure_ascii=False, indent=2)
        log_info(f"调研记录已保存: id={entry['id']}")
        return True
    except Exception as e:
        log_error("survey_save", e, "保存调研记录失败")
        st.error(f"❌ 保存失败: {e}")
        return False


# ══════════════════════════════════════════════════════════════
# 报告生成
# ══════════════════════════════════════════════════════════════

def generate_survey_report() -> str:
    """生成用户痛点汇总报告（Markdown）"""
    surveys = load_surveys()
    if not surveys:
        return "暂无调研数据。"

    total = len(surveys)
    nps_scores = [
        s.get("nps_score", 0)
        for s in surveys
        if s.get("nps_score") is not None
    ]
    avg_nps = sum(nps_scores) / len(nps_scores) if nps_scores else 0

    # 汇总痛点
    all_pain_points = []
    for s in surveys:
        pp = s.get("pain_points", "").strip()
        if pp:
            all_pain_points.append(pp)

    # 汇总高频建议
    all_suggestions = []
    for s in surveys:
        sug = s.get("suggestions", "").strip()
        if sug:
            all_suggestions.append(sug)

    report = f"""# 用户调研汇总报告
> 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 概况
- 总调研样本数：**{total}**
- 平均 NPS 评分：**{avg_nps:.1f} / 10**
- 反馈痛点数：**{len(all_pain_points)}**

## NPS 评分分布
"""

    # 计算分布
    detractors = sum(1 for s in nps_scores if s <= 6)
    passives = sum(1 for s in nps_scores if 7 <= s <= 8)
    promoters = sum(1 for s in nps_scores if s >= 9)
    total_nps = len(nps_scores) or 1

    report += f"""
| 分类 | 人数 | 占比 |
|------|------|------|
| 😡 贬损者（0-6） | {detractors} | {detractors / total_nps * 100:.0f}% |
| 😐 被动者（7-8） | {passives} | {passives / total_nps * 100:.0f}% |
| 😍 推荐者（9-10） | {promoters} | {promoters / total_nps * 100:.0f}% |

**NPS = {promoters / total_nps * 100 - detractors / total_nps * 100:.0f}**

## 用户痛点汇总
"""
    for i, pp in enumerate(all_pain_points, 1):
        report += f"\n{i}. {pp}\n"

    if all_suggestions:
        report += "\n## 用户建议汇总\n"
        for i, sug in enumerate(all_suggestions, 1):
            report += f"\n{i}. {sug}\n"

    report += "\n---\n> 数据来源：简历优化助手用户调研模块"
    return report


# ══════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════

def render():
    """渲染「用户调研」Tab 的全部 UI"""
    st.markdown("### 📝 标准化用户调研")
    st.caption("录入 1v1 访谈记录、NPS 评分、痛点反馈，一键生成汇总报告")

    col_survey_form, col_survey_report = st.columns([1, 1])

    # ── 左侧：录入表单 ──
    with col_survey_form:
        st.markdown("#### 📋 调研问卷录入")
        st.markdown('<div class="input-card">', unsafe_allow_html=True)

        survey_name = st.text_input(
            "受访者称呼", placeholder="例如：张同学 / 匿名用户", key="survey_name"
        )
        survey_type = st.selectbox(
            "调研类型",
            ["1v1 深度访谈", "问卷调查", "用户测试反馈", "自发反馈"],
            key="survey_type",
        )
        survey_role = st.selectbox(
            "用户身份",
            ["应届生求职者", "有工作经验求职者", "HR / 面试官", "其他"],
            key="survey_role",
        )
        survey_nps = st.slider(
            "NPS 推荐度评分",
            min_value=0, max_value=10, value=8,
            help="0=完全不推荐，10=强烈推荐",
            key="survey_nps",
        )
        survey_pain = st.text_area(
            "核心痛点 / 反馈",
            placeholder="描述用户在使用简历优化过程中遇到的主要痛点或反馈…",
            height=100,
            key="survey_pain",
        )
        survey_suggestions = st.text_area(
            "改进建议",
            placeholder="用户提出的改进建议…",
            height=80,
            key="survey_suggestions",
        )

        if st.button("💾 保存调研记录", type="primary",
                     use_container_width=True, key="btn_save_survey"):
            if not survey_name.strip():
                st.error("⚠️ 请至少填写受访者称呼。")
            else:
                entry = {
                    "name": survey_name,
                    "type": survey_type,
                    "role": survey_role,
                    "nps_score": survey_nps,
                    "pain_points": survey_pain,
                    "suggestions": survey_suggestions,
                }
                if save_survey(entry):
                    st.success("✅ 调研记录已保存！")
                    st.session_state.survey_submitted = True
                    st.rerun()

        st.markdown("</div>", unsafe_allow_html=True)

    # ── 右侧：数据概览 & 报告 ──
    with col_survey_report:
        st.markdown("#### 📊 调研数据概览")

        surveys = load_surveys()
        if surveys:
            st.metric("总样本数", len(surveys))

            with st.expander(f"📋 最近录入（共 {len(surveys)} 条）", expanded=True):
                for s in reversed(surveys[-5:]):
                    st.markdown(
                        f"""
                        <div class="kb-card">
                            <strong>{s.get('name', '未知')}</strong>
                            <span style="color:#8b949e;"> | {s.get('type', '')} | NPS: {s.get('nps_score', '-')}/10</span>
                            <br><span style="color:#c9d1d9;font-size:0.85rem;">痛点：{s.get('pain_points', '-')[:60]}…</span>
                            <br><span style="color:#8b949e;font-size:0.75rem;">{s.get('created_at', '')}</span>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
        else:
            st.info("暂无调研数据，请在左侧录入。")

        st.divider()

        # 生成报告按钮
        if st.button("📄 生成痛点汇总报告", use_container_width=True, key="btn_gen_report"):
            if not load_surveys():
                st.warning("⚠️ 暂无调研数据，请先录入调研记录。")
            else:
                report = generate_survey_report()
                st.session_state.survey_report = report

        # 展示与下载报告
        if st.session_state.get("survey_report"):
            report = st.session_state.survey_report
            with st.expander("📋 报告预览", expanded=True):
                st.markdown(report)

            st.download_button(
                label="📥 下载调研报告（Markdown）",
                data=report,
                file_name=f"user_research_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md",
                mime="text/markdown",
                use_container_width=True,
            )
