"""Request models for novel cover generation APIs."""

from typing import Any, Dict

from pydantic import BaseModel, Field


class CoverPromptDraftRequest(BaseModel):
    template_id: str = Field(default="wuxia_gold_blade")
    source_mode: str = Field(default="project_plus_custom")
    title: str = ""
    author: str = ""
    custom_elements: Dict[str, Any] = Field(default_factory=dict)
    prompt_api_config_id: str = ""
    prompt_model: str = ""


class CoverGenerateRequest(BaseModel):
    template_id: str = Field(default="wuxia_gold_blade")
    prompt: str = ""
    typography_prompt: str = ""
    element_prompt: str = ""
    source_mode: str = "project_plus_custom"
    custom_elements: Dict[str, Any] = Field(default_factory=dict)
    api_config_id: str = ""
    model: str = ""
    size: str = "1024x1536"


class CoverBatchDeleteRequest(BaseModel):
    cover_ids: list[str] = Field(default_factory=list)
