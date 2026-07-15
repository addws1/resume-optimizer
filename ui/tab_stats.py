"""
=============================================================================
简历优化助手 · Tab 5：数据看板
=============================================================================
展示项目运行统计：访问量、优化次数、评分趋势、模型使用分布。
数据来源：utils/stats.py（JSON 文件持久化）。
=============================================================================
"""

import streamlit as st

from utils.stats import get_all_stats


def render():
    """渲染数据看板 Tab"""
    st.markdown("### 📊 项目数据看板")
    st.caption("以下数据由应用自动采集，跨会话持久化。刷新页面或重启服务不会丢失。")

    all_stats = get_all_stats()
    visits = all_stats["visits"]
    opts = all_stats["optimizations"]
    llm = all_stats["llm"]

    # ════════════════════════════════════════════════════════════
    # 第一行：核心指标卡片
    # ════════════════════════════════════════════════════════════
    st.markdown("#### 📈 核心指标")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("累计访问", visits["total_visits"])
    with col2:
        st.metric("今日访问", visits["today_visits"])
    with col3:
        st.metric("累计优化次数", opts["total_count"])
    with col4:
        avg_label = f"{opts['avg_score_all']} / 5.0" if opts["avg_score_all"] else "暂无"
        st.metric("平均优化评分", avg_label)
    with col5:
        st.metric("RAG 使用率", f"{opts['rag_usage_rate']}%")

    st.divider()

    # ════════════════════════════════════════════════════════════
    # 第二行：LLM 调用统计
    # ════════════════════════════════════════════════════════════
    if llm["total_calls"] > 0:
        st.markdown("#### 🤖 LLM 调用概览")
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("API 调用次数", llm["total_calls"])
        with col2:
            st.metric("总 Token 消耗", f"{llm['total_tokens']:,}")
        with col3:
            st.metric("成功率", f"{llm['success_rate']}%")
        with col4:
            st.metric("平均响应耗时", f"{llm['avg_duration_ms']}ms")

        # Provider 分布
        if llm["providers"]:
            st.markdown("**模型使用分布**")
            providers = llm["providers"]
            # 用简单的进度条展示
            for provider, count in sorted(providers.items(), key=lambda x: -x[1]):
                pct = count / llm["total_calls"] * 100
                st.markdown(
                    f"`{provider}` ▏{count} 次（{pct:.0f}%）"
                )
                st.progress(pct / 100)

        st.divider()

    # ════════════════════════════════════════════════════════════
    # 第三行：优化评分趋势（从 optimizations.json 读取）
    # ════════════════════════════════════════════════════════════
    if opts["total_count"] >= 2:
        st.markdown("#### 📈 优化评分趋势")

        from utils.stats import _read_json, OPTIMIZATIONS_FILE
        data = _read_json(OPTIMIZATIONS_FILE)
        records = data.get("records", [])
        scored = [r for r in records if r.get("avg_score") is not None]

        if len(scored) >= 2:
            chart_data = {
                "序号": [],
                "均分": [],
            }
            for i, r in enumerate(scored, 1):
                chart_data["序号"].append(i)
                chart_data["均分"].append(r["avg_score"])

            import pandas as pd
            df = pd.DataFrame(chart_data).set_index("序号")
            st.line_chart(df, height=250)

    # ════════════════════════════════════════════════════════════
    # 第四行：最近优化记录
    # ════════════════════════════════════════════════════════════
    if opts["total_count"] > 0:
        st.markdown("#### 📋 最近优化记录")

        from utils.stats import _read_json, OPTIMIZATIONS_FILE
        data = _read_json(OPTIMIZATIONS_FILE)
        records = data.get("records", [])

        # 显示最近 10 条
        recent = list(reversed(records))[:10]
        for i, r in enumerate(recent):
            ts = r.get("timestamp", "")
            role = r.get("role", "")
            company = r.get("company", "")
            avg = r.get("avg_score")
            rag = "🔍" if r.get("use_rag") else ""
            preview = r.get("experience_preview", "")[:60]

            role_tag = f" → {role}" if role else ""
            company_tag = f" @ {company}" if company else ""
            score_tag = f" ⭐{avg}" if avg is not None else ""

            st.markdown(
                f"**{i+1}.** {rag} `{ts}`{role_tag}{company_tag}{score_tag}"
            )
            if preview:
                st.caption(f"　　　{preview}…")

    # ════════════════════════════════════════════════════════════
    # 空状态
    # ════════════════════════════════════════════════════════════
    if visits["total_visits"] == 0 and opts["total_count"] == 0:
        st.info("👋 还没有数据。使用「简历优化」功能后，统计数据会自动出现在这里。")

    st.divider()
    st.caption("💡 数据存储于本地 `data/stats.json` 和 `data/optimizations.json`，不会上传到云端。")
