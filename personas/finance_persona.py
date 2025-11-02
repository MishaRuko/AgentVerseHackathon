# personas/finance_persona.py

import json
from strands import Agent, tool
from strands.models.openai import OpenAIModel
from .prompts import FINANCE_PERSONA_PROMPT

def build_finance_persona_agent(model: OpenAIModel) -> Agent:
    return Agent(
        model=model,
        name="Finance Persona",
        description="Finance/investment analyst. Can plan info needs and deliver financial analysis.",
        system_prompt=FINANCE_PERSONA_PROMPT,
        callback_handler=None,
    )

def make_finance_persona_tool(persona_agent: Agent):
    @tool(description="Finance persona. mode='plan' or 'deliver'. Helps plan enrichment and generate financial output.")
    def finance_persona_agent(mode: str, persona_task: str, kb_size: int, graph_answer_json: str) -> str:
        """
        mode: "plan" or "deliver"
        persona_task: ex. 'investment_analysis', 'risk_assessment'
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

persona_task: {persona_task}
kb_size: {kb_size}

Here is the current graph-based analysis snapshot:
{graph_answer_json}

Follow the MODE rules from your system prompt.
If MODE is "plan", respond with a pure JSON object as a string.
If MODE is "deliver", respond with final stakeholder-facing narrative (no JSON).
"""
        resp = persona_agent(prompt)
        return str(resp).strip()

    return finance_persona_agent
