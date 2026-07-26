"""
=============================================================================
简历优化助手 · 统计数据模块
=============================================================================
持久化访问记录、优化历史、LLM 调用统计。
数据存储于 data/stats.json 和 data/optimizations.json。
=============================================================================
"""

import json
import os
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from config import DATA_DIR


# ── 数据文件路径 ──────────────────────────────────
STATS_FILE = DATA_DIR / "stats.json"
OPTIMIZATIONS_FILE = DATA_DIR / "optimizations.json"


def _read_json(filepath: Path) -> dict:
    """安全读取 JSON 文件，不存在则返回空 dict"""
    if not filepath.exists():
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _write_json(filepath: Path, data: dict):
    """安全写入 JSON 文件"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════
# 访问统计
# ══════════════════════════════════════════════════════════════

def log_visit():
    """记录一次页面访问（每次 Streamlit 启动/刷新触发）"""
    stats = _read_json(STATS_FILE)
    visits = stats.get("visits", [])
    visits.append(datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

    # 只保留最近 2000 条访问记录，避免文件膨胀
    if len(visits) > 2000:
        visits = visits[-2000:]

    # 累计总数（增量）
    total = stats.get("total_visits", 0) + 1

    stats["visits"] = visits
    stats["total_visits"] = total
    _write_json(STATS_FILE, stats)


def get_visit_stats() -> dict:
    """获取访问统计摘要"""
    stats = _read_json(STATS_FILE)
    visits = stats.get("visits", [])
    total = stats.get("total_visits", 0)

    today_str = date.today().isoformat()
    today_visits = sum(1 for v in visits if v.startswith(today_str))

    return {
        "total_visits": total,
        "today_visits": today_visits,
        "first_visit": visits[0] if visits else None,
        "last_visit": visits[-1] if visits else None,
    }


# ══════════════════════════════════════════════════════════════
# 优化记录持久化
# ══════════════════════════════════════════════════════════════

def persist_optimization(record: dict):
    """
    将一次优化记录持久化到磁盘。

    Args:
        record: 优化记录 dict，包含 experience/role/company/eval_scores/timestamp/use_rag
                注意：parsed 字段（含大段文本）会被精简，仅保留摘要
    """
    saved = {
        "timestamp": record.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "role": record.get("role", ""),
        "company": record.get("company", ""),
        "use_rag": record.get("use_rag", False),
        "experience_preview": (record.get("experience", "") or "")[:120],
        "eval_scores": record.get("eval_scores"),
    }
    # 计算均分
    scores = record.get("eval_scores")
    if scores:
        try:
            saved["avg_score"] = round(
                (float(scores.get("completeness", 0))
                 + float(scores.get("job_match", 0))
                 + float(scores.get("format_quality", 0))) / 3, 1)
        except (ValueError, TypeError):
            saved["avg_score"] = None
    else:
        saved["avg_score"] = None

    data = _read_json(OPTIMIZATIONS_FILE)
    records = data.get("records", [])
    records.append(saved)
    # 最多保留 500 条
    if len(records) > 500:
        records = records[-500:]
    data["records"] = records
    data["total_count"] = len(records)
    _write_json(OPTIMIZATIONS_FILE, data)


def get_optimization_stats() -> dict:
    """获取优化记录统计摘要"""
    data = _read_json(OPTIMIZATIONS_FILE)
    records = data.get("records", [])

    if not records:
        return {
            "total_count": 0,
            "scored_count": 0,
            "avg_score_all": None,
            "latest_score": None,
            "rag_usage_rate": 0,
            "today_count": 0,
        }

    scored = [r for r in records if r.get("avg_score") is not None]
    rag_used = sum(1 for r in records if r.get("use_rag"))

    all_avgs = [r["avg_score"] for r in scored]

    today_str = date.today().isoformat()
    today_count = sum(1 for r in records if r.get("timestamp", "").startswith(today_str))

    return {
        "total_count": len(records),
        "scored_count": len(scored),
        "avg_score_all": round(sum(all_avgs) / len(all_avgs), 1) if all_avgs else None,
        "latest_score": all_avgs[-1] if all_avgs else None,
        "rag_usage_rate": round(rag_used / len(records) * 100) if records else 0,
        "today_count": today_count,
    }


# ══════════════════════════════════════════════════════════════
# LLM 调用统计（从 stats.json 读取，由 migrate_logs.py 写入）
# ══════════════════════════════════════════════════════════════

def log_llm_call_stats(provider: str, model: str, tokens: int, duration_ms: float, success: bool):
    """记录一次 LLM 调用到 stats.json"""
    stats = _read_json(STATS_FILE)
    calls = stats.get("llm_calls", [])
    calls.append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "provider": provider,
        "model": model,
        "tokens": tokens,
        "duration_ms": round(duration_ms, 0),
        "success": success,
    })
    if len(calls) > 2000:
        calls = calls[-2000:]
    stats["llm_calls"] = calls
    _write_json(STATS_FILE, stats)


def get_llm_stats() -> dict:
    """获取 LLM 调用统计摘要"""
    stats = _read_json(STATS_FILE)
    calls = stats.get("llm_calls", [])

    if not calls:
        return {"total_calls": 0, "total_tokens": 0, "avg_duration_ms": 0,
                "success_rate": 0, "providers": {}}

    successful = [c for c in calls if c.get("success", True)]
    total_tokens = sum(c.get("tokens", 0) for c in calls)
    avg_duration = sum(c.get("duration_ms", 0) for c in calls) / len(calls)
    success_rate = round(len(successful) / len(calls) * 100)

    # 各 provider 使用次数
    providers = {}
    for c in calls:
        p = c.get("provider", "unknown")
        providers[p] = providers.get(p, 0) + 1

    return {
        "total_calls": len(calls),
        "total_tokens": total_tokens,
        "avg_duration_ms": round(avg_duration, 0),
        "success_rate": success_rate,
        "providers": providers,
    }


def get_all_stats() -> dict:
    """聚合全部统计数据（供看板使用）"""
    return {
        "visits": get_visit_stats(),
        "optimizations": get_optimization_stats(),
        "llm": get_llm_stats(),
    }
