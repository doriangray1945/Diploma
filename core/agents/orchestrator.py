from core.llm.base import LLMProvider
from core.schemas import Complexity, Message, Role


CLASSIFICATION_PROMPT = """You are a request complexity classifier. Determine if the user's request is SIMPLE or COMPLEX.

SIMPLE — can be solved with a single tool call or a short chain of calls:
- Searching for something
- Getting details about an item
- Performing a single action
- Asking a question

COMPLEX — requires planning, multiple searches, and combining results:
- Composing a set of items that work together
- Comparing multiple options and making a recommendation
- Multi-step workflows with dependencies between steps

Respond with ONLY one word: SIMPLE or COMPLEX"""


class OrchestratorAgent:
    """Classifies request complexity and routes to the right handler."""

    def __init__(self, llm: LLMProvider):
        self.llm = llm

    async def classify(self, user_message: str) -> Complexity:
        # Short messages are almost always simple
        if len(user_message) < 100:
            return Complexity.SIMPLE

        messages = [
            Message(role=Role.SYSTEM, content=CLASSIFICATION_PROMPT),
            Message(role=Role.USER, content=user_message),
        ]

        response = await self.llm.chat(messages, temperature=0.0)

        content = ""
        if "message" in response:
            content = response["message"].get("content", "").strip().upper()

        if "COMPLEX" in content:
            return Complexity.COMPLEX
        return Complexity.SIMPLE