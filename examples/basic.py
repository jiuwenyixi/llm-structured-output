"""Run with: python examples/basic.py (after installing the package)."""

from llm_output_helper import structured_output


def main():
    data = structured_output(
        '模型回复：｛"summary"："会议结束"，"items"：［｛"name"："写文档"｝］｝',
        schema={"summary": str, "items": [{"name": str}]},
        ensure_keys=["summary", "items[*].name"],
    )
    assert data == {"summary": "会议结束", "items": [{"name": "写文档"}]}

    callbacks = []

    def retry(feedback):
        callbacks.append(feedback)
        return '{"name":"recovered"}'

    assert structured_output("no JSON", ensure_keys=["name"], max_retries=1,
                             on_retry=retry) == {"name": "recovered"}
    assert len(callbacks) == 1
    print("Chinese JSON extraction, wildcard validation, and callback retry passed.")


if __name__ == "__main__":
    main()
