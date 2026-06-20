"""Tests for llm_output_helper.validator and structured_output integration."""

import pytest

from llm_output_helper import (
    ValidationError,
    make_retry_feedback,
    structured_output,
    validate,
)


# ============================================================================
# Sample schema
# ============================================================================

MEETING_SCHEMA = {
    "summary": (str, "会议核心结论，100字以内"),
    "action_items": [
        {
            "task": (str, "待办事项描述"),
            "owner": (str, "负责人姓名"),
            "deadline": (str, "截止日期"),
        }
    ],
}


# ============================================================================
# validate
# ============================================================================

class TestValidate:
    def test_all_keys_present(self):
        data = {
            "summary": "项目启动会议结论",
            "action_items": [
                {"task": "写文档", "owner": "张三", "deadline": "2026-07-01"},
                {"task": "搭建环境", "owner": "李四", "deadline": "2026-06-25"},
            ],
        }
        keys = ["summary", "action_items[*].task", "action_items[*].owner"]
        assert validate(data, keys, MEETING_SCHEMA) == []

    def test_missing_top_level_key(self):
        data = {"action_items": []}
        errors = validate(data, ["summary"], MEETING_SCHEMA)
        assert len(errors) == 1
        assert "summary" in errors[0]

    def test_missing_nested_key_in_array_item(self):
        data = {
            "summary": "结论",
            "action_items": [
                {"task": "写文档"},  # missing owner
                {"owner": "张三"},   # missing task
            ],
        }
        errors = validate(
            data,
            ["action_items[*].task", "action_items[*].owner"],
            MEETING_SCHEMA,
        )
        assert len(errors) == 2
        assert "task" in errors[0] or "task" in errors[1]
        assert "owner" in errors[0] or "owner" in errors[1]

    def test_type_mismatch(self):
        data = {
            "summary": 12345,  # should be str
            "action_items": [],
        }
        errors = validate(data, ["summary"], MEETING_SCHEMA)
        assert len(errors) == 1
        assert "类型错误" in errors[0] or "type" in errors[0].lower()

    def test_empty_array(self):
        data = {"summary": "结论", "action_items": []}
        errors = validate(data, ["action_items[*].task"], MEETING_SCHEMA)
        assert len(errors) == 1
        assert "空数组" in errors[0] or "empty" in errors[0].lower()

    def test_field_on_non_dict(self):
        """action_items[0] exists but is not a dict."""
        data = {"summary": "ok", "action_items": ["not_a_dict"]}
        errors = validate(data, ["action_items[*].task"], MEETING_SCHEMA)
        # "not_a_dict" is a str, not a dict, so .task can't be accessed
        assert len(errors) >= 1

    def test_no_ensure_keys(self):
        data = {"anything": "goes"}
        assert validate(data, [], {}) == []

    def test_flat_schema(self):
        schema = {"name": (str, "姓名"), "age": (int, "年龄")}
        data = {"name": "Alice", "age": 30}
        assert validate(data, ["name", "age"], schema) == []

    def test_flat_schema_missing(self):
        schema = {"name": (str, ""), "age": (int, "")}
        data = {"name": "Alice"}
        errors = validate(data, ["name", "age"], schema)
        assert len(errors) == 1
        assert "age" in errors[0].lower()


# ============================================================================
# make_retry_feedback
# ============================================================================

class TestMakeRetryFeedback:
    def test_single_error(self):
        feedback = make_retry_feedback(["缺少字段: summary"])
        assert "summary" in feedback
        assert "修正" in feedback

    def test_multiple_errors(self):
        feedback = make_retry_feedback(["缺少 summary", "缺少 owner"])
        assert "1." in feedback
        assert "2." in feedback

    def test_language_is_chinese(self):
        feedback = make_retry_feedback(["missing field"])
        assert "JSON" in feedback or "修正" in feedback


# ============================================================================
# structured_output — integration
# ============================================================================

class TestStructuredOutput:
    def test_clean_json_passes_through(self):
        data = structured_output(
            text='{"name": "Alice", "age": 30}',
            schema={"name": (str, ""), "age": (int, "")},
        )
        assert data["name"] == "Alice"
        assert data["age"] == 30

    def test_chinese_punctuation_handled(self):
        data = structured_output(
            text='｛"name"： "张三" ， "age"： 25｝',
            schema={"name": (str, ""), "age": (int, "")},
        )
        assert data["name"] == "张三"
        assert data["age"] == 25

    def test_truncated_json_repaired(self):
        data = structured_output(
            text='{"summary": "结论", "action_items": [{"task": "写文档", "owner": "张三"}',
            schema=MEETING_SCHEMA,
        )
        assert data["summary"] == "结论"
        assert len(data["action_items"]) == 1

    def test_ensure_keys_valid(self):
        data = structured_output(
            text='{"summary": "结论", "action_items": [{"task": "写文档", "owner": "张三"}]}',
            schema=MEETING_SCHEMA,
            ensure_keys=["summary", "action_items[*].task", "action_items[*].owner"],
        )
        assert data["summary"] == "结论"

    def test_ensure_keys_fails_without_on_retry(self):
        with pytest.raises(ValidationError) as exc:
            structured_output(
                text='{"action_items": [{"task": "写文档"}]}',
                schema=MEETING_SCHEMA,
                ensure_keys=["summary", "action_items[*].owner"],
                max_retries=0,
            )
        assert "summary" in str(exc.value)
        assert "owner" in str(exc.value)

    def test_retry_succeeds_on_second_attempt(self):
        call_count = [0]
        responses = [
            '{"summary": "incomplete"}',  # first attempt — missing action_items
            '{"summary": "结论", "action_items": [{"task": "写文档", "owner": "张三"}]}',
        ]

        def mock_llm(feedback):
            idx = call_count[0]
            call_count[0] += 1
            return responses[idx]

        data = structured_output(
            text=responses[0],
            schema=MEETING_SCHEMA,
            ensure_keys=["summary", "action_items[*].task", "action_items[*].owner"],
            max_retries=2,
            on_retry=mock_llm,
        )
        assert data["summary"] == "结论"
        assert call_count[0] == 2  # first attempt + one retry

    def test_retry_exhausted_raises(self):
        responses = [
            '{"summary": "bad"}',
            '{"summary": "still bad"}',
            '{"summary": "still no action items"}',
        ]
        call_count = [0]

        def mock_llm(feedback):
            idx = call_count[0]
            call_count[0] += 1
            return responses[idx]

        with pytest.raises(ValidationError):
            structured_output(
                text=responses[0],
                schema=MEETING_SCHEMA,
                ensure_keys=["summary", "action_items[*].task"],
                max_retries=2,
                on_retry=mock_llm,
            )
        # initial attempt + 2 retries via on_retry = 2 callbacks
        assert call_count[0] == 2

    def test_embedded_json_in_chatty_text(self):
        """Full integration: CoT text with Chinese punctuation."""
        text = """让我想想……

        ｛
          "summary"： "今天讨论了项目排期"，
          "action_items"： ［
            ｛"task"： "整理需求文档" ， "owner"： "张三"｝
          ］
        ｝"""
        data = structured_output(
            text=text,
            schema=MEETING_SCHEMA,
            ensure_keys=["summary", "action_items[*].task", "action_items[*].owner"],
        )
        assert data["summary"] == "今天讨论了项目排期"
        assert data["action_items"][0]["task"] == "整理需求文档"
        assert data["action_items"][0]["owner"] == "张三"

    def test_no_json_raises(self):
        with pytest.raises(ValueError, match="No JSON block"):
            structured_output(
                text="just plain text, no json at all",
                schema={"name": (str, "")},
            )
