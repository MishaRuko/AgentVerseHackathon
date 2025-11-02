# personas/finance_persona.py

import json
from strands import Agent, tool
from strands.models.openai import OpenAIModel

from .prompts import FINANCE_PERSONA_PROMPT

def build_finance_persona_agent(model: OpenAIModel) -> Agent:
    """
    Create and return the finance persona Agent.
    This Agent can handle multiple 'task' modes.
    """
    return Agent(
        model=model,
        name="Finance Persona",
        description="Frames analysis in investor / exec terms: risk, sentiment, competitive posture.",
        system_prompt=FINANCE_PERSONA_PROMPT,
        callback_handler=None,
    )


def make_finance_persona_tool(persona_agent: Agent):
    """
    Wrap the finance persona Agent as a callable tool for the Supervisor.

    The tool accepts:
    - task: str (e.g. 'investor_opportunity_scan')
    - answer_json: str (JSON string from graph_rag_agent with 'answer', etc.)

    Returns stakeholder-facing narrative for leadership / investors.
    """

    @tool(description="Finance persona. Input: task + answer_json. Returns exec/board-facing output.")
    def ib_persona_agent(task: str, answer_json: str) -> str:
        try:
            payload = json.loads(answer_json)
        except Exception:
            payload = { "answer": answer_json }

        persona_prompt = f"""
Task: {task}

Here is the structured analysis you are working from:
{json.dumps(payload, indent=2)}

Follow your task definition from your system prompt.
Output should be boardroom-safe executive language.
No invented metrics. No internal tool names.
""".strip()

        resp = persona_agent(persona_prompt)
        return str(resp).strip()

    return ib_persona_agent
