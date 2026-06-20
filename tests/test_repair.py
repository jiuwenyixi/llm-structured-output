"""Tests for llm_output_helper.repair — punctuation fix & bracket completion."""

import pytest

from llm_output_helper.repair import (
    repair_json_fragment,
    complete_json,
    parse_json,
    parse_json_safe,
)


# ============================================================================
# repair_json_fragment
# ============================================================================

class TestRepairJsonFragment:
    """Context-aware Chinese punctuation → ASCII repair."""

    # --- empty / no-op --------------------------------------------------

    def test_empty_input(self):
        assert repair_json_fragment("") == ""

    def test_already_valid_json_passes_through(self):
        text = '{"name": "Alice", "age": 30}'
        assert repair_json_fragment(text) == text

    def test_whitespace_only(self):
        assert repair_json_fragment("   \n  ") == "   \n  "

    # --- Chinese structural punctuation ---------------------------------

    def test_chinese_colon(self):
        assert repair_json_fragment('{"name"： "Alice"}') == '{"name": "Alice"}'

    def test_chinese_comma(self):
        assert repair_json_fragment('{"a"：1 ， "b"：2}') == '{"a":1 , "b":2}'

    def test_fullwidth_curly_braces(self):
        result = repair_json_fragment('｛"name"： "Alice"｝')
        assert result == '{"name": "Alice"}'

    def test_fullwidth_square_brackets(self):
        result = repair_json_fragment('［1 ， 2 ， 3］')
        assert result == '[1 , 2 , 3]'

    # --- smart / fullwidth quotes ---------------------------------------

    def test_smart_double_quotes(self):
        result = repair_json_fragment('“name”： “Alice”')
        # "name": "Alice"
        assert '"name"' in result
        assert '"Alice"' in result

    def test_fullwidth_quotes(self):
        result = repair_json_fragment('＂name＂： ＂Alice＂')
        assert '"name"' in result
        assert '"Alice"' in result

    # --- Chinese punctuation inside string VALUE must be preserved -----

    def test_chinese_colon_inside_string_value_preserved(self):
        """Structural colon → :, but 地址：北京 inside value stays."""
        text = '{"addr"： "地址：北京"}'
        result = repair_json_fragment(text)
        # The colon after "addr" (structural) → :
        # But 地址：北京 should keep its Chinese colon
        parsed = parse_json(result)
        assert parsed["addr"] == "地址：北京"

    def test_chinese_comma_inside_string_value_preserved(self):
        text = '{"tags"： "标签1，标签2"}'
        parsed = parse_json(repair_json_fragment(text))
        assert parsed["tags"] == "标签1，标签2"

    # --- unquoted keys --------------------------------------------------

    def test_unquoted_keys_preserved(self):
        """Repair should not break unquoted-key JSON (json5 handles it later)."""
        text = "{name： Alice}"
        result = repair_json_fragment(text)
        assert "name" in result

    # --- mixed scenarios -------------------------------------------------

    def test_fully_broken_chinese_json(self):
        text = '｛"name"： "张三" ， "items"： ［"a" ， "b"］｝'
        result = repair_json_fragment(text)
        assert result == '{"name": "张三" , "items": ["a" , "b"]}'

    def test_realistic_llm_output(self):
        text = """｛
  "question_type"： "math"，
  "answer"： "the answer is 42"，
  "confidence"： 0.95
｝"""
        result = repair_json_fragment(text)
        assert '：' not in result
        assert '，' not in result
        assert '｛' not in result
        assert '｝' not in result


# ============================================================================
# complete_json
# ============================================================================

