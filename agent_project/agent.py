"""
=============================================================================
简历优化 Agent · 核心引擎
=============================================================================
手写 Agent Loop：优化 → 自审 → 改进 → 自评 → 输出

与 v1.0（单次 LLM 调用）的核心区别：
  - 多轮迭代：不是一次生成就输出，而是经过"自我审查→改进"的闭环
  - 可解释性：用户能看到 Agent 发现了什么问题、怎么改的
  - 质量内建：自审机制让质量不再完全依赖单次 prompt 的好坏
=============================================================================
"""

import re

from openai import OpenAI

from config import (
    DEEPSEEK_BASE_URL, DEEPSEEK_MODEL, _get_api_key,
    LLM_TEMPERATURE, LLM_MAX_TOKENS, REVIEW_MAX_TOKENS, ASSESS_MAX_TOKENS,
)
from prompts import (
    build_optimize_prompt,
    build_review_prompt,
    build_improve_prompt,
    build_self_assessment_prompt,
    build_synthesize_prompt,
    build_followup_prompt,
    build_interview_questions_prompt,
)
from logger import log_prompt, log_response, log_error as log_llm_error


# ══════════════════════════════════════════════════════════════
# 自定义异常
# ══════════════════════════════════════════════════════════════

class AgentError(Exception):
    """Agent 执行错误，携带用户可理解的提示"""
    def __init__(self, step: str, message: str, user_msg: str):
        super().__init__(message)
        self.step = step       # 哪个步骤出错
        self.user_msg = user_msg  # 给用户看的友好提示


# ══════════════════════════════════════════════════════════════
# LLM 客户端
# ══════════════════════════════════════════════════════════════

