import os
import requests
from llm.base import LLM


class GeminiFlash(LLM):
 
    MODEL_URL = (
        "https://generativelanguage.googleapis.com/v1beta/"
        "models/gemini-1.5-flash:generateContent"
    )

    def __init__(self):
        if "GEMINI_API_KEY" not in os.environ:
            raise EnvironmentError("GEMINI_API_KEY not set")

        self.api_key = os.environ["GEMINI_API_KEY"]

    def complete(self, prompt: str) -> str:
        response = requests.post(
            self.MODEL_URL,
            params={"key": self.api_key},
            json={
                "contents": [
                    {"parts": [{"text": prompt}]}
                ]
            },
            timeout=30,
        )

        response.raise_for_status()

        try:
            return (
                response.json()["candidates"][0]
                ["content"]["parts"][0]["text"]
            )
        except Exception:
            raise RuntimeError("Malformed response from Gemini")
