# LLM Output Helper

[![English](https://img.shields.io/badge/English-README_EN.md-blue)](README_EN.md)

不依赖任何框架的 LLM 结构化输出提取工具。零依赖 LangChain、Agently 等 Agent 框架，只需 `json5` 做宽松 JSON 解析。

## 为什么需要这个工具？

LLM 输出的 JSON 质量一言难尽——夹带 markdown 代码块、中文标点、多余尾逗号、被 `max_tokens` 截断的半成品、甚至前面的"让我想想…"闲聊。`response_format: json_object` 参数能缓解一些，但不是所有模型都支持，而且就算支持，出来的东西照样需要清洗。

本项目用**三层兜底**策略（算法思路参考 [Agently](https://github.com/AgentEra/Agently)，代码完全自写）：

| 层 | 模块 | 职责 |
|----|------|------|
| ① | `locator.py` | 状态机扫描原始文本，找到所有 JSON 块；多个候选时按 schema 字段重合度打分选最优 |
| ② | `repair.py` | 中文标点→英文标点、智能引号修复、缺失括号补全、注释处理、json5 解析 |
| ③ | `validator.py` | 按 schema 校验字段完整性 + 类型正确性，失败自动生成反馈重试 |

## 开发进度

- [x] **第一层 — `locator.py`** — 完成，48 个测试通过
- [x] **第二层 — `repair.py`** — 完成，44 个测试通过
- [ ] 第三层 — `validator.py` — 待开发

## 安装

```bash
# PyPI（上线后可用）
pip install llm-output-helper

# 从源码安装
git clone https://github.com/jiuwenyixi/llm-structured-output.git
cd llm-structured-output
pip install -e ".[dev]"
```

## 快速上手

```python
from llm_output_helper import locate_output_json, parse_json

# 一个典型的中文 LLM 回复——全角标点 + 聊天式前缀
response = """
让我来分析一下这个问题……
用户想知道：什么是机器学习？

｛
  "question_type"： "定义解释"，
  "answer"： "机器学习是人工智能的一个分支"，
  "confidence"： 0.9
｝
"""

# 第一层：从原始文本中找到 JSON 块
raw_json = locate_output_json(
    response,
    schema={"question_type": str, "answer": str, "confidence": float}
)

# 第二层：修复中文标点、补全括号、解析为 dict
data = parse_json(raw_json)
print(data["answer"])  # → 机器学习是人工智能的一个分支
```

## 三层兜底详解

### ① JSON 定位器

逐字符扫描状态机，两个阶段交替：

1. **预处理** — 把 Python 三引号 `"""..."""` 转为 json5 安全格式，保护 `[OUTPUT]` 标签
2. **SEEK 阶段** — 找 `{` 或 `[`，开始一个新块
3. **CAPTURE 阶段** — 跟踪括号深度、引号边界、转义序列，深度归零时完成一个块
4. **多候选打分** — 用 json5 解析每个候选，按 schema key 重合度评分，选最优

### ② JSON 修复器

两步流水线：

**`repair_json_fragment`** — 上下文感知状态机：
- 中文/全角结构标点归一化：`：→:` `，→,` `｛→{` `｝→}` `［→[` `］→]`
- 智能引号归一化：`" "` → `"`、`' '` → `'`
- **字符串内容不动**：`"地址：北京"` 里的中文冒号原样保留
- 未加引号的 key 也能处理

**`complete_json`** — 栈扫描补全：
- 未闭合的 `{` `[` 自动补上对应的 `}` `]`
- 未闭合的字符串引号自动补上
- `//` 单行注释和 `/* */` 块注释自动收尾

**`parse_json`** — 一键调用，修复→补全→解析，自动处理裸 key:value 对缺失外层 `{}` 的情况

### json5 兜不住，才需要第二层

| 错误类型 | json5 能处理？ | repair.py 能处理？ |
|----------|:---:|:---:|
| `：` 中文冒号 | ❌ | ✅ |
| `，` 中文逗号 | ❌ | ✅ |
| `｛｝［］` 全角括号 | ❌ | ✅ |
| `" "` 智能引号 | ❌ | ✅ |
| `}` `]` 缺失闭合 | ❌ | ✅ |
| `,}` 尾部逗号 | ✅ | — |
| `'key'` 单引号 | ✅ | — |
| `//` 注释 | ✅ | — |

## 与同类工具的区别

| | llm-output-helper | json_repair | outputguard | Agently |
|----|:---:|:---:|:---:|:---:|
| 多 JSON 块定位 | ✅ | ❌ | ✅ | ✅ |
| 中文标点修复 | ✅ | ❌ | ❌ | ✅ |
| 缺失括号补全 | ✅ | ✅ | ✅ | ✅ |
| 字段校验+重试 | ✅ (开发中) | ❌ | ✅ | ✅ |
| 零框架依赖 | ✅ | ✅ | ❌ | ❌ |
| 一个函数入口 | ✅ | ✅ | ❌ | — |

## 面试怎么说

> "我写了一个结构化输出工具，三层兜底——状态机 JSON 定位 → 上下文感知中文标点修复 → 字段校验重试。不依赖 `response_format` 参数，换不支持结构化输出的模型也能跑。92 个测试用例，代码和测试全手写。"

## 开发

```bash
pip install -e ".[dev]"
pytest -v
```

## License

MIT
