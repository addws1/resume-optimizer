"""
=============================================================================
简历优化助手 · 效果评估模块
=============================================================================
模型输出质量量化打分、评分渲染、历史趋势图、CSV 导出。
=============================================================================
"""

import csv
import io
import json
import re
from datetime import datetime
from typing import Optional

import streamlit as st

from utils.logger import log_error, log_info


# ══════════════════════════════════════════════════════════════
# Prompt 构建
# ══════════════════════════════════════════════════════════════

def build_evaluation_prompt(
    original: str, optimized: str, target_role: str
) -> str:
    """构建效果评估 Prompt（三维度打分）"""
    return f"""你是一位严格的简历质量评估专家。请对以下简历优化结果进行量化打分。

## 评估对象
- 目标岗位：{target_role or "未指定"}
- 原始经历：
{original}

- 优化版本：
{optimized}

## 评分要求

请从以下三个维度评分（0-5 分，保留 1 位小数），并给出简要理由：

| 维度 | 评分标准 |
|------|---------|
| **完整性** | 是否覆盖所有关键信息？STAR 要素是否齐全？有无遗漏重要成果？ |
| **岗位匹配度** | 优化后的表述是否匹配目标岗位？关键词是否突出？ |
| **格式规范度** | 语法是否通顺？格式是否统一？可读性如何？ |

## 输出格式（严格 JSON）

```json
{{
  "completeness": 4.0,
  "job_match": 4.0,
  "format_quality": 4.0,
  "completeness_reason": "一句话理由（10字以内）",
  "job_match_reason": "一句话理由（10字以内）",
  "format_quality_reason": "一句话理由（10字以内）",
  "overall_comment": "总体评价（30字以内）"
}}
```

请仅输出 JSON，不要添加任何其他文字。"""


# ══════════════════════════════════════════════════════════════
# JSON 容错解析
# ══════════════════════════════════════════════════════════════

