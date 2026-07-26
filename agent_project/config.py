"""
=============================================================================
简历优化 Agent · 配置文件
=============================================================================
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env（确保在任意启动方式下都能读到环境变量）
_env_path = Path(__file__).parent / ".env"
load_dotenv(_env_path)


def _get_secret(name: str, default: str = "") -> str:
    """
    读取配置值，优先级：环境变量 > st.secrets > 默认值。

    本地开发用 .env（通过 load_dotenv 注入环境变量），
    Streamlit Cloud 用 Secrets 面板（环境变量不一定注入，需直接读 st.secrets）。
    """
    val = os.getenv(name, "")
    if val:
        return val
    try:
        import streamlit as st
        # 直接用 [] 访问，KeyError 明确表示未配置；
        # 不用 .get() 避免静默返回空串
        return st.secrets[name]
    except KeyError:
        return default
    except Exception as e:
        # 其他异常（如 secrets.toml 格式错误）用醒目的方式暴露
        import streamlit as st
        st.error(f"读取 Secrets 失败（{name}）：{e}")
        return default


# ── 路径 ──
PROJECT_DIR = Path(__file__).parent
OUTPUT_DIR = PROJECT_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# ── DeepSeek API ──
# 延迟读取：不在模块导入时求值，避免 Streamlit Cloud 上 st.secrets 尚未初始化
def _get_api_key() -> str:
    return _get_secret("DEEPSEEK_API_KEY")

DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_MODEL = "deepseek-v4-pro"   # DeepSeek 2026 最新模型名

# ── LLM 参数 ──
LLM_TEMPERATURE = 0.3       # 简历优化需要一致性，不宜过高
LLM_MAX_TOKENS = 8192       # 四栏输出 + 模板 + 反造假规则，需要足够空间
REVIEW_MAX_TOKENS = 2048    # 自审输出较短
ASSESS_MAX_TOKENS = 2048   # 自评总结 + 多维度评分

# ── 文件上传 ──
MAX_FILE_SIZE_MB = 10
ALLOWED_EXTENSIONS = ["pdf", "docx"]