class TestCompleteJson:
    """Stack-based bracket / string / comment completion."""

    # --- no-op -----------------------------------------------------------

    def test_already_complete_passes_through(self):
        text = '{"a": 1}'
        assert complete_json(text) == text

    def test_empty_input(self):
        assert complete_json("") == ""

    # --- missing closing brackets ---------------------------------------

    def test_missing_single_close_brace(self):
        result = complete_json('{"a": 1')
        assert result == '{"a": 1}'

    def test_missing_single_close_bracket(self):
        result = complete_json('[1, 2')
        assert result == '[1, 2]'

    def test_nested_missing_braces(self):
        result = complete_json('{"a": {"b": 3')
        assert result == '{"a": {"b": 3}}'

    def test_mixed_missing_brackets(self):
        result = complete_json('{"items": [1, 2')
        assert result == '{"items": [1, 2]}'

    def test_missing_nested_array_close(self):
        result = complete_json('[[1, 2], [3, 4')
        assert result == '[[1, 2], [3, 4]]'

    # --- unclosed string -------------------------------------------------

    def test_unclosed_string(self):
        result = complete_json('{"name": "Alice')
        assert result == '{"name": "Alice"}'

    def test_unclosed_string_at_end(self):
        result = complete_json('["hello')
        assert result == '["hello"]'

    def test_unclosed_single_quoted_string(self):
        result = complete_json("{'name': 'Alice")
        assert result == "{'name': 'Alice'}"

    # --- comment handling ------------------------------------------------

    def test_ending_in_line_comment(self):
        result = complete_json('{"a": 1\n// comment')
        assert result.endswith('comment\n}')

    def test_ending_in_block_comment(self):
        result = complete_json('{"a": 1\n/* unfinished')
        assert result.endswith('unfinished*/}')

    # --- edge cases ------------------------------------------------------

    def test_string_with_brace_inside_not_mistaken_for_bracket(self):
        text = '{"text": "hello { world"'
        result = complete_json(text)
        assert result == '{"text": "hello { world"}'

    def test_escaped_quote_inside_string(self):
        text = '{"msg": "he said \\"hi\\""'
        result = complete_json(text)
        assert result == '{"msg": "he said \\"hi\\""}'


# ============================================================================
# parse_json
# ============================================================================

class TestParseJson:
    """Full pipeline: repair → complete → json5.loads."""

    def test_parse_valid_json(self):
        assert parse_json('{"a": 1}') == {"a": 1}

    def test_parse_with_chinese_punctuation(self):
        result = parse_json('｛"name"： "张三"｝')
        assert result == {"name": "张三"}

    def test_parse_with_trailing_comma(self):
        """json5 handles trailing commas natively."""
        result = parse_json('{"a": 1, "b": 2,}')
        assert result == {"a": 1, "b": 2}

    def test_parse_with_comments(self):
        result = parse_json('{"a": 1\n// comment\n}')
        assert result == {"a": 1}

    def test_parse_truncated_json(self):
        result = parse_json('{"name": "Alice", "items": [1, 2')
        assert result == {"name": "Alice", "items": [1, 2]}

    def test_parse_single_quotes(self):
        result = parse_json("{'name': 'Alice'}")
        assert result == {"name": "Alice"}

    def test_parse_realistic_llm_chinese_output(self):
        text = """｛
  "question_type"： "填空题"，
  "answer"： "正确答案是42"，
  "options"： ［"A"， "B"， "C"］
｝"""
        result = parse_json(text)
        assert result["question_type"] == "填空题"
        assert result["answer"] == "正确答案是42"
        assert result["options"] == ["A", "B", "C"]

    def test_parse_completely_broken_raises(self):
        with pytest.raises(Exception):
            parse_json("this is not json at all {[")

    def test_parse_array(self):
        result = parse_json("[1, 2, 3]")
        assert result == [1, 2, 3]

    def test_parse_nested(self):
        text = '{"user": {"name": "test", "scores": [90, 85]}}'
        result = parse_json(text)
        assert result["user"]["scores"] == [90, 85]


# ============================================================================
# parse_json_safe
# ============================================================================

class TestParseJsonSafe:
    def test_returns_none_on_failure(self):
        assert parse_json_safe("not json {{{") is None

    def test_returns_data_on_success(self):
        assert parse_json_safe('{"ok": true}') == {"ok": True}

    def test_returns_none_on_empty_string(self):
        assert parse_json_safe("") is None


# ============================================================================
# Integration: repair + complete + parse
# ============================================================================

class TestIntegration:
    """End-to-end scenarios that exercise all layers together."""

    def test_chinese_plus_truncation(self):
        """Chinese punctuation + missing close bracket — classic LLM output."""
        text = '｛"items"： ［"值1"， "值2"'
        result = parse_json(text)
        assert result == {"items": ["值1", "值2"]}

    def test_smart_quotes_plus_truncation(self):
        text = '“name”： “Alice'
        result = parse_json(text)
        assert result == {"name": "Alice"}

    def test_mixed_scenario(self):
        text = """Here's the data: ｛"姓名"： "张三" ， "得分"： ［95"""
        # The text contains non-JSON prefix, but parse_json receives the JSON part
        # after locator extracts it.  We test the JSON fragment directly.
        result = parse_json('｛"姓名"： "张三" ， "得分"： ［95］｝')
        assert result == {"姓名": "张三", "得分": [95]}
