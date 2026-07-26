"""
=============================================================================
简历优化 Agent · 板块解析器（共享模块）
=============================================================================
app.py 和 docx_gen.py 的统一解析入口，支持多种 Markdown/纯文本格式变体。

支持的标题格式：
  - ### 📋 原句          （标准格式）
  - ## 📋 原句           （二级标题）
  - 📋 原句              （纯文本，无 # 前缀）
  - **📋 原句**          （粗体包裹）
  - 📋 原句：            （尾部带冒号）
  - ### 📋 原句\n        （尾随空白）
=============================================================================
"""

import re

# ── 板块标记：emoji+关键字 → 内部 key ──
SECTION_MARKERS = [
    ("📋 原句", "original"),
    ("🔍 问题分析", "issue"),
    ("✅ 优化版本", "optimized"),
    ("💡 优化理由", "reason"),
]

# ── 标题行最大长度（超过此长度认为是正文误匹配）──
MAX_HEADER_LEN = 80


def _strip_markdown_prefix(line: str) -> str:
    """
    剥掉行首的 Markdown 标题标记（#、##、###、####、** 等），
    返回清洗后的纯文本标题内容。
    """
    stripped = line.strip()
    # 去掉 Markdown 标题前缀（# 后面可选空格）
    cleaned = re.sub(r'^#{1,4}\s*', '', stripped)
    # 去掉首尾的 ** 粗体标记
    cleaned = cleaned.strip('*').strip()
    # 去掉尾部冒号（中英文）
    cleaned = cleaned.rstrip('：:').strip()
    return cleaned


def _match_section(line: str) -> str | None:
    """
    判断一行是否为板块标题，是则返回对应的内部 key（original/issue/optimized/reason），
    否则返回 None。
    """
    stripped = line.strip()
    if len(stripped) > MAX_HEADER_LEN:
        return None

    cleaned = _strip_markdown_prefix(line)

    if not cleaned:
        return None

    for marker, key in SECTION_MARKERS:
        if cleaned == marker:
            return key
        # 也匹配 "📋 原句" 后跟空格或冒号的情况
        if cleaned.startswith(marker) and cleaned[len(marker):].strip() in ('', '：', ':'):
            return key

    return None


def parse_sections(text: str) -> dict:
    """
    将 LLM 输出文本按四个板块标题拆分为字典。

    Returns:
        {"original": str, "issue": str, "optimized": str, "reason": str}
    """
    sections = {"original": "", "issue": "", "optimized": "", "reason": ""}
    current_key: str | None = None

    for line in text.split("\n"):
        matched_key = _match_section(line)
        if matched_key:
            current_key = matched_key
            continue

        if current_key and current_key in sections:
            sections[current_key] += line + "\n"

    result = {k: v.strip() for k, v in sections.items()}

    # 兜底：如果四个板块全空，给 original 赋值全文
    if all(not v for v in result.values()):
        result["original"] = text.strip()

    return result


def parse_sections_with_titles(text: str) -> list:
    """
    将 LLM 输出文本拆分为 (标题, 内容) 列表，供 DOCX 生成使用。

    Returns:
        [(title: str, content: str), ...]
    """
    sections: list = []
    current_title = ""
    current_body: list[str] = []

    for line in text.split("\n"):
        matched_key = _match_section(line)
        if matched_key:
            # 保存上一段
            if current_body:
                sections.append((current_title, "\n".join(current_body)))
            # 用原始行的清洗版本作为标题
            current_title = _strip_markdown_prefix(line)
            current_body = []
        else:
            if current_title:  # 只有命中过标题才收集
                current_body.append(line)

    # 保存最后一段
    if current_body and current_title:
        sections.append((current_title, "\n".join(current_body)))

    # 兜底：如果没识别到任何板块，全部内容作为"优化内容"
    if not sections and text.strip():
        sections.append(("优化内容", text.strip()))

    return sections
