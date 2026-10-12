"""Keep persisted user text compatible with JSON, SQLite and XLSX/XML exports."""
import re

from pydantic import BaseModel, field_validator


UNSUPPORTED_CHARACTERS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]")


class SafeInputModel(BaseModel):
    @field_validator("*", mode="before")
    @classmethod
    def reject_unsupported_characters(cls, value):
        if isinstance(value, str) and UNSUPPORTED_CHARACTERS.search(value):
            raise ValueError("Unsupported characters in user text")
        return value
