import os
import requests
from llm.base import LLM


class LlamaGroq(LLM):

    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self):
        if "GROQ_API_KEY" not in os.environ:
            raise EnvironmentError("GROQ_API_KEY not set")

        self.api_key = os.environ["GROQ_API_KEY"]

    def complete(self, prompt: str) -> str:
        response = requests.post(
            self.API_URL,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0,
            },
            timeout=30,
        )

        response.raise_for_status()

        try:
            return response.json()["choices"][0]["message"]["content"]
        except Exception:
            raise RuntimeError("Malformed response from Groq")