class LLMClient:
    """DeepSeek LLM 客户端（MVP 只接 DeepSeek）"""

    def __init__(self):
        api_key = _get_api_key()
        if not api_key:
            raise AgentError(
                "init",
                "未找到 DEEPSEEK_API_KEY",
                "❌ 未配置 API Key，请在 .env 文件中设置 DEEPSEEK_API_KEY。"
            )
        self._client = OpenAI(
            api_key=api_key,
            base_url=DEEPSEEK_BASE_URL,
        )

    @staticmethod
    def _ensure_format(text: str) -> str:
        """
        兜底修复：如果 LLM 输出的板块标记缺少 ### 前缀，自动补上。
        确保下游解析器（section_parser）能正确拆分四个板块。
        """
        if not text:
            return text

        marker_emojis = ["📋 原句", "🔍 问题分析", "✅ 优化版本", "💡 优化理由"]

        for marker in marker_emojis:
            escaped = re.escape(marker)
            # 匹配行首是 marker 但不以 ### 开头的情况
            text = re.sub(
                rf'(?m)^(?!###\s){escaped}\s*$',
                rf'### {marker}',
                text,
            )

        return text

    def generate(
        self,
        prompt: str,
        system_prompt: str = "",
        max_tokens: int = LLM_MAX_TOKENS,
        temperature: float = LLM_TEMPERATURE,
    ) -> str:
        """调用 LLM 生成文本"""
        if not system_prompt:
            system_prompt = (
                "你是一位资深 HR 兼简历优化专家。"
                "请始终用中文回复，严格按照用户要求的格式输出。"
                ""
                "【最高优先级 · 不可违反】"
                "1. 绝不编造任何数据。原文没有的具体数字（用户数、百分比、金额、增长率等），"
                "一律用定性描述（如「显著提升」「有效改善」），禁止估算具体数值。"
                "2. 项目时间和项目角色保留原文不动。"
                "3. 专业技能范围以用户原文为准，不新增用户没提的技能。"
                "4. 如果某个数据原文确实没有但你强烈认为应该补充，"
                "写成「建议补充：[具体什么数据]」让用户自己填，不要替用户编。"
            )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ]

        try:
            # 记录请求日志
            log_prompt("llm", f"model={DEEPSEEK_MODEL} max_tokens={max_tokens}\n\n{prompt[:5000]}")

            response = self._client.chat.completions.create(
                model=DEEPSEEK_MODEL,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content or ""
            # 自动修复缺失的 ### 标题前缀
            content = self._ensure_format(content)

            # 记录响应日志
            log_response("llm", content[:5000])

            return content

        except Exception as e:
            err_text = str(e)

            # 记录错误日志
            log_llm_error("llm", err_text[:500])

            # 分类错误 → 用户友好提示
            if "401" in err_text or "Authentication" in err_text:
                user_msg = "❌ API Key 无效，请检查 .env 文件中的 DEEPSEEK_API_KEY 是否正确。"
            elif "429" in err_text or "rate" in err_text.lower():
                user_msg = "⚠️ API 请求过于频繁，请稍后重试。"
            elif "timeout" in err_text.lower() or "timed out" in err_text.lower():
                user_msg = "⚠️ API 响应超时，请重试。"
            elif "503" in err_text or "overloaded" in err_text.lower():
                user_msg = "⚠️ DeepSeek 服务繁忙，请稍后重试。"
            else:
                user_msg = f"⚠️ LLM 调用失败，请重试。（{err_text[:100]}）"

            raise AgentError("llm_call", err_text[:200], user_msg)


# ══════════════════════════════════════════════════════════════
# Agent 核心
# ══════════════════════════════════════════════════════════════

class ResumeAgent:
    """
    简历优化 Agent。

    工作流：
      1. 第 1 轮优化（基于 STAR 法则 + 目标岗位 + 简历模板）
      2. Agent 自审（挑出具体缺陷）
      3. 第 2 轮改进（只修复自审发现的问题）
      4. 自评总结（定性描述优化重点和效果）
      5. 合成干净简历（将优化条目按模板结构合成为可投递简历）
    """

    def __init__(self):
        self.llm = LLMClient()
        self.round1_output: str = ""   # 第 1 轮优化结果
        self.review_findings: str = "" # 自审发现
        self.round2_output: str = ""   # 第 2 轮改进结果
        self.self_assessment: str = "" # 自评总结
        self.final_resume: str = ""    # 合成后的干净简历

    def run(
        self,
        resume_text: str,
        target_role: str = "",
        target_company: str = "",
        template_mode: str = "builtin",
        custom_template: str = "",
        jd_text: str = "",
        progress_callback=None,
    ) -> dict:
        """
        执行完整的 Agent 优化流程。

        Args:
            resume_text: 简历原文
            target_role: 目标岗位（可选）
            target_company: 目标公司（可选）
            template_mode: "builtin" / "custom" / "none"
            custom_template: 自定义模板文本（mode="custom" 时使用）
            jd_text: 目标 JD 文本（可选，用于匹配度分析）
            progress_callback: 进度回调，接收 (step_name: str, status: str)

        Returns:
            {
                "round1": str,       # 第 1 轮优化
                "review": str,       # 自审发现
                "round2": str,       # 第 2 轮改进（最终版本）
                "assessment": str,   # 自评总结
                "final_resume": str, # 合成后的干净可投递简历
            }
        """
        # ── Step 1：第 1 轮优化 ──
        self._update_progress(progress_callback, "optimize", "running")
        try:
            prompt = build_optimize_prompt(resume_text, target_role, target_company, template_mode, custom_template, jd_text)
            self.round1_output = self.llm.generate(prompt)
            self._update_progress(progress_callback, "optimize", "done")
        except AgentError:
            self._update_progress(progress_callback, "optimize", "error")
            raise

        # ── Step 2：Agent 自审 ──
        self._update_progress(progress_callback, "review", "running")
        try:
            review_prompt = build_review_prompt(self.round1_output, resume_text, jd_text)
            self.review_findings = self.llm.generate(
                review_prompt,
                max_tokens=REVIEW_MAX_TOKENS,
            )
            self._update_progress(progress_callback, "review", "done")
        except AgentError:
            self._update_progress(progress_callback, "review", "error")
            raise

        # ── Step 3：第 2 轮改进 ──
        self._update_progress(progress_callback, "improve", "running")
        try:
            improve_prompt = build_improve_prompt(
                self.round1_output, self.review_findings, resume_text, template_mode, custom_template, jd_text
            )
            self.round2_output = self.llm.generate(improve_prompt)
            self._update_progress(progress_callback, "improve", "done")
        except AgentError:
            self._update_progress(progress_callback, "improve", "error")
            raise

        # ── Step 4：自评总结 + 多维度评分 ──
        self._update_progress(progress_callback, "assess", "running")
        raw_assessment = ""
        scores = {}
        try:
            assess_prompt = build_self_assessment_prompt(
                resume_text, self.round2_output, self.review_findings,
                final_resume=self.final_resume or self.round2_output,
                jd_text=jd_text,
            )
            raw_assessment = self.llm.generate(
                assess_prompt,
                max_tokens=ASSESS_MAX_TOKENS,
            )
            scores = self._parse_scores(raw_assessment)
            self.self_assessment = self._extract_summary(raw_assessment)
            self._update_progress(progress_callback, "assess", "done")
        except AgentError:
            self.self_assessment = "（自评总结生成失败）"
            self._update_progress(progress_callback, "assess", "done")

        # ── Step 5：合成干净简历 ──
        self._update_progress(progress_callback, "synthesize", "running")
        try:
            synthesize_prompt = build_synthesize_prompt(
                self.round2_output, resume_text, template_mode, custom_template, jd_text
            )
            self.final_resume = self.llm.generate(
                synthesize_prompt,
                max_tokens=LLM_MAX_TOKENS,
            )
            self._update_progress(progress_callback, "synthesize", "done")
        except AgentError:
            # 合成失败不影响主流程
            self.final_resume = ""
            self._update_progress(progress_callback, "synthesize", "done")

        return {
            "round1": self.round1_output,
            "review": self.review_findings,
            "round2": self.round2_output,
            "assessment": self.self_assessment,
            "final_resume": self.final_resume,
            "scores": scores,
            "score_raw": raw_assessment,
        }

    def followup(self, user_feedback: str, original_text: str, current_output: str = "", template_mode: str = "builtin", custom_template: str = "", jd_text: str = "") -> dict:
        """
        执行用户追问的针对性修改。

        Args:
            user_feedback: 用户的修改意见
            original_text: 原始简历文本
            current_output: 当前优化版本（用于多轮追问，为空则用实例内部状态）
            template_mode: "builtin" / "custom" / "none"
            custom_template: 自定义模板文本
            jd_text: 目标 JD 文本（可选）

        Returns:
            {"round1": "", "review": "", "round2": new_output, "assessment": "", "final_resume": "", "scores": {}}
        """
        base_output = current_output or self.round2_output or self.round1_output
        prompt = build_followup_prompt(
            base_output,
            user_feedback,
            original_text,
            jd_text,
        )
        new_output = self.llm.generate(prompt)

        # 追问后也合成一份最终简历
        final_resume = ""
        try:
            synthesize_prompt = build_synthesize_prompt(new_output, original_text, template_mode, custom_template, jd_text)
            final_resume = self.llm.generate(
                synthesize_prompt,
                max_tokens=LLM_MAX_TOKENS,
            )
        except AgentError:
            pass

        return {
            "round1": "",
            "review": "",
            "round2": new_output,
            "assessment": f"已根据您的反馈「{user_feedback[:50]}」调整。",
            "final_resume": final_resume,
            "scores": {},
            "score_raw": "",
        }

    def generate_questions(self, resume_text: str, jd_text: str = "") -> str:
        """根据简历生成面试题。返回分类面试题文本。"""
        prompt = build_interview_questions_prompt(resume_text, jd_text)
        return self.llm.generate(prompt)

    @staticmethod
    def _parse_scores(text: str) -> dict:
        """从 LLM 评分输出中提取各维度分数"""
        scores = {}
        # 匹配 "维度名: 分数" 格式（分数在行尾或后跟空格/评语）
        pattern = r'([^\n:：]+?)\s*[:：]\s*(\d{1,3})\s*$'
        for match in re.finditer(pattern, text, re.MULTILINE):
            key = match.group(1).strip()
            val = int(match.group(2))
            # 过滤掉明显不是评分的行（分数需在 0-100 范围）
            if 0 <= val <= 100 and len(key) <= 20:
                scores[key] = val
        return scores

    @staticmethod
    def _extract_summary(raw_text: str) -> str:
        """从评分+总结输出中提取纯文本总结（去掉评分板块）"""
        if not raw_text:
            return raw_text
        # 找到 💬 优化总结 部分
        m = re.search(r'###\s*💬\s*优化总结\s*\n(.*)', raw_text, re.DOTALL)
        if m:
            return m.group(1).strip()
        # 如果没有找到 💬 标记，尝试去掉评分部分
        m = re.search(r'###\s*📊\s*简历评分\s*\n(.*?)(?=###\s*💬)', raw_text, re.DOTALL)
        if m:
            # 评分部分之后的内容
            after = raw_text[m.end():]
            if after.strip():
                return after.strip()
        # 兜底：返回原文（去掉明显的评分行）
        lines = raw_text.split('\n')
        summary_lines = []
        in_scores = True
        for line in lines:
            if '💬' in line or '优化总结' in line:
                in_scores = False
                continue
            if not in_scores:
                summary_lines.append(line)
        result = '\n'.join(summary_lines).strip()
        return result or raw_text

    @staticmethod
    def _update_progress(callback, step: str, status: str):
        """安全调用进度回调"""
        if callback:
            try:
                callback(step, status)
            except Exception:
                pass  # 进度更新失败不影响主流程
