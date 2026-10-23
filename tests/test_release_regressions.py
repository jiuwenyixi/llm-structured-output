"""Regression cases found while preparing the first public release."""

import pytest

from llm_output_helper import (
    ValidationError, locate_all_json, locate_output_json, parse_json,
    structured_output, validate,
)


@pytest.mark.parametrize("value", ["a } b", "a { b", "a ] b", 'say "hi"', "中文：，"])
def test_json5_single_quoted_content_survives_location(value):
    text = "{'name': '" + value + "'}"
    assert locate_all_json(text) == [text]
    assert structured_output("Answer: " + text)["name"] == value


@pytest.mark.parametrize("comment", ["/* } ] ' */", "// } ] '\n"])
def test_json5_comment_brackets_do_not_end_block(comment):
    text = '{"name": ' + comment + ' "complete"}'
    assert locate_all_json(text) == [text]
    assert structured_output(text) == {"name": "complete"}


def test_valid_json_string_content_is_not_repaired():
    text = '{"text": "中文”, 后半段：保留"}'
    assert parse_json(text) == {"text": "中文”, 后半段：保留"}


def test_truncated_candidate_is_completed_for_schema_scoring():
    text = '{"other": 1} then {"name": "Alice"'
    selected = locate_output_json(text, {"name": str})
    assert parse_json(selected) == {"name": "Alice"}


@pytest.mark.parametrize("spec", [str, (str, "description")])
def test_wildcard_item_uses_its_own_schema(spec):
    schema = {"items": [{"name": spec}]}
    errors = validate({"items": [{"name": 42}]}, ["items[*].name"], schema)
    assert len(errors) == 1
    assert "items[0].name" in errors[0]
    assert "str" in errors[0]


def test_multiple_wildcards_validate_and_report_full_path():
    schema = {"groups": [{"items": [{"name": str}]}]}
    keys = ["groups[*].items[*].name"]
    assert validate({"groups": [{"items": [{"name": "ok"}]}]}, keys, schema) == []
    errors = validate({"groups": [{"items": [{"name": 42}]}]}, keys, schema)
    assert len(errors) == 1
    assert "groups[0].items[0].name" in errors[0]


def test_adjacent_wildcards_validate_scalar_elements():
    schema = {"matrix": [[int]]}
    assert validate({"matrix": [[1, 2]]}, ["matrix[*][*]"], schema) == []
    errors = validate({"matrix": [[1, "bad"]]}, ["matrix[*][*]"], schema)
    assert len(errors) == 1 and "matrix[0][1]" in errors[0]


@pytest.mark.parametrize("item", [None, "bad", True])
def test_scalar_array_items_are_checked(item):
    assert validate({"items": [item]}, ["items[*]"], {"items": [int]})


@pytest.mark.parametrize("schema,data", [
    ({"items": [str]}, {"items": "bad"}),
    ({"user": {"name": str}}, {"user": "bad"}),
])
def test_required_container_shape_is_checked(schema, data):
    assert validate(data, list(schema), schema)


@pytest.mark.parametrize("spec", [int, float])
def test_boolean_is_not_a_number(spec):
    assert validate({"value": True}, ["value"], {"value": spec})


@pytest.mark.parametrize("value,spec", [(False, bool), (0, int), (0.0, float)])
def test_false_and_zero_are_valid_values(value, spec):
    assert validate({"value": value}, ["value"], {"value": spec}) == []


@pytest.mark.parametrize("text", ["no json", "{not: valid: json}"])
def test_extraction_and_parse_errors_can_retry(text):
    feedbacks = []

    def retry(feedback):
        feedbacks.append(feedback)
        return '{"name":"ok"}'

    assert structured_output(text, ensure_keys=["name"], max_retries=1,
                             on_retry=retry) == {"name": "ok"}
    assert len(feedbacks) == 1


def test_parse_and_validation_failures_share_one_retry_budget():
    feedbacks = []
    responses = iter(['{"other":1}', '{"name":"ok"}'])

    def retry(feedback):
        feedbacks.append(feedback)
        return next(responses)

    assert structured_output("no json", ensure_keys=["name"],
                             max_retries=2, on_retry=retry) == {"name": "ok"}
    assert len(feedbacks) == 2


def test_exhaustion_reports_latest_validation_failure():
    with pytest.raises(ValidationError):
        structured_output("no json", ensure_keys=["name"], max_retries=1,
                          on_retry=lambda _: '{"other":1}')


def test_parse_retry_exhaustion_is_still_value_error():
    calls = []

    def retry(feedback):
        calls.append(feedback)
        return "still no json"

    with pytest.raises(ValueError, match="No JSON block"):
        structured_output("no json", max_retries=2, on_retry=retry)
    assert len(calls) == 2


def test_no_callback_when_retries_disabled():
    calls = []
    with pytest.raises(ValueError):
        structured_output("no json", max_retries=0, on_retry=calls.append)
    assert calls == []


def test_callback_exception_is_not_swallowed_or_retried():
    def retry(_):
        raise RuntimeError("provider failed")

    with pytest.raises(RuntimeError, match="provider failed"):
        structured_output("no json", on_retry=retry)


def test_schema_without_ensure_keys_preserves_existing_behavior():
    assert structured_output('{"qty":"wrong"}', schema={"qty": int}) == {"qty": "wrong"}
