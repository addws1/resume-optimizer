"""
=============================================================================
简历优化 Agent · 免费额度 / BYOK 模块
=============================================================================
每个 IP 每天免费使用 FREE_QUOTA_PER_DAY 次，超出后需填入自己的 API Key
（BYOK）才能继续使用。

设计原则：
  - 每日重置（非终身制），适合 Demo 场景——面试官点开就能试
  - IP sha256 哈希存储，不落明文
  - IP 不可得时降级为会话级 UUID（刷新重置）
  - BYOK Key 仅存 session_state，不落盘
=============================================================================
"""

import hashlib
import json
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Tuple

from config import FREE_QUOTA_PER_DAY, QUOTA_FILE


# ══════════════════════════════════════════════════════════════
# JSON 读写（内联，不依赖外部模块）
# ══════════════════════════════════════════════════════════════

def _read_json(filepath: Path) -> dict:
    """安全读取 JSON 文件，不存在或损坏则返回空 dict"""
    if not filepath.exists():
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _write_json(filepath: Path, data: dict):
    """安全写入 JSON 文件"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ══════════════════════════════════════════════════════════════
# 用户识别
# ══════════════════════════════════════════════════════════════

def get_user_id() -> str:
    """
    获取当前用户标识（四级回退）：
      1. st.context.headers 的 X-Forwarded-For 首段（Streamlit Cloud / 反代）
      2. st.context.ip_address（直连场景）
      3. Host 请求头（本地直连的稳定标识，避免刷新重置）
      4. 会话级 UUID（最终降级）

    IP 只存 sha256 前 16 位哈希，不落明文。
    """
    import streamlit as st

    ip = ""
    try:
        if hasattr(st, "context"):
            headers = getattr(st.context, "headers", None)
            if headers:
                xff = headers.get("X-Forwarded-For", "")
                if isinstance(xff, str) and xff:
                    ip = xff.split(",")[0].strip()
            if not ip:
                addr = getattr(st.context, "ip_address", None)
                if isinstance(addr, str):
                    ip = addr.strip()
            if not ip and headers:
                host = headers.get("Host", "")
                if isinstance(host, str) and host:
                    ip = "host:" + host
    except Exception:
        ip = ""

    if ip:
        return "ip:" + hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]

    # 会话级回退
    import streamlit as st
    if not st.session_state.get("_quota_session_id"):
        st.session_state["_quota_session_id"] = "sess:" + uuid.uuid4().hex[:16]
    return st.session_state["_quota_session_id"]


# ══════════════════════════════════════════════════════════════
# 每日额度读写
# ══════════════════════════════════════════════════════════════

def _today_key() -> str:
    """返回今天的日期字符串，用于按日分组额度"""
    return date.today().isoformat()  # "2026-07-26"


def get_used_today(user_id: str) -> int:
    """返回该用户今天已用的免费次数"""
    data = _read_json(QUOTA_FILE)
    today = _today_key()
    return int(data.get("daily", {}).get(today, {}).get(user_id, 0))


def get_remaining(user_id: str) -> int:
    """返回该用户今天剩余的免费次数"""
    return max(0, FREE_QUOTA_PER_DAY - get_used_today(user_id))


def consume(user_id: str) -> int:
    """已用次数 +1 并写盘，返回剩余次数"""
    today = _today_key()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = _read_json(QUOTA_FILE)
    daily = data.setdefault("daily", {})
    today_data = daily.setdefault(today, {})
    today_data[user_id] = today_data.get(user_id, 0) + 1

    # 记录最后使用时间
    users = data.setdefault("users", {})
    user_record = users.setdefault(user_id, {"first_seen": now})
    user_record["last_used"] = now
    user_record["total_used"] = user_record.get("total_used", 0) + 1

    _write_json(QUOTA_FILE, data)
    return max(0, FREE_QUOTA_PER_DAY - today_data[user_id])


# ══════════════════════════════════════════════════════════════
# BYOK 助手
# ══════════════════════════════════════════════════════════════

BYOK_SESSION_KEY = "_byok_api_key"


def get_byok_key() -> str:
    """读取用户在界面填入的自有 API Key（仅存 session_state，不落盘）"""
    import streamlit as st
    return (st.session_state.get(BYOK_SESSION_KEY) or "").strip()


def is_quota_exempt() -> bool:
    """用户是否豁免额度（填了自己的 API Key）"""
    return bool(get_byok_key())


# ══════════════════════════════════════════════════════════════
# 门禁
# ══════════════════════════════════════════════════════════════

def check_quota() -> Tuple[bool, str]:
    """
    额度门禁检查。

    Returns:
        (是否放行, 拦截提示语)
    """
    if is_quota_exempt():
        return True, ""

    user_id = get_user_id()
    remaining = get_remaining(user_id)
    if remaining > 0:
        return True, ""

    return False, (
        f"今日免费次数已用完（每日 {FREE_QUOTA_PER_DAY} 次）。"
        "请填入您自己的 DeepSeek API Key 继续使用，或明天再来。"
    )


def consume_quota() -> None:
    """扣减一次免费额度；BYOK 用户不扣"""
    if is_quota_exempt():
        return
    consume(get_user_id())


# ══════════════════════════════════════════════════════════════
# 清理：自动删除 30 天前的每日记录，防止 JSON 膨胀
# ══════════════════════════════════════════════════════════════

def _cleanup_old_daily_data():
    """删除超过 30 天的每日额度记录（在每次读写时惰性调用）"""
    data = _read_json(QUOTA_FILE)
    daily = data.get("daily", {})
    if not daily:
        return

    from datetime import timedelta
    cutoff = (date.today() - timedelta(days=30)).isoformat()
    stale_keys = [k for k in daily if k < cutoff]

    if stale_keys:
        for k in stale_keys:
            del daily[k]
        _write_json(QUOTA_FILE, data)
