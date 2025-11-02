# personas/marketing_persona.py

import json

from strands import Agent, tool
from strands.models.openai import OpenAIModel

from .prompts import MARKETING_PERSONA_PROMPT


def build_marketing_persona_agent(model: OpenAIModel) -> Agent:
    return Agent(
        model=model,
        name="Marketing Persona",
        description="Marketing/growth strategist. Can plan info needs and deliver strategy.",
        system_prompt=MARKETING_PERSONA_PROMPT,
        callback_handler=None,
    )


def make_marketing_persona_tool(persona_agent: Agent):
    @tool(description="Marketing persona. mode='plan' or 'deliver'. Helps plan enrichment and generate marketing output.")
    def marketing_persona_agent(mode: str, persona_task: str, user_query: str, kb_size: int, graph_answer_json: str) -> str:
        """
        mode: "plan" or "deliver"
        persona_task: ex. 'draft_marketing_strategy', 'risk_scan'
        user_query: the original user question or request
        kb_size: current size of the knowledge base (int)
        graph_answer_json: string from graph_rag_agent(...) with fields:
            - answer
            - confidence
            - contexts
        returns:
          - if mode == 'plan': JSON string telling Supervisor if more info is needed
          - if mode == 'deliver': final stakeholder-facing output text
        """
        # just pass the raw string; persona will read it
        prompt = f"""
You are operating in MODE = {mode}.

Original user query: {user_query}
persona_task: {persona_task}
kb_size: {kb_size}

Here is the current graph-based analysis snapshot:
{graph_answer_json}

Follow the MODE rules from your system prompt.
When generating search_hints in MODE "plan", ensure they are specific to the user's query: "{user_query}".
When responding in MODE "deliver", tailor your response to address the user's query: "{user_query}".

If MODE is "plan", respond with a pure JSON object as a string.
If MODE is "deliver", respond with final stakeholder-facing narrative (no JSON).
"""
        resp = persona_agent(prompt)
        return str(resp).strip()

    return marketing_persona_agent
