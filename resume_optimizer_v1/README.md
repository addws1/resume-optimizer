# 📄 简历优化助手 · Resume Optimizer

AI 驱动的简历优化工具 —— 输入项目经历，自动输出 STAR 法则优化版 + 质量评分 + PRD 需求文档。

**面向求职作品集展示** · 适合 AI 产品实习生 / Python 后端岗位投递。

[![Python](https://img.shields.io/badge/Python-3.10+-blue)](https://www.python.org/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.37+-red)](https://streamlit.io/)
[![DeepSeek](https://img.shields.io/badge/LLM-DeepSeek-green)](https://platform.deepseek.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow)](LICENSE)

---

## 🎯 解决什么问题

写简历时最常见的痛点：

> "项目经历写成了流水账，不知道怎么改成 HR 想看的版本。"

这个工具做的事情：
- 你粘贴原始经历 → AI 用 **STAR 法则** 重写，每条给出"原句 → 问题分析 → 优化版 → 优化理由"
- 上传目标岗位的 JD 文档作为**知识库** → AI 参考行业规范来优化，不是瞎编
- 自动给优化结果**打分**（完整性 / 匹配度 / 格式规范度），不是"优化完就完了"
- 一键生成配套 **PRD 需求文档**、导出 CSV 评估对比表

---

## 📸 界面预览

> 运行 `deploy.ps1` 后浏览器打开 `http://localhost:8501`

| 功能 | 说明 |
|------|------|
| **简历优化** | 粘贴经历 → RAG 知识增强 → 四栏输出（原句/问题/优化/理由） |
| **PRD 导出** | 基于项目经历自动生成标准化产品需求文档 |
| **效果评估** | 三维度打分卡片 + 历史趋势折线图 + CSV 导出 |
| **用户调研** | 问卷录入 / NPS 评分 / 痛点汇总报告 |
| **数据看板** | 访问量 / 优化次数 / 评分均值 / LLM 调用统计 / 独立用户数，数据文件持久化 |
| **免费额度 + BYOK** | 每用户每功能免费 3 次；超出后可填入自己的 API Key 无限使用（本地 Ollama 不限） |

---

## 🚀 快速开始

### 前提条件
- Python 3.10+
- DeepSeek API Key（[免费注册获取](https://platform.deepseek.com/)）

### 一键启动（Windows）

```powershell
.\deploy.ps1
```

脚本会自动完成：检测环境 → 安装依赖 → 检查配置 → 启动应用。

### 手动启动

```bash
# 1. 安装依赖
pip install -r requirements_resume.txt

# 2. 配置 API Key（编辑 .env 文件）
#    DEEPSEEK_API_KEY=sk-xxxxxxxx

# 3. 启动
streamlit run resume_optimizer.py
```

---

## 🧱 项目架构

```
resume_optimizer.py          ← 主入口：页面路由 + CSS + 侧边栏（~430行）
    │
    ├── config.py            ← 全局配置中心（路径/密钥/模型参数/chunk策略）
    ├── llm_client.py        ← LLM 抽象层（DeepSeek / Ollama / 通义千问 一键切换）
    ├── rag_core.py          ← RAG 核心（双 Embedding + 多路召回 + 重排序）
    │
    ├── ui/                  ← 五个 Tab 独立页面
    │   ├── tab_resume.py    ← Tab1：简历优化
    │   ├── tab_prd.py       ← Tab2：PRD 文档生成
    │   ├── tab_eval.py      ← Tab3：质量评估 + 趋势图
    │   ├── tab_survey.py    ← Tab4：用户调研
    │   └── tab_stats.py     ← Tab5：数据看板（访问/优化/LLM 统计）
    │
    ├── utils/               ← 工具模块
    │   ├── logger.py        ← 本地日志（按天轮转，堆栈追踪）
    │   ├── file_utils.py    ← 多编码兼容 + PDF/DOCX 解析
    │   ├── export_utils.py  ← Markdown / Word 导出
    │   ├── evaluation.py    ← 三维评分 + JSON 容错解析
    │   ├── stats.py         ← 统计数据持久化（访问/优化/LLM 调用）
    │   ├── quota.py         ← 免费额度 + BYOK（IP 哈希识别用户，额度门禁与扣费）
    │   └── migrate_logs.py  ← 一次性脚本：历史日志 → JSON 数据
    │
    └── docs/                ← 设计文档
        ├── coze-agent-design.md      ← Coze Agent 设计方案 + 搭建指南
        └── figma-learning-roadmap.md ← Figma 学习路线 + 原型规格
```

**设计原则**：主文件只做路由，不堆业务逻辑。每个模块职责单一、可独立测试。

---

## 💡 核心技术决策（面试亮点）

### 一、RAG 多路召回（而非单纯向量检索）

```
用户输入 → 同时走两条路：
  ├── 路径① 向量语义召回：句子转数学向量，匹配"意思相近"的文档
  └── 路径② 关键词召回(TF-IDF)：匹配"用词一致"的文档
        ↓
  合并去重 → 重排序 → 取 Top-K 注入 Prompt
```

**为什么这样做**：语义检索抓"同义表达"（如"容器编排"≈"K8s运维"），关键词检索抓"精确术语"（如"Kubernetes"必须命中"Kubernetes"）。单靠一边都会漏结果，两条路互补才能覆盖全。

### 二、LLM 输出容错机制

大模型输出 JSON 时常带废话/格式错误，直接解析会崩溃。采用**四层降级策略**：

```
第1层：json.loads() 直接解析                      ← 正常情况
  ↓ 失败
第2层：正则提取 ```json ... ``` 代码块内容         ← 模型多套了代码块
  ↓ 失败
第3层：提取花括号 + 自动修复末尾多余逗号            ← 格式小毛病
  ↓ 失败
第4层：逐字段正则兜底（"completeness"附近搜数字）    ← 彻底散架也能捞出值
```

只要有一层成功，程序不崩。这体现了对 LLM 输出不稳定性的工程认知。

### 三、LLM 抽象封装

```python
class AbstractLLMClient(ABC):
    def generate(prompt, ...) -> str    # 统一接口

class DeepSeekClient(AbstractLLMClient)  # 云端 API
class OllamaClient(AbstractLLMClient)    # 本地部署（免费）
class QwenClient(AbstractLLMClient)      # 阿里云
```

好处：① 用户可按预算切换模型 ② 避免供应商锁定 ③ 新增模型只需写一个子类，不改业务代码。

### 四、Embedding 双方案

| 方案 | 特点 | 适用场景 |
|------|------|---------|
| **LocalTFIDF** | 纯本地、零网络、384维 | 快速启动 / 离线环境 |
| **BGE-small-zh** | 中文语义、512维、首次下载~100MB | 追求检索精度 |

侧边栏一键切换，切换后自动清除向量库缓存。

### 五、免费额度 + BYOK（公开部署的成本防护）

公开部署后所有 LLM 调用都消耗开发者的 API 额度，存在被刷爆的风险。设计：

```
用户点击功能按钮
  ├── 本地 Ollama？        → 豁免（不花开发者的钱）
  ├── 填了自己的 Key？      → 豁免（BYOK，走用户自己的账单）
  ├── 免费额度还有剩余？    → 放行，调用成功后扣 1 次
  └── 都不满足             → 拦截，引导填入自己的 API Key
```

> 注：Ollama 跑在运行应用的机器上，仅本机运行时可用；侧边栏会自动探测服务是否可达并给出提示，云端部署的访问者请使用 BYOK。

关键工程细节：
- **用户识别**：客户端 IP 做 sha256 哈希后持久化计数（不存明文 IP），无登录系统也能跨会话限流；本地 localhost 直连时回退到 Host 头稳定标识
- **防跨会话密钥泄漏**：LLM 客户端全局单例是进程级共享的，用户自带 Key 时绕过单例、每次新建会话独立实例——否则 A 用户的 Key 会被 B 用户静默使用
- **失败不扣费**：额度在 LLM 调用成功后才扣减，网络错误 / 无效 Key 不烧用户额度
- **密钥安全**：BYOK Key 仅存于会话内存（session_state），永不写盘、不写日志

---

## 🛠 技术栈

| 层级 | 技术 |
|------|------|
| 界面 | Streamlit |
| LLM | DeepSeek API / Ollama / 通义千问（OpenAI 兼容协议） |
| 向量库 | Chroma + LangChain |
| 向量化 | sklearn TF-IDF / BAAI bge-small-zh |
| 数据处理 | Pandas, NumPy |
| 文件解析 | PyPDF2, pdfplumber, python-docx |
| 日志 | Python logging（RotatingFileHandler 按天轮转） |
| 部署 | PowerShell 一键脚本 + .env 环境管理 |

---

## 📁 文件说明

| 文件 | 作用 |
|------|------|
| `.env` | API Key 配置（已 gitignore，不提交） |
| `.gitignore` | 屏蔽密钥/数据库/临时文件 |
| `.streamlit/config.toml` | 深色主题配置（让原生组件文字在深色背景下清晰渲染） |
| `deploy.ps1` | Windows 一键部署脚本 |
| `requirements_resume.txt` | Python 依赖清单 |
| `docs/coze-agent-design.md` | Coze Agent「AI 求职策略顾问」设计方案 |
| `docs/figma-learning-roadmap.md` | Figma 学习路线 + 3 页原型规格 |

---

## 🔒 数据安全

- **所有数据本地存储**：向量库（chroma_db/）、调研记录（data/）、日志（data/logs/）
- **API Key 保护**：.env 文件已加入 .gitignore，不会被提交到 Git
- **用户自带 Key（BYOK）不落盘**：仅存会话内存，刷新即失效，不写日志
- **用户识别匿名化**：额度统计只存 IP 的 sha256 哈希，不保存明文 IP
- **不上传云端**：除 LLM API 调用外，无任何数据外发

---

## 📝 License

MIT — 可自由用于个人学习和求职展示。