def _safe_parse_json(raw: str) -> Optional[dict]:
    """
    多策略 JSON 解析，应对 LLM 输出格式错乱。

    策略：
    1. 直接 json.loads
    2. 正则提取 ```json ... ``` 代码块
    3. 正则提取花括号内容并尝试修复常见错误
    4. 逐字段正则兜底提取
    """
    if not raw:
        return None

    # 策略 1：直接解析
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # 策略 2：提取代码块
    code_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', raw)
    if code_match:
        try:
            return json.loads(code_match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 策略 3：提取花括号内容，尝试修复
    brace_match = re.search(r'\{[\s\S]*\}', raw)
    if brace_match:
        json_str = brace_match.group(0)
        # 修复常见错误：末尾多余逗号
        json_str = re.sub(r',\s*([}\]])', r'\1', json_str)
        # 修复单引号
        # (保持双引号不变)
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            pass

    # 策略 4：逐字段正则兜底
    scores = {}
    patterns = {
        "completeness": r'["\']?completeness["\']?\s*[:：]\s*([\d.]+)',
        "job_match": r'["\']?job_match["\']?\s*[:：]\s*([\d.]+)',
        "format_quality": r'["\']?format_quality["\']?\s*[:：]\s*([\d.]+)',
        "completeness_reason": r'["\']?completeness_reason["\']?\s*[:：]\s*["\']?(.+?)["\']?[,\s\n}]',
        "job_match_reason": r'["\']?job_match_reason["\']?\s*[:：]\s*["\']?(.+?)["\']?[,\s\n}]',
        "format_quality_reason": r'["\']?format_quality_reason["\']?\s*[:：]\s*["\']?(.+?)["\']?[,\s\n}]',
        "overall_comment": r'["\']?overall_comment["\']?\s*[:：]\s*["\']?(.+?)["\']?[,\s\n}]',
    }
    for key, pat in patterns.items():
        m = re.search(pat, raw, re.IGNORECASE)
        if m:
            val = m.group(1).strip().rstrip(',').strip('"').strip("'")
            try:
                if key in ("completeness", "job_match", "format_quality"):
                    scores[key] = float(val)
                else:
                    scores[key] = val
            except ValueError:
                continue

    if scores:
        return scores
    return None


# ══════════════════════════════════════════════════════════════
# 评估主函数
# ══════════════════════════════════════════════════════════════

def evaluate_optimization(
    original: str,
    optimized: str,
    target_role: str,
    llm_client,
) -> Optional[dict]:
    """
    调用 LLM 对优化结果进行量化打分。

    Args:
        original: 原始简历文本
        optimized: 优化后的文本
        target_role: 目标岗位
        llm_client: LLM 客户端实例（需支持 generate 方法）

    Returns:
        评分 dict 或 None
    """
    try:
        prompt = build_evaluation_prompt(original, optimized, target_role)
        raw = llm_client.generate(prompt, max_tokens=1024)
        scores = _safe_parse_json(raw)

        if scores:
            # 校验必要字段
            for field in ("completeness", "job_match", "format_quality"):
                if field not in scores:
                    scores[field] = 0.0
            log_info(f"评估完成: 均分={(scores.get('completeness',0)+scores.get('job_match',0)+scores.get('format_quality',0))/3:.1f}")
            return scores
        else:
            log_error("evaluation", ValueError("JSON解析失败"), raw[:200])
            return None

    except Exception as e:
        log_error("evaluation", e, "LLM 评估调用失败")
        return None


# ══════════════════════════════════════════════════════════════
# 评分渲染
# ══════════════════════════════════════════════════════════════

def render_evaluation_scores(scores: dict):
    """
    在 Streamlit 中渲染评分卡片（三列布局 + 综合均分）。

    Args:
        scores: 评分 dict
    """
    if not scores:
        return

    st.markdown("### 📊 本次优化质量评估")
    col1, col2, col3 = st.columns(3)

    metrics = [
        ("完整性", "completeness", "completeness_reason"),
        ("岗位匹配度", "job_match", "job_match_reason"),
        ("格式规范度", "format_quality", "format_quality_reason"),
    ]

    for col, (label, key, reason_key) in zip([col1, col2, col3], metrics):
        value = float(scores.get(key, 0))
        reason = scores.get(reason_key, "")
        with col:
            st.markdown(
                f"""
                <div class="score-card">
                    <div class="score-label">{label}</div>
                    <div class="score-value">{value:.1f}</div>
                    <div style="color:#8b949e;font-size:0.8rem;margin-top:6px;">/ 5.0</div>
                    <div style="color:#c9d1d9;font-size:0.75rem;margin-top:8px;">{reason}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    # 综合均分
    avg = (
        float(scores.get("completeness", 0))
        + float(scores.get("job_match", 0))
        + float(scores.get("format_quality", 0))
    ) / 3
    overall = scores.get("overall_comment", "")
    st.markdown(
        f"""
        <div class="section-card" style="text-align:center;">
            <span class="section-badge badge-score">📈 综合均分</span>
            <div class="score-value" style="font-size:2.4rem;">{avg:.1f} / 5.0</div>
            <div class="score-label">{overall}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    return avg


# ══════════════════════════════════════════════════════════════
# 趋势图 & CSV
# ══════════════════════════════════════════════════════════════

def render_history_chart(history: list):
    """
    渲染历史评分的折线图。

    Args:
        history: session_state.history 列表
    """
    scored = [h for h in history if h.get("eval_scores")]
    if len(scored) < 2:
        st.caption("至少需要 2 轮评分数据才能展示趋势图。")
        return

    chart_data = {
        "轮次": [],
        "完整性": [],
        "岗位匹配度": [],
        "格式规范度": [],
        "均分": [],
    }
    for i, h in enumerate(scored, 1):
        s = h["eval_scores"]
        chart_data["轮次"].append(f"#{i}")
        chart_data["完整性"].append(float(s.get("completeness", 0)))
        chart_data["岗位匹配度"].append(float(s.get("job_match", 0)))
        chart_data["格式规范度"].append(float(s.get("format_quality", 0)))
        chart_data["均分"].append(
            (float(s.get("completeness", 0))
             + float(s.get("job_match", 0))
             + float(s.get("format_quality", 0))) / 3
        )

    import pandas as pd
    df = pd.DataFrame(chart_data).set_index("轮次")
    st.line_chart(df, height=320)


def generate_eval_csv(history: list) -> Optional[str]:
    """
    生成评估数据 CSV 字符串。

    Args:
        history: session_state.history 列表

    Returns:
        CSV 字符串或 None
    """
    scored = [h for h in history if h.get("eval_scores")]
    if not scored:
        return None

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "轮次", "原始经历(摘要)", "完整性", "岗位匹配度",
        "格式规范度", "均分", "总体评价", "优化时间"
    ])
    for i, h in enumerate(scored, 1):
        s = h["eval_scores"]
        preview = h["experience"].replace("\n", " ")[:60]
        avg = (
            float(s.get("completeness", 0))
            + float(s.get("job_match", 0))
            + float(s.get("format_quality", 0))
        ) / 3
        writer.writerow([
            i, preview,
            s.get("completeness", ""),
            s.get("job_match", ""),
            s.get("format_quality", ""),
            f"{avg:.1f}",
            s.get("overall_comment", ""),
            h.get("timestamp", ""),
        ])

    return output.getvalue()


def get_eval_stats(history: list) -> dict:
    """
    从历史记录中计算评估统计数据。

    Returns:
        包含 scored_count, total_count, latest_avg 的 dict
    """
    scored = [h for h in history if h.get("eval_scores")]
    total = len(history)
    scored_count = len(scored)

    latest_avg = None
    if scored:
        all_avgs = []
        for h in scored:
            s = h["eval_scores"]
            avg = (
                float(s.get("completeness", 0))
                + float(s.get("job_match", 0))
                + float(s.get("format_quality", 0))
            ) / 3
            all_avgs.append(avg)
        latest_avg = all_avgs[-1]

    return {
        "total_count": total,
        "scored_count": scored_count,
        "latest_avg": latest_avg,
    }
