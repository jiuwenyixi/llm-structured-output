"""Tests for llm_output_helper.locator — JSON block extraction & scoring."""

import pytest

from llm_output_helper.locator import (
    locate_all_json,
    locate_output_json,
    _extract_leaf_keys,
    _has_dotted_key,
    _score_schema_match,
    _preprocess,
)


# ============================================================================
# locate_all_json
# ============================================================================

class TestLocateAllJson:
    """Character-by-character state machine tests."""

    # --- edge cases --------------------------------------------------------

    def test_empty_input(self):
        assert locate_all_json("") == []

    def test_whitespace_only(self):
        assert locate_all_json("   \n\t  ") == []

    def test_no_json_blocks(self):
        assert locate_all_json("hello world, this is plain text.") == []

    def test_bare_braces_not_a_block(self):
        # Single braces with no matching pairs in a "layer returns to 0" sense.
        # Actually: '{' triggers stage=2, layer=1; then '}' closes layer=0 → it IS a block.
        assert locate_all_json("{}") == ["{}"]
        assert locate_all_json("[]") == ["[]"]

    def test_unclosed_brace_not_returned(self):
        # Stage stays in CAPTURE, never returns to depth=0 → nothing yielded.
        assert locate_all_json("{ 'name': 'test'  ") == []

    # --- simple blocks -----------------------------------------------------

    def test_single_object(self):
        result = locate_all_json('{"a": 1}')
        assert result == ['{"a": 1}']

    def test_single_array(self):
        result = locate_all_json('[1, 2, 3]')
        assert result == ['[1, 2, 3]']

    def test_object_with_string_values(self):
        text = '{"name": "Alice", "city": "New York"}'
        assert locate_all_json(text) == [text]

    # --- multiple blocks ---------------------------------------------------

    def test_two_objects(self):
        text = 'first {"a": 1} middle {"b": 2} last'
        assert locate_all_json(text) == ['{"a": 1}', '{"b": 2}']

    def test_mixed_object_and_array(self):
        text = '{"x": [1, 2]} and [3, 4]'
        assert locate_all_json(text) == ['{"x": [1, 2]}', '[3, 4]']

    def test_three_blocks(self):
        text = '[1] {"k": "v"} [2]'
        assert locate_all_json(text) == ['[1]', '{"k": "v"}', '[2]']

    # --- nested structures -------------------------------------------------

    def test_deeply_nested_object(self):
        text = '{"a": {"b": {"c": [1, 2, 3]}}}'
        assert locate_all_json(text) == [text]

    def test_nested_array_in_object(self):
        text = '{"items": [{"id": 1}, {"id": 2}]}'
        assert locate_all_json(text) == [text]

    # --- strings containing brackets ---------------------------------------

    def test_brace_inside_string_value(self):
        # A JSON object with a string value that contains '{' and '}'.
        text = '{"text": "this has a {brace} inside"}'
        assert locate_all_json(text) == [text]

    def test_bracket_inside_string(self):
        text = '{"code": "function foo() { return []; }"}'
        assert locate_all_json(text) == [text]

    # --- escape sequences --------------------------------------------------

    def test_escaped_quote_inside_string(self):
        text = '{"msg": "he said \\"hello\\""}'
        assert locate_all_json(text) == ['{"msg": "he said \\"hello\\""}']

    def test_backslash_in_string(self):
        text = '{"path": "C:\\\\Users\\\\test"}'
        result = locate_all_json(text)
        assert len(result) == 1
        # The locator preserves the escape sequences inside strings.
        assert "C:\\\\" in result[0]

    # --- real-world LLM output patterns ------------------------------------

    def test_json_in_markdown_code_fence(self):
        text = '''
Here is the answer:

```json
{"name": "test", "value": 42}
```
'''
        assert locate_all_json(text) == ['{"name": "test", "value": 42}']

    def test_chain_of_thought_with_json_at_end(self):
        text = '''
Let me think about this step by step...
First, I need to consider X.
Then, I should check Y.

Based on my analysis: {"answer": "yes", "confidence": 0.95}
'''
        assert locate_all_json(text) == ['{"answer": "yes", "confidence": 0.95}']

    def test_multiple_json_in_cot(self):
        text = '''
Thought: {"step": 1, "action": "analyze"}
Then: {"step": 2, "action": "decide"}
Final: {"result": "done"}
'''
        assert locate_all_json(text) == [
            '{"step": 1, "action": "analyze"}',
            '{"step": 2, "action": "decide"}',
            '{"result": "done"}',
        ]

    def test_json_with_newlines(self):
        text = '''{
"name": "Alice",
"hobbies": ["reading", "coding"]
}'''
        result = locate_all_json(text)
        # Newlines inside strings become \\n, but structural newlines
        # (between keys) are preserved as-is since they're outside quoted strings.
        assert len(result) == 1
        assert '"name"' in result[0]

    # --- triple-quote handling ---------------------------------------------

    def test_triple_quoted_block(self):
        text = 'The data is: """{"key": "value"}""" end'
        result = locate_all_json(text)
        assert len(result) == 1
        assert '"key"' in result[0]

    # --- [OUTPUT] tag protection -------------------------------------------

    def test_output_tag_protection(self):
        text = 'before [OUTPUT] {"a": 1} after'
        result = locate_all_json(text)
        # [OUTPUT] is protected from being treated as an array bracket.
        assert result == ['{"a": 1}']


