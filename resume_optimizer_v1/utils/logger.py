"""
=============================================================================
简历优化助手 · 本地日志模块
=============================================================================
记录 LLM 调用、知识库操作、报错堆栈，日志按天轮转。
所有日志保存至 data/logs/ 目录，方便排查问题和审计。
=============================================================================
"""

import logging
import os
import traceback
from datetime import datetime
from pathlib import Path
from logging.handlers import RotatingFileHandler

from config import LOG_DIR


# ══════════════════════════════════════════════════════════════
# 日志格式 & 级别
# ══════════════════════════════════════════════════════════════
LOG_FORMAT = (
    "[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s"
)
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 单文件最大 5MB，保留 5 个历史文件
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5


def _build_log_path(name: str) -> Path:
    """根据日志名称构建完整路径"""
    today = datetime.now().strftime("%Y%m%d")
    safe_name = name.replace(" ", "_").lower()
    return LOG_DIR / f"{safe_name}_{today}.log"


def get_logger(name: str = "resume_optimizer") -> logging.Logger:
    """
    获取一个命名的 logger 实例。

    特性：
    - 自动按天分割日志文件
    - 单文件超过 5MB 自动轮转
    - 同时输出到控制台和文件
    - 首次调用时自动创建日志目录
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # ── 文件 handler（RotatingFileHandler 自动轮转）──
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_path = _build_log_path(name)
    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(file_handler)

    # ── 控制台 handler ──
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))
    logger.addHandler(console_handler)

    return logger


# ══════════════════════════════════════════════════════════════
# 便捷函数
# ══════════════════════════════════════════════════════════════

# 全局默认 logger
_log = get_logger("resume_optimizer")


def log_llm_call(provider: str, model: str, prompt_len: int,
                 token_count: int = 0, duration_ms: float = 0,
                 success: bool = True, error: str = ""):
    """
    记录一次 LLM 调用。
    用于审计 API 用量、排查异常调用。
    """
    status = "✓" if success else "✗"
    msg = (
        f"LLM调用 | {status} provider={provider} model={model} "
        f"prompt_len={prompt_len} tokens={token_count} "
        f"duration={duration_ms:.0f}ms"
    )
    if error:
        msg += f" error={error}"
    _log.info(msg)


def log_kb_operation(action: str, doc_count: int = 0,
                     doc_name: str = "", detail: str = ""):
    """记录知识库操作（导入/删除/清空/检索）"""
    parts = [f"知识库操作 | action={action}"]
    if doc_count:
        parts.append(f"count={doc_count}")
    if doc_name:
        parts.append(f"doc={doc_name}")
    if detail:
        parts.append(f"detail={detail}")
    _log.info(" ".join(parts))


def log_error(module: str, error: Exception, context: str = ""):
    """
    记录异常及其完整堆栈。
    用于排查运行时崩溃问题。
    """
    tb = traceback.format_exc()
    _log.error(
        f"异常 | module={module} type={type(error).__name__} "
        f"msg={str(error)[:200]} context={context}\n{tb}"
    )


def log_info(msg: str):
    """通用 info 日志"""
    _log.info(msg)


def log_debug(msg: str):
    """通用 debug 日志"""
    _log.debug(msg)


def log_warning(msg: str):
    """通用 warning 日志"""
    _log.warning(msg)
