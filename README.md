# LLM Output Helper

[![English](https://img.shields.io/badge/English-README_EN.md-blue)](README_EN.md)

不依赖任何框架的 LLM 结构化输出工具。一个函数，三层兜底，零框架依赖。

```python
from llm_output_helper import structured_output

data = structured_output(
    text=model_response,
    schema={
        "summary": (str, "会议核心结论，100字以内"),
        "action_items": [{
            "task": (str, "待办事项描述"),
            "owner": (str, "负责人姓名"),
            "deadline": (str, "截止日期"),
        }],
    },
    ensure_keys=["summary", "action_items[*].task", "action_items[*].owner"],
    max_retries=2,
    on_retry=lambda feedback: call_your_llm(feedback),
)
```

## 为什么需要这个工具？

LLM 输出的 JSON 质量一言难尽——夹带 markdown 代码块、中文标点、多余尾逗号、被 `max_tokens` 截断的半成品、甚至前面的"让我想想…"闲聊。`response_format: json_object` 参数能缓解一些，但不是所有模型都支持，而且就算支持，出来的东西照样需要清洗。

本项目用**三层兜底**策略，一个 `structured_output()` 全自动搞定：

| 层 | 模块 | 职责 |
|----|------|------|
| ① | `locator.py` | 状态机扫描原始文本，找到所有 JSON 块；多个候选时按 schema 字段重合度打分选最优；全角括号 `｛｝` 也能识别 |
| ② | `repair.py` | 中文标点→英文标点、智能引号修复、缺失括号补全、注释处理、json5 解析 |
| ③ | `validator.py` | 按 ensure_keys 校验字段完整性 + 类型正确性，失败自动生成中文反馈调用 on_retry 重试 |

## 安装

```bash
pip install "git+https://github.com/jiuwenyixi/llm-structured-output.git@v0.2.0"

# 或从源码
git clone https://github.com/jiuwenyixi/llm-structured-output.git
cd llm-structured-output
pip install -e ".[dev]"
```

## 快速上手

```python
from llm_output_helper import structured_output

# 一个典型的中文 LLM 回复——全角标点 + 聊天前缀 + 截断
response = """
让我来分析一下这个问题……
用户想知道：什么是机器学习？

｛
  "question_type"： "定义解释"，
  "answer"： "机器学习是人工智能的一个分支"，
  "confidence"： 0.9
｝
"""

data = structured_output(
    text=response,
    schema={
        "question_type": (str, "问题类型"),
        "answer": (str, "回答内容"),
    },
    ensure_keys=["question_type", "answer"],
)
print(data["answer"])  # → 机器学习是人工智能的一个分支
```

带重试的用法：

```python
def ask_llm(prompt):
    # 你的 LLM 调用逻辑
    return your_model.chat(prompt)

data = structured_output(
    text=ask_llm("整理会议纪要..."),
    schema={
        "summary": (str, "会议结论"),
        "action_items": [{
            "task": (str, "任务"),
            "owner": (str, "负责人"),
        }],
    },
    ensure_keys=["summary", "action_items[*].task", "action_items[*].owner"],
    max_retries=2,
    on_retry=lambda feedback: ask_llm(f"上次输出有问题，请修正：\n{feedback}"),
)
```

## 可选：Pydantic 完整约束校验（v0.2.0）

```bash
pip install "llm-output-helper[pydantic] @ git+https://github.com/jiuwenyixi/llm-structured-output.git@v0.2.0"
```

```python
from typing import Literal
from pydantic import BaseModel, Field
from llm_output_helper import structured_output

class Ticket(BaseModel):
    title: str = Field(min_length=3, max_length=80)
    priority: int = Field(ge=1, le=3)
    status: Literal["open", "closed"]

data = structured_output(
    text='{"title":"修复解析器", "priority":2, "status":"open"}',
    output_model=Ticket,
    model_strict=True,
)
```

传入 `output_model` 后，即使不写 `ensure_keys`，也会校验整个模型的字段、范围、长度、
枚举、别名及自定义规则。失败时返回有界字段反馈并使用同一个 `on_retry` / `max_retries`
预算；耗尽后抛本库的 `ValidationError`。未安装可选依赖、传错模型或 validator 内的
编程异常直接抛出，不消耗模型重试。

返回值保持普通容器，来自 `model_dump(mode="python")`：字段名归一化、默认值和模型
允许的转换会反映在结果中；日期或枚举等可能保留 Python 原生对象，不承诺直接可 JSON 序列化。
`ensure_keys` 在模型校验后执行，使用归一化后的字段名。
`model_strict=None` 默认遵循 Pydantic 模型配置，可能转换类型；`True` 显式禁止强制转换，
`False` 显式允许。它只控制模型类型校验，不控制前面的 JSON 修复。
未传 `schema` 时，模型字段名和字符串别名仅作为候选选择提示；最终仍以模型校验为准。
支持 `RootModel` 数组结果；JSON 标量根、异步和流式入口尚未提供。

完整离线重试示例见 [examples/pydantic_validation.py](examples/pydantic_validation.py)。

## 三层兜底详解

### ① JSON 定位器

逐字符状态机，SEEK→CAPTURE 两阶段交替：找 `{` `[` `｛` `［` → 跟踪括号深度和引号边界 → 深度归零产出完整块。多个候选时按 schema key 重合度打分选最优。文本截断时也不丢数据——不完整块照样产出，交给 repair 层修复。

### ② JSON 修复器

- **`repair_json_fragment`** — 上下文感知替换中文结构标点（`：→:` `，→,` `｛→{`），**字符串内容不动**
- **`complete_json`** — 栈扫描补全缺失的 `}` `]` `"` 和未闭合注释
- **`parse_json`** — 一键修复→补全→json5 解析

### ③ 字段校验 + 重试

`ensure_keys` 支持 `[*]` 通配符和点号路径：
- `"summary"` — 顶层字段必须存在
- `"action_items[*].task"` — 数组中每个元素的 task 字段
- 类型不匹配、字段缺失、空数组都会生成中文错误反馈

校验失败 → 自动生成反馈 → 调用 `on_retry` → 新文本回到第一层重新走。超限抛 `ValidationError`，脏数据不下传。

## 使用边界

- 普通字典 `schema` 用于候选 JSON 选择及指定字段的类型检查；**只传 `schema` 不会自动校验全部字段**，需要通过 `ensure_keys` 明确列出必填路径，或用 `output_model` 做完整模型校验。
- `ensure_keys` 支持多层 `[*]`，例如 `groups[*].items[*].name`；数组元素按对应层的模板检查类型。普通 schema 的整数和浮点数字段不接受布尔值；Pydantic 则按其模型配置和 `model_strict` 处理转换。
- 提取失败、解析失败、字段校验失败共用 `max_retries` 次回调预算；无回调或预算耗尽时，提取/解析失败抛 `ValueError`，字段失败抛 `ValidationError`。回调自身的异常直接传播。
- 补齐括号或引号只能恢复语法，不能恢复模型没有生成的内容，也不能保证业务正确性。重要字段应增加业务校验。
- 支持可选 Pydantic v2 模型校验；尚无独立 JSON Schema 校验器、异步回调或增量流式 API；返回值可以是对象或数组。
- 本次是 GitHub Release。上面的命令从版本标签安装；不代表已经发布到 PyPI。

可运行的离线例子见 [examples/basic.py](examples/basic.py)。

## 开发

```bash
pip install -e ".[dev]"
pytest -v   # base: 148 passed, model suite skipped without Pydantic
pip install -e ".[pydantic]"
pytest -v   # 171 tests with Pydantic v2
```

## 来源与 License

JSON 定位、修复与补全的部分实现参考并改编自 [Agently](https://github.com/AgentEra/Agently)。
这些派生模块按 Apache-2.0 发布，其余项目代码按 MIT 发布。详见
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)、[LICENSE](LICENSE) 和
[LICENSE-APACHE-2.0](LICENSE-APACHE-2.0)。运行时不依赖 Agently。
