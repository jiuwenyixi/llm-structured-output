"""Base installation must work without importing Pydantic."""

import builtins
import subprocess
import sys
from types import SimpleNamespace

import pytest

from llm_output_helper import structured_output


def test_base_import_does_not_eagerly_load_pydantic():
    subprocess.run([sys.executable, "-c", "import sys; import llm_output_helper; "
                    "assert 'pydantic' not in sys.modules; "
                    "assert llm_output_helper.structured_output('{\"ok\":true}') == {'ok':True}"],
                   check=True)


def test_missing_dependency_has_install_guidance_and_no_retry(monkeypatch):
    real_import = builtins.__import__

    def blocked(name, *args, **kwargs):
        if name == "pydantic":
            raise ImportError("dependency unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", blocked)
    calls = []
    with pytest.raises(ImportError, match=r"llm-output-helper\[pydantic\]"):
        structured_output("no JSON", output_model=object, on_retry=calls.append)
    assert calls == []


def test_pydantic_v1_is_explicitly_rejected(monkeypatch):
    legacy = SimpleNamespace(BaseModel=type("LegacyModel", (), {}), ValidationError=Exception)
    monkeypatch.setitem(sys.modules, "pydantic", legacy)
    with pytest.raises(ImportError, match="v1 is not supported"):
        structured_output("no JSON", output_model=object)


def test_strict_option_requires_a_model():
    with pytest.raises(TypeError, match="requires output_model"):
        structured_output('{"ok":true}', model_strict=True)
