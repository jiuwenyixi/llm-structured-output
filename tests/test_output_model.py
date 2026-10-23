"""Observable model constraints, retry boundaries, and result contracts."""

from typing import List, Literal, Optional

import pytest

pydantic = pytest.importorskip("pydantic", minversion="2")
from pydantic import BaseModel, ConfigDict, Field, RootModel, field_validator, model_validator

from llm_output_helper import ValidationError, structured_output


class Ticket(BaseModel):
    title: str = Field(min_length=3, max_length=30)
    priority: int = Field(ge=1, le=3)
    status: Literal["open", "closed"]


@pytest.mark.parametrize("text", [
    '{"title":"ok","priority":2,"status":"open"}',
    '{"title":"valid","priority":4,"status":"open"}',
    '{"title":"valid","priority":2,"status":"unknown"}',
    '{"priority":2,"status":"open"}',
])
def test_full_model_constraints_apply_without_ensure_keys(text):
    with pytest.raises(ValidationError):
        structured_output(text, output_model=Ticket, max_retries=0)


def test_constraints_retry_once_and_return_a_plain_dict():
    feedbacks = []

    def retry(feedback):
        feedbacks.append(feedback)
        return '{"title":"fixed","priority":2,"status":"open"}'

    result = structured_output('{"title":"bad","priority":9,"status":"open"}',
                               output_model=Ticket, max_retries=1, on_retry=retry)
    assert type(result) is dict
    assert result == {"title": "fixed", "priority": 2, "status": "open"}
    assert len(feedbacks) == 1 and "priority" in feedbacks[0]


def test_parse_model_and_ensure_failures_share_one_budget():
    feedbacks = []
    responses = iter([
        '{"title":"valid","priority":9,"status":"open"}',
        '{"title":"valid","priority":2,"status":"open"}',
    ])

    def retry(feedback):
        feedbacks.append(feedback)
        return next(responses)

    with pytest.raises(ValidationError, match="extra"):
        structured_output("no JSON", output_model=Ticket, ensure_keys=["extra"],
                          max_retries=2, on_retry=retry)
    assert len(feedbacks) == 2


def test_model_coercion_defaults_and_strict_override():
    class Count(BaseModel):
        count: int

    assert structured_output('{"count":"2"}', output_model=Count) == {"count": 2}
    with pytest.raises(ValidationError):
        structured_output('{"count":"2"}', output_model=Count, model_strict=True)


def test_strict_model_configuration_is_preserved_by_default():
    class Count(BaseModel):
        model_config = ConfigDict(strict=True)
        count: int

    with pytest.raises(ValidationError):
        structured_output('{"count":"2"}', output_model=Count)
    assert structured_output('{"count":"2"}', output_model=Count,
                             model_strict=False) == {"count": 2}


def test_aliases_defaults_and_ensure_keys_use_normalized_field_names():
    class User(BaseModel):
        name: str = Field(alias="display_name")
        active: bool = True
        note: Optional[str] = None

    assert structured_output('{"display_name":"Alice"}', output_model=User,
                             ensure_keys=["name", "active", "note"]) == {
        "name": "Alice", "active": True, "note": None,
    }


def test_validation_alias_guides_selection():
    class User(BaseModel):
        name: str = Field(validation_alias="display_name")

    result = structured_output('{"other":1} {"display_name":"Alice"} {"other":2}',
                               output_model=User)
    assert result == {"name": "Alice"}


def test_model_fields_guide_selection_without_an_explicit_schema():
    assert structured_output('{"other":1} {"title":"valid","priority":2,"status":"open"} {"other":2}',
                             output_model=Ticket)["title"] == "valid"


def test_explicit_selection_schema_remains_supported():
    result = structured_output('{"other":1} {"title":"valid","priority":2,"status":"open"}',
                               schema={"title": str}, output_model=Ticket)
    assert result["title"] == "valid"


def test_nested_model_error_paths_are_usable():
    class Batch(BaseModel):
        tickets: List[Ticket] = Field(min_length=1)

    with pytest.raises(ValidationError) as exc:
        structured_output('{"tickets":[{"title":"valid","priority":9,"status":"open"}]}',
                          output_model=Batch)
    assert "tickets[0].priority" in str(exc.value)
    with pytest.raises(ValidationError):
        structured_output('{"tickets":[]}', output_model=Batch)


def test_root_array_returns_an_array():
    Model = RootModel[List[int]]
    assert structured_output('[1,2]', output_model=Model) == [1, 2]
    with pytest.raises(ValidationError):
        structured_output('[1,"bad"]', output_model=Model)


def test_extra_field_policy_belongs_to_the_model():
    class Closed(BaseModel):
        model_config = ConfigDict(extra="forbid")
        count: int

    with pytest.raises(ValidationError):
        structured_output('{"count":2,"unexpected":3}', output_model=Closed)


def test_custom_cross_field_rule_uses_the_same_retry_path():
    class Window(BaseModel):
        start: int
        end: int

        @model_validator(mode="after")
        def ordered(self):
            if self.start >= self.end:
                raise ValueError("start must precede end")
            return self

    assert structured_output('{"start":4,"end":2}', output_model=Window,
                             on_retry=lambda _: '{"start":1,"end":3}') == {"start": 1, "end": 3}


def test_programming_error_in_custom_validator_does_not_trigger_model_calls():
    class Broken(BaseModel):
        count: int

        @field_validator("count")
        @classmethod
        def broken(cls, value):
            raise TypeError("programming error")

    calls = []
    with pytest.raises(TypeError, match="programming error"):
        structured_output('{"count":2}', output_model=Broken, on_retry=calls.append)
    assert calls == []


def test_feedback_is_bounded_without_raw_input_values():
    class Batch(BaseModel):
        values: List[int]

    with pytest.raises(ValidationError) as exc:
        structured_output('{"values":[' + ','.join(['"PRIVATE_VALUE"'] * 20) + ']}',
                          output_model=Batch)
    assert len(exc.value.errors) == 8
    assert all(len(error) <= 300 for error in exc.value.errors)
    assert "PRIVATE_VALUE" not in str(exc.value)


@pytest.mark.parametrize("model", [dict, 42, Ticket(title="valid", priority=1, status="open")])
def test_invalid_model_configuration_fails_before_retries(model):
    calls = []
    with pytest.raises(TypeError, match="BaseModel class"):
        structured_output("no JSON", output_model=model, on_retry=calls.append)
    assert calls == []


def test_invalid_strict_configuration_fails_before_retries():
    with pytest.raises(TypeError, match="model_strict"):
        structured_output("no JSON", output_model=Ticket, model_strict="yes")


def test_python_mode_dump_preserves_native_types():
    from datetime import date

    class Event(BaseModel):
        day: date

    assert structured_output('{"day":"2026-10-24"}', output_model=Event) == {
        "day": date(2026, 10, 24),
    }
