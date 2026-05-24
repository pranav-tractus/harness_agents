"""Pydantic schemas for the validation (post-processing) LLM layer."""

from typing import List

from pydantic import BaseModel, Field

from core.models import SOExtractContractList


class ValidationIssue(BaseModel):
    severity: str = Field(description='One of "info", "warning", "error"')
    field_path: str = Field(description="JSON path e.g. data[0].items[0].unit_price")
    issue: str = Field(description="What is wrong or ambiguous")
    suggestion: str = Field(default="", description="Recommended fix grounded in chat")


class SOValidationResult(BaseModel):
    """Validation LLM output: refined contract plus audit trail."""

    extraction: SOExtractContractList = Field(
        description="Corrected SOExtractContractList; date fields are overwritten from raw by code"
    )
    issues: List[ValidationIssue] = Field(default_factory=list)
    notes: str = Field(default="", description="Brief rationale for major corrections")
