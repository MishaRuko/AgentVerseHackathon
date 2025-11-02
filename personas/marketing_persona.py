# personas/marketing_persona.py

import json
from strands import Agent, tool
from strands.models.openai import OpenAIModel

from .prompts import MARKETING_PERSONA_PROMPT

def build_marketing_persona_agent(model: OpenAIModel) -> Agent:
    """
    Create and return the marketing persona Agent.
    This Agent can handle multiple 'task' modes.
    """
    return Agent(
        model=model,
        name="Marketing Persona",
        description="Turns analysis into marketing strategy, positioning, and risk guidance.",
        system_prompt=MARKETING_PERSONA_PROMPT,
        callback_handler=None,
    )


def make_marketing_persona_tool(persona_agent: Agent):
    """
    Wrap the marketing persona Agent as a callable tool for the Supervisor.

    The tool accepts:
    - task: str  (e.g. 'draft_marketing_strategy')
    - answer_json: str (JSON string from graph_rag_agent with 'answer', 'contexts', etc.)

    It returns stakeholder-facing text, not JSON.
    """

    @tool(description="Marketing persona. Input: task + answer_json. Returns stakeholder-facing marketing output.")
    def marketing_persona_agent(task: str, answer_json: str) -> str:
        try:
            payload = json.loads(answer_json)
        except Exception:
            payload = { "answer": answer_json }

        persona_prompt = f"""
Task: {task}

Here is the structured analysis you are working from:
{json.dumps(payload, indent=2)}

Follow your task definition from your system prompt.
Output something a marketing lead can drop directly into a deck or brief.
Do not invent numbers. Do not reveal internal tool names.
""".strip()

        resp = persona_agent(persona_prompt)
        return str(resp).strip()

    return marketing_persona_agent
