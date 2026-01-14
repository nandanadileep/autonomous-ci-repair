import os
from google import genai
from llm.base import LLM


class GeminiFlash(LLM):
    """
    Gemini Reader LLM using the new google.genai SDK.
    """

    def __init__(self):
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY not set")

        # Create client (NO configure(), this is the new API)
        self.client = genai.Client(api_key=api_key)

        # Use gemini-2.0-flash-exp (10 req/min limit, but it works)
        self.model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-exp")

    def complete(self, prompt: str) -> str:
        response = self.client.models.generate_content(
            model=self.model,
            contents=prompt,
        )
        return response.text
