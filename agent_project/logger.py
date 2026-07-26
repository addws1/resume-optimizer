"""
=============================================================================
简历优化 Agent · 日志模块
=============================================================================
记录每次 LLM 调用的 prompt 和 response，方便排查优化效果问题。

日志位置：agent_project/logs/
格式：纯文本，按 session 分文件，自动清理超过 20 个的旧 session。
=============================================================================
"""

import os
import re
from datetime import datetime
from pathlib import Path

# ── 日志目录 ──
LOG_DIR = Path(__file__).parent / "logs"

# 最多保留的 session 数
MAX_SESSIONS = 20

# ── 当前 session ──
_session_id: str | None = None


def _init_session() -> str:
    """初始化当前 session，返回 session_id"""
    global _session_id
    if _session_id is None:
        _session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        LOG_DIR.mkdir(exist_ok=True)
        _cleanup_old_sessions()
    return _session_id


def _cleanup_old_sessions():
    """保留最近 MAX_SESSIONS 个 session，删除更早的"""
    try:
        files = sorted(LOG_DIR.glob("session_*.log"), key=os.path.getmtime, reverse=True)
        for f in files[MAX_SESSIONS:]:
            f.unlink(missing_ok=True)
    except Exception:
        pass


def _session_path() -> Path:
    """获取当前 session 的日志文件路径"""
    return LOG_DIR / f"session_{_init_session()}.log"


def _mask_api_key(text: str) -> str:
    """遮蔽 API Key，防止日志泄露"""
    # 匹配 sk- 开头的 key 模式
    return re.sub(r'sk-[a-zA-Z0-9]{20,}', 'sk-***MASKED***', text)


def _write(header: str, content: str):
    """追加一条日志记录"""
    path = _session_path()
    timestamp = datetime.now().strftime("%H:%M:%S")
    safe_content = _mask_api_key(content)
    # 截断过长内容
    if len(safe_content) > 8000:
        safe_content = safe_content[:8000] + "\n\n... [截断，完整内容过长]"

    with open(path, "a", encoding="utf-8") as f:
        f.write(f"\n{'═' * 60}\n")
        f.write(f"  {header}  |  {timestamp}\n")
        f.write(f"{'═' * 60}\n")
        f.write(safe_content)
        f.write(f"\n{'─' * 60}\n")


def log_prompt(step: str, prompt: str):
    """记录发送给 LLM 的 prompt"""
    _write(f"📤 PROMPT [{step}]", prompt)


def log_response(step: str, response: str):
    """记录 LLM 返回的 response"""
    _write(f"📥 RESPONSE [{step}]", response)


def log_error(step: str, error: str):
    """记录调用异常"""
    _write(f"❌ ERROR [{step}]", error)


def current_log_path() -> str:
    """返回当前日志文件路径，供 UI 展示"""
    return str(_session_path())
