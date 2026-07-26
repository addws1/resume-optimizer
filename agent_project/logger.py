"""
=============================================================================
简历优化 Agent · 日志模块（v2.1）
=============================================================================
Python logging + RotatingFileHandler，取代旧的手写文件写入方案。

特性：
  - RotatingFileHandler 自动轮转（5MB × 5 备份），不再需要手动清理
  - 标准日志级别：DEBUG / INFO / WARNING / ERROR
  - 完整 traceback 支持（logger.exception 自动记录堆栈）
  - API Key 自动脱敏
  - 同时输出到控制台（Streamlit Cloud 可见）
  - 保持旧 API 兼容：log_prompt / log_response / log_error / current_log_path
=============================================================================
"""

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

# ── 路径 & 参数 ──
LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "agent.log"
LOG_MAX_BYTES = 5 * 1024 * 1024   # 5MB 触发轮转
LOG_BACKUP_COUNT = 5               # 保留 5 个备份

# ── 构建 logger ──
_logger = logging.getLogger("resume_agent")
_logger.setLevel(logging.DEBUG)

# 避免 Streamlit 的 rerun 导致重复添加 handler
if not _logger.handlers:
    LOG_DIR.mkdir(exist_ok=True)

    # ── 文件 handler（UTF-8，自动轮转）──
    fh = RotatingFileHandler(
        str(LOG_FILE),
        maxBytes=LOG_MAX_BYTES,
        backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))
    _logger.addHandler(fh)

    # ── 控制台 handler（仅 WARNING+，避免刷屏）──
    ch = logging.StreamHandler()
    ch.setLevel(logging.WARNING)
    ch.setFormatter(logging.Formatter(
        "%(levelname)s | %(message)s"
    ))
    _logger.addHandler(ch)


# ══════════════════════════════════════════════════════════════
# API Key 脱敏
# ══════════════════════════════════════════════════════════════

def _mask_api_key(text: str) -> str:
    """遮蔽 sk- 开头的 API Key"""
    return re.sub(r'sk-[a-zA-Z0-9]{20,}', 'sk-***MASKED***', text)


def _truncate(text: str, max_len: int = 4000) -> str:
    """截断过长内容，超出部分标注"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"\n\n... [截断 {len(text) - max_len} 字符]"


# ══════════════════════════════════════════════════════════════
# 公开 API（保持旧接口兼容）
# ══════════════════════════════════════════════════════════════

def log_prompt(step: str, prompt: str):
    """记录发送给 LLM 的 prompt"""
    safe = _mask_api_key(prompt)
    _logger.info(f"[PROMPT {step}]\n{_truncate(safe)}")


def log_response(step: str, response: str):
    """记录 LLM 返回的 response"""
    _logger.info(f"[RESPONSE {step}]\n{_truncate(response)}")


def log_error(step: str, error: str):
    """记录调用异常（含完整 traceback）"""
    _logger.error(f"[ERROR {step}] {error[:1000]}", exc_info=True)


def log_metrics(step: str, metrics: dict):
    """记录 LLM 调用指标：token 分布、耗时、成本"""
    _logger.info(
        f"[METRICS {step}] "
        f"in={metrics.get('prompt_tokens', 0)} "
        f"out={metrics.get('completion_tokens', 0)} "
        f"reason={metrics.get('reasoning_tokens', 0)} "
        f"total={metrics.get('total_tokens', 0)} "
        f"time={metrics.get('elapsed_seconds', 0):.1f}s "
        f"cost=${metrics.get('cost_usd', 0):.6f}"
    )


def current_log_path() -> str:
    """返回当前日志文件路径"""
    return str(LOG_FILE)