# ============================================================================
# locate_output_json
# ============================================================================

class TestLocateOutputJson:
    """Schema-guided best-candidate selection."""

    def test_no_candidates_returns_none(self):
        assert locate_output_json("hello world") is None
        assert locate_output_json("") is None

    def test_single_candidate_returned_directly(self):
        text = 'some text {"a": 1} more text'
        assert locate_output_json(text) == '{"a": 1}'

    def test_multiple_no_schema_returns_last(self):
        # Fallback: last block is often the "final answer" in CoT responses.
        text = '{"step": 1} {"step": 2} {"final": "answer"}'
        assert locate_output_json(text) == '{"final": "answer"}'

    def test_multiple_with_schema_picks_best_match(self):
        text = '''
{"unrelated": "data", "foo": "bar"}
{"question_type": "math", "answer": "42"}
{"another": "block"}
'''
        schema = {"question_type": str, "answer": str}
        best = locate_output_json(text, schema=schema)
        assert best == '{"question_type": "math", "answer": "42"}'

    def test_partial_schema_match(self):
        text = '{"name": "Alice"} {"name": "Bob", "age": 30}'
        schema = {"name": str, "age": int}
        best = locate_output_json(text, schema=schema)
        assert '"age"' in best
        assert '"Bob"' in best

    def test_nested_schema_keys(self):
        text = '{"a": 1} {"user": {"name": "Alice", "email": "a@b.com"}}'
        schema = {"user": {"name": str}}
        best = locate_output_json(text, schema=schema)
        assert "Alice" in best

    def test_schema_ignores_array_when_expecting_object(self):
        text = '[1, 2, 3] {"name": "test"}'
        schema = {"name": str}
        best = locate_output_json(text, schema=schema)
        assert best == '{"name": "test"}'

    def test_no_schema_keys_match_returns_first(self):
        text = '{"x": 1} {"y": 2}'
        schema = {"nonexistent": str}
        result = locate_output_json(text, schema=schema)
        # Both score 0 (valid dict but no key matches);
        # the first candidate to hit score 0 wins.
        assert result is not None
        assert result in ('{"x": 1}', '{"y": 2}')


# ============================================================================
# Internal helpers
# ============================================================================

class TestExtractLeafKeys:
    def test_flat_schema(self):
        schema = {"name": str, "age": int}
        assert _extract_leaf_keys(schema) == {"name", "age"}

    def test_nested_schema(self):
        schema = {
            "user": {
                "name": str,
                "address": {
                    "city": str,
                    "zip": str,
                },
            },
            "score": float,
        }
        assert _extract_leaf_keys(schema) == {
            "user.name",
            "user.address.city",
            "user.address.zip",
            "score",
        }

    def test_empty_schema(self):
        assert _extract_leaf_keys({}) == set()


class TestHasDottedKey:
    def test_top_level_key(self):
        assert _has_dotted_key({"a": 1, "b": 2}, "a") is True
        assert _has_dotted_key({"a": 1}, "c") is False

    def test_nested_key(self):
        data = {"user": {"name": "Alice", "email": "a@b.com"}}
        assert _has_dotted_key(data, "user.name") is True
        assert _has_dotted_key(data, "user.age") is False

    def test_deeply_nested(self):
        data = {"a": {"b": {"c": "found"}}}
        assert _has_dotted_key(data, "a.b.c") is True
        assert _has_dotted_key(data, "a.b.x") is False
        assert _has_dotted_key(data, "a.x.c") is False

    def test_missing_intermediate(self):
        data = {"a": "flat"}
        assert _has_dotted_key(data, "a.b.c") is False


class TestScoreSchemaMatch:
    def test_perfect_match(self):
        assert _score_schema_match('{"a": 1, "b": 2}', {"a", "b"}) == 2

    def test_partial_match(self):
        assert _score_schema_match('{"a": 1}', {"a", "b"}) == 1

    def test_no_match(self):
        assert _score_schema_match('{"x": 1}', {"a", "b"}) == 0

    def test_invalid_json(self):
        assert _score_schema_match("not json", {"a"}) == -1

    def test_array_when_expecting_object(self):
        assert _score_schema_match("[1, 2, 3]", {"a"}) == -1

    def test_empty_schema_keys(self):
        assert _score_schema_match('{"a": 1}', set()) == 0  # anything goes

    def test_nested_key_match(self):
        json_str = '{"user": {"name": "Alice", "email": "a@b.com"}}'
        assert _score_schema_match(json_str, {"user.name"}) == 1
        assert _score_schema_match(json_str, {"user.name", "user.email"}) == 2
        assert _score_schema_match(json_str, {"user.name", "user.age"}) == 1


class TestPreprocess:
    def test_triple_quote_conversion(self):
        text = 'Text: """hello world""" end'
        processed = _preprocess(text)
        # The triple-quoted content should be json5-escaped (quoted).
        assert '"""' not in processed

    def test_output_tag_protection(self):
        text = "[OUTPUT]"
        processed = _preprocess(text)
        assert "[OUTPUT]" not in processed
        assert "$<<OUTPUT>>" in processed

    def test_combination(self):
        text = '[OUTPUT] """{"a": 1}"""'
        processed = _preprocess(text)
        assert "[OUTPUT]" not in processed
        assert '"""' not in processed
