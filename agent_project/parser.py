"""
=============================================================================
简历优化 Agent · 文件解析模块
=============================================================================
支持 PDF（PyMuPDF）和 DOCX（python-docx）的文本提取。
=============================================================================
"""

from pathlib import Path
from typing import Optional, Tuple


class ParseError(Exception):
    """文件解析错误，携带用户可理解的提示"""
    def __init__(self, message: str, user_msg: str):
        super().__init__(message)
        self.user_msg = user_msg  # 给用户看的友好提示


def parse_resume_file(file_path: str) -> Tuple[str, str, Optional[str]]:
    """
    解析简历文件，返回 (文本内容, 文件类型标签, 模板路径)。

    Args:
        file_path: PDF 或 DOCX 文件路径

    Returns:
        (extracted_text, label, template_path)
        - label 如 "PDF" 或 "DOCX"
        - template_path: DOCX 文件返回原始路径（用于模板化生成），PDF 返回 None

    Raises:
        ParseError: 解析失败，携带用户友好提示
    """
    path = Path(file_path)
    ext = path.suffix.lower()

    if ext == ".pdf":
        return _parse_pdf(path)
    elif ext == ".docx":
        return _parse_docx(path)
    else:
        raise ParseError(
            f"不支持的文件格式: {ext}",
            f"不支持的文件格式（{ext}），请上传 PDF 或 DOCX 文件。"
        )


def _parse_pdf(path: Path) -> Tuple[str, str, None]:
    """解析 PDF 文件，返回 (text, "PDF", None)"""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        raise ParseError(
            "PyMuPDF 未安装",
            "PDF 解析组件未安装，请运行: pip install PyMuPDF"
        )

    try:
        doc = fitz.open(str(path))
        text_parts = []
        for page in doc:
            text = page.get_text()
            if text.strip():
                text_parts.append(text.strip())

        doc.close()

        if not text_parts:
            raise ParseError(
                "PDF 无可提取文本",
                "❌ 无法解析文件：PDF 可能是图片扫描件，没有可提取的文字。"
                "请尝试直接粘贴简历文本。"
            )

        full_text = "\n\n".join(text_parts)
        return full_text, "PDF", None

    except ParseError:
        raise
    except Exception as e:
        raise ParseError(
            f"PDF 解析异常: {str(e)}",
            f"❌ PDF 文件解析失败，文件可能已损坏。请尝试直接粘贴简历文本。"
        )


def _parse_docx(path: Path) -> Tuple[str, str, str]:
    """解析 DOCX 文件，返回 (text, "DOCX", template_path)"""
    try:
        from docx import Document
    except ImportError:
        raise ParseError(
            "python-docx 未安装",
            "DOCX 解析组件未安装，请运行: pip install python-docx"
        )

    try:
        doc = Document(str(path))
        text_parts = []

        for para in doc.paragraphs:
            text = para.text.strip()
            if text:
                text_parts.append(text)

        # 也提取表格中的文字
        for table in doc.tables:
            for row in table.rows:
                row_text = []
                for cell in row.cells:
                    if cell.text.strip():
                        row_text.append(cell.text.strip())
                if row_text:
                    text_parts.append(" | ".join(row_text))

        if not text_parts:
            raise ParseError(
                "DOCX 无内容",
                "❌ DOCX 文件似乎没有内容，请检查文件是否正确。"
            )

        full_text = "\n".join(text_parts)
        return full_text, "DOCX", str(path)

    except ParseError:
        raise
    except Exception as e:
        raise ParseError(
            f"DOCX 解析异常: {str(e)}",
            f"❌ DOCX 文件解析失败，文件可能已损坏。请尝试直接粘贴简历文本。"
        )
