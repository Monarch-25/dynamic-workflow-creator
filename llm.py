"""
Shared LLM configuration for DWC.
"""

from __future__ import annotations

import os
from typing import Any, Dict, Optional

DWC_BEDROCK_MODEL_ID = "us.anthropic.claude-sonnet-4-20250514-v1:0"


def build_chat_bedrock_converse(
    *,
    region_name: Optional[str] = None,
    temperature: float = 0.0,
) -> Any:
    """
    Build a ChatBedrockConverse client pinned to the DWC default model.
    """

    from langchain_aws import ChatBedrockConverse

    resolved_region = region_name or os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION")
    kwargs: Dict[str, Any] = {
        "model": DWC_BEDROCK_MODEL_ID,
        "temperature": temperature,
    }
    if resolved_region:
        kwargs["region_name"] = resolved_region
    return ChatBedrockConverse(**kwargs)
