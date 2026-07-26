# 📄 简历优化助手 · Resume Optimizer

AI 驱动的简历优化工具 —— 从单次 LLM 优化到 Agent 自审闭环，两个版本展示产品迭代思路。

**面向 AI 产品实习生求职作品集展示。**

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.37+-red)](https://streamlit.io/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek%20v4-green)](https://platform.deepseek.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 🗺 项目总览

| | v1.0（RAG 增强版） | v2.0（Agent 自审闭环） |
|---|---|---|
| 目录 | `resume_optimizer_v1/` | `agent_project/` |
| 启动 | `streamlit run resume_optimizer.py` | `streamlit run app.py` |
| 核心理念 | RAG 知识增强 + 多维度质量评分 | Agent 自我审查 → 改进 → 评分 → 合成 |
| LLM 调用 | 单次调用 | 5 步 Agent Loop |
| 特色功能 | PRD 生成、数据看板、用户调研 | 面试题生成、多轮追问、BYOK |
| 适用场景 | 深度定制、求职准备全流程 | 快速优化、Demo 链接放简历上 |

---

## 🚀 快速开始

### 前提条件
- Python 3.10+
- DeepSeek API Key（[免费注册获取](https://platform.deepseek.com/)）

### v2.0 Agent 版（推荐）

```bash
cd agent_project
pip install streamlit openai python-dotenv python-docx PyMuPDF
cp .env.example .env   # 编辑填入 DEEPSEEK_API_KEY=sk-xxx
streamlit run app.py
```

浏览器打开 `http://localhost:8502`，上传简历或粘贴文本即可。

### v1.0 经典版

```bash
cd resume_optimizer_v1
pip install -r requirements.txt
# 编辑 .env 填入 DEEPSEEK_API_KEY
streamlit run resume_optimizer.py
```

---

## 🧠 v2.0 Agent 自审闭环（核心亮点）

v1.0 是"一次 LLM 调用出结果"，质量完全依赖 prompt 好坏。v2.0 引入了 **Agent 自我审查循环**：

```
原始简历 → 第 1 轮优化（STAR 法则）
    → Agent 自审（像 HR 一样挑毛病）
    → 第 2 轮改进（只修自审发现的问题）
    → 多维度自评（STAR 完整度/量化率/动词力度/关键词密度/简洁度/JD 匹配度 + 综合分）
    → 合成干净简历（可直接投递的 Markdown/DOCX）
```

每次优化 = 5 次 LLM 调用，但质量远高于单次调用。

### v2.0 其他特性

- **每日免费额度**：每 IP 每天 10 次免费优化（Demo 友好）
- **BYOK**：填入自己的 DeepSeek API Key 不限次数，Key 仅存会话内存
- **多轮追问**：对结果不满意可以反复修改
- **面试题生成**：根据优化后的简历自动出题
- **多模板支持**：内置模板 / 自定义模板 / 保留原结构
- **LLM 指标面板**：每次优化展示 token 消耗、耗时、成本

详细架构见 [agent_project/](agent_project/)。

---

## 📦 v1.0 经典版功能

| 功能模块 | 说明 |
|---|---|
| **简历优化** | 粘贴经历 → RAG 知识增强 → 四栏输出（原句/问题/优化/理由） |
| **PRD 导出** | 基于项目经历自动生成标准化产品需求文档 |
| **效果评估** | 三维度打分 + 历史趋势折线图 + CSV 导出 |
| **用户调研** | 问卷录入 / NPS 评分 / 痛点汇总报告 |
| **数据看板** | 访问量 / 优化次数 / 评分均值 / LLM 调用统计 |
| **免费额度 + BYOK** | 每功能免费 3 次（终身），超出可填自己的 Key |
| **多模型支持** | DeepSeek / Ollama 本地 / 通义千问 一键切换 |
| **RAG 多路召回** | 向量语义 + TF-IDF 关键词双路检索 + 重排序 |

详细架构见 [resume_optimizer_v1/README.md](resume_optimizer_v1/README.md)。

---

## 🏗 技术架构演进

```
v1.0:  用户输入 → RAG 检索 → 单次 LLM 优化 → 输出
                         ↑
                    JD 知识库（Chroma）

v2.0:  用户输入 → 第1轮优化 → Agent自审 → 第2轮改进 → 自评 → 合成
                   ↑            ↑           ↑          ↑       ↑
              5 次 LLM 调用（每步独立 prompt + 独立指标追踪）
```

### 共用技术栈

| 层级 | 技术 |
|---|---|
| 界面 | Streamlit |
| LLM | DeepSeek API（OpenAI 兼容协议） |
| 文件解析 | PyMuPDF（PDF）+ python-docx（DOCX），v2.1 新增三级 PDF 回退 + 五级编码回退 |
| 日志 | Python logging + RotatingFileHandler |
| 部署 | Streamlit Cloud（免费） |

---

## 🔒 数据安全

- **所有数据本地存储**，不上传云端（除 LLM API 调用外）
- **API Key 保护**：.env 已 gitignore，BYOK Key 仅存会话内存、永不落盘
- **用户识别匿名化**：IP sha256 哈希存储，不保存明文 IP
- **日志脱敏**：API Key 自动遮蔽（`sk-***MASKED***`）

---

## 📁 仓库结构

```
resume-optimizer/
├── agent_project/               ← v2.0 Agent 自审闭环
│   ├── app.py                   ← Streamlit 主页面
│   ├── agent.py                 ← Agent 核心引擎（5 步闭环）
│   ├── prompts.py               ← 全部 prompt 模板
│   ├── parser.py                ← 文件解析（PDF/DOCX + 编码回退）
│   ├── section_parser.py        ← LLM 输出板块解析
│   ├── docx_gen.py              ← DOCX 生成
│   ├── quota.py                 ← 免费额度 + BYOK
│   ├── config.py                ← 配置中心
│   ├── logger.py                ← 日志模块
│   └── .env.example             ← 配置模板
│
├── resume_optimizer_v1/         ← v1.0 RAG 增强版
│   ├── resume_optimizer.py      ← 主入口（路由 + 侧边栏）
│   ├── llm_client.py            ← LLM 抽象层（3 种后端）
│   ├── rag_core.py              ← RAG 核心（双 Embedding）
│   ├── ui/                      ← 五个 Tab 页面
│   ├── utils/                   ← 工具模块（日志/文件/导出/评估/统计/额度）
│   └── docs/                    ← 设计文档
│
├── docs/                        ← 共享文档
│   └── eval-materials/          ← 评估材料
│
├── .gitignore
└── README.md                    ← 本文件
```

---

## 📝 License

MIT — 可自由用于个人学习和求职展示。
