"""
=============================================================================
简历优化助手 · Tab 3：效果评估
=============================================================================
查看历史优化质量趋势，导出评估对比数据。
=============================================================================
"""

import io
from datetime import datetime

import pandas as pd
import streamlit as st

from utils.evaluation import (
    render_history_chart,
    generate_eval_csv,
    get_eval_stats,
)


# ══════════════════════════════════════════════════════════════
# 主入口
# ══════════════════════════════════════════════════════════════

def render():
    """渲染「效果评估」Tab 的全部 UI"""
    st.markdown("### 📊 模型效果量化评估")
    st.caption("查看历史优化质量趋势，导出评估对比数据")

    history = st.session_state.get("history", [])
    stats = get_eval_stats(history)

    # ── 统计卡片 ──
    col_stat1, col_stat2, col_stat3 = st.columns(3)
    with col_stat1:
        st.metric("总优化次数", stats["total_count"])
    with col_stat2:
        st.metric("已评估次数", stats["scored_count"])
    with col_stat3:
        if stats["latest_avg"] is not None:
            st.metric("最新均分", f"{stats['latest_avg']:.1f} / 5.0")
        else:
            st.metric("最新均分", "N/A")

    st.divider()

    # ── 趋势图 ──
    if stats["scored_count"] >= 2:
        st.markdown("#### 📈 优化质量趋势")
        render_history_chart(history)
    elif stats["scored_count"] == 1:
        st.info("📈 再进行一次优化并评估后，即可展示趋势折线图。")
    else:
        st.info("📈 暂无评估数据。在「简历优化」标签页完成优化后自动生成评估。")

    st.divider()

    # ── CSV 导出 ──
    if stats["scored_count"] > 0:
        st.markdown("#### 📥 导出评估数据")
        csv_data = generate_eval_csv(history)
        if csv_data:
            st.download_button(
                label="📥 导出评估对比表（CSV）",
                data=csv_data,
                file_name=f"evaluation_scores_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv",
                use_container_width=True,
            )

            # 数据预览
            with st.expander("📋 数据预览", expanded=False):
                try:
                    df = pd.read_csv(io.StringIO(csv_data))
                    st.dataframe(df, use_container_width=True)
                except Exception as e:
                    st.warning(f"预览失败: {e}")
