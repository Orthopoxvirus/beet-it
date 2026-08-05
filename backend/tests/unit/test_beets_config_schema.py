"""Unit tests for the beets config Pydantic schemas."""

import pytest
from pydantic import ValidationError

from app.schemas.beets_config import ImportConfig


class TestImportConfigResume:
    """`resume` must accept true/false/yes/no/ask per beets docs.

    See https://beets.readthedocs.io/en/stable/reference/config.html#resume
    """

    def test_resume_accepts_true(self):
        cfg = ImportConfig(resume=True)
        assert cfg.resume is True

    def test_resume_accepts_false(self):
        cfg = ImportConfig(resume=False)
        assert cfg.resume is False

    def test_resume_accepts_yes_string(self):
        """YAML `yes` parses to bool True already, but accept the string form too."""
        cfg = ImportConfig(resume="yes")
        assert cfg.resume is True

    def test_resume_accepts_no_string(self):
        cfg = ImportConfig(resume="no")
        assert cfg.resume is False

    def test_resume_accepts_ask_string(self):
        """`ask` is the interactive-prompt mode beets writes after a failed import."""
        cfg = ImportConfig(resume="ask")
        assert cfg.resume == "ask"

    def test_resume_case_insensitive(self):
        assert ImportConfig(resume="ASK").resume == "ask"
        assert ImportConfig(resume="Yes").resume is True

    def test_resume_rejects_garbage(self):
        with pytest.raises(ValidationError):
            ImportConfig(resume="maybe")

    def test_resume_rejects_integer(self):
        with pytest.raises(ValidationError):
            ImportConfig(resume=42)

    def test_resume_default(self):
        """Default stays True so existing configs without an explicit resume value are unaffected."""
        assert ImportConfig().resume is True
