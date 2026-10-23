"""Offline constrained-output example; install with the [pydantic] extra."""

from typing import Literal

from pydantic import BaseModel, Field

from llm_output_helper import structured_output


class Ticket(BaseModel):
    title: str = Field(min_length=3, max_length=80)
    priority: int = Field(ge=1, le=3)
    status: Literal["open", "closed"]


def main():
    feedbacks = []

    def retry(feedback):
        # Replace with a caller-owned LLM request in a real application.
        feedbacks.append(feedback)
        return '{"title":"Fix JSON parser","priority":2,"status":"open"}'

    result = structured_output(
        '{"title":"Fix JSON parser","priority":9,"status":"open"}',
        output_model=Ticket,
        model_strict=True,
        max_retries=1,
        on_retry=retry,
    )
    assert result == {"title": "Fix JSON parser", "priority": 2, "status": "open"}
    assert len(feedbacks) == 1 and "priority" in feedbacks[0]
    print("Pydantic constraints, field feedback, and bounded retry passed.")


if __name__ == "__main__":
    main()
