"""
=============================================================================
简历优化助手 · 免费额度 / BYOK 模块
=============================================================================
每个用户每个功能免费使用 FREE_QUOTA_PER_FEATURE 次，超出后需在侧边栏
填入自己的 API Key（BYOK）才能继续使用。

用户识别：客户端 IP（sha256 哈希后存储，不落明文）+ 服务端 JSON 持久化；
IP 不可得时降级为会话级 UUID（刷新页面即重置）。

豁免规则：
  - 当前 provider 为 ollama（本地推理，不消耗 owner 的 API 额度）
  - 用户已在侧边栏填入自己的 API Key（BYOK，仅存 session_state，永不落盘）

并发说明：与 stats.json 一致，写入无文件锁（last-write-wins）。
单进程 Streamlit 下最坏情况是并发点击少记一次，对本应用可接受。
=============================================================================
"""

import hashlib
import uuid
from datetime import datetime
from typing import Tuple

from config import FREE_QUOTA_PER_FEATURE, QUOTA_FILE, LLM_PROVIDER
from utils.stats import _read_json, _write_json

# 计入额度的功能标识
FEATURES = ("resume", "prd")

# 无需 API Key 的本地 provider
_EXEMPT_PROVIDERS = ("ollama",)


# ══════════════════════════════════════════════════════════════
# 用户识别
# ══════════════════════════════════════════════════════════════

def get_user_id() -> str:
    """
    获取当前用户标识（四级回退）：
      1. st.context.headers 的 X-Forwarded-For 首段（Streamlit Cloud / 反代场景）
      2. st.context.ip_address（Streamlit >= 1.45 直连场景；localhost 为 None）
      3. Host 请求头（本地 localhost 直连的稳定标识，避免刷新页面额度重置）
      4. 会话级 UUID（额度降级为会话级，刷新即重置）

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
                # 仅接受字符串（测试环境下该属性可能是 Mock 对象）
                if isinstance(addr, str):
                    ip = addr.strip()
            if not ip and headers:
                # 本地/直连场景拿不到客户端 IP：用 Host 头作稳定标识，
                # 否则每次打开页面都会被当成新用户、额度重置
                host = headers.get("Host", "")
                if isinstance(host, str) and host:
                    ip = "host:" + host
    except Exception:
        ip = ""

    if ip:
        return "ip:" + hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]

    # 会话级回退
    if not st.session_state.get("_quota_session_id"):
        st.session_state["_quota_session_id"] = "sess:" + uuid.uuid4().hex[:16]
    return st.session_state["_quota_session_id"]


# ══════════════════════════════════════════════════════════════
# 额度读写（JSON 持久化）
# ══════════════════════════════════════════════════════════════

def get_used(user_id: str, feature: str) -> int:
    """返回该用户在指定功能上已用的免费次数"""
    data = _read_json(QUOTA_FILE)
    return int(data.get("users", {}).get(user_id, {}).get(feature, 0))


def get_remaining(user_id: str, feature: str) -> int:
    """返回该用户在指定功能上剩余的免费次数"""
    return max(0, FREE_QUOTA_PER_FEATURE - get_used(user_id, feature))


def consume(user_id: str, feature: str) -> int:
    """已用次数 +1 并写盘，返回剩余次数"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = _read_json(QUOTA_FILE)
    users = data.setdefault("users", {})
    record = users.setdefault(user_id, {"first_seen": now})
    record[feature] = int(record.get(feature, 0)) + 1
    record["last_used"] = now
    _write_json(QUOTA_FILE, data)
    return max(0, FREE_QUOTA_PER_FEATURE - record[feature])


# ══════════════════════════════════════════════════════════════
# 会话 / BYOK 助手（依赖 streamlit，保持 llm_client 与 UI 解耦）
# ══════════════════════════════════════════════════════════════

def get_current_provider() -> str:
    """
    获取当前会话选择的 LLM provider。
    优先读会话级的侧边栏选择（多用户隔离），回退到 .env 配置。
    """
    import streamlit as st
    return st.session_state.get("sidebar_llm_provider") or LLM_PROVIDER


def get_byok_key(provider: str = "") -> str:
    """读取用户在侧边栏填入的自有 API Key（仅存 session_state）"""
    import streamlit as st
    provider = provider or get_current_provider()
    if provider in _EXEMPT_PROVIDERS:
        return ""
    return (st.session_state.get(f"byok_{provider}") or "").strip()


def is_quota_exempt() -> bool:
    """是否豁免额度：本地 ollama 或用户已填自己的 Key"""
    provider = get_current_provider()
    return provider in _EXEMPT_PROVIDERS or bool(get_byok_key(provider))


def check_quota(feature: str) -> Tuple[bool, str]:
    """
    门禁检查。返回 (是否放行, 拦截提示语)。
    豁免或还有剩余次数 → (True, "")。
    """
    if is_quota_exempt():
        return True, ""
    if get_remaining(get_user_id(), feature) > 0:
        return True, ""
    return False, (
        f"免费额度已用完（{FREE_QUOTA_PER_FEATURE} 次）。"
        "请在左侧边栏填入您自己的 API Key 继续使用，或切换到本地 Ollama 模型。"
    )


def consume_quota(feature: str) -> None:
    """扣减一次免费额度；豁免场景（BYOK / ollama）不扣"""
    if is_quota_exempt():
        return
    consume(get_user_id(), feature)


def get_session_llm_client(provider: str = ""):
    """
    获取当前会话的 LLM 客户端。
    用户填了 BYOK key 时走独立实例（不进全局单例，防跨会话 key 泄漏）。
    """
    from llm_client import get_llm_client
    provider = provider or get_current_provider()
    return get_llm_client(provider, api_key=get_byok_key(provider))


# ══════════════════════════════════════════════════════════════
# 统计（供数据看板）
# ══════════════════════════════════════════════════════════════

def get_quota_stats() -> dict:
    """返回额度使用总览：独立用户数 + 各功能累计免费使用次数"""
    users = _read_json(QUOTA_FILE).get("users", {})
    stats = {"total_users": len(users)}
    for feature in FEATURES:
        stats[f"total_{feature}"] = sum(
            int(rec.get(feature, 0)) for rec in users.values()
        )
    return stats
