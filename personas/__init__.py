# personas/__init__.py

from .prompts import MARKETING_PERSONA_PROMPT, FINANCE_PERSONA_PROMPT, ACADEMIC_PERSONA_PROMPT
from .marketing_persona import build_marketing_persona_agent, make_marketing_persona_tool
from .finance_persona import build_finance_persona_agent, make_finance_persona_tool
from .academic_persona import build_academic_persona_agent, make_academic_persona_tool

__all__ = [
    "MARKETING_PERSONA_PROMPT",
    "FINANCE_PERSONA_PROMPT",
    "ACADEMIC_PERSONA_PROMPT",
    "build_marketing_persona_agent",
    "make_marketing_persona_tool",
    "build_finance_persona_agent",
    "make_finance_persona_tool",
    "build_academic_persona_agent",
    "make_academic_persona_tool",
]
