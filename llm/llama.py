import os
import requests
import time
from llm.base import LLM


class LlamaGroq(LLM):

    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def __init__(self):
        if "GROQ_API_KEY" not in os.environ:
            raise EnvironmentError("GROQ_API_KEY not set")

        self.api_key = os.environ["GROQ_API_KEY"]

    def complete(self, prompt: str) -> str:
        max_retries = 3
        timeout = 60  # Increased from 30 to 60 seconds
        
        for attempt in range(max_retries):
            try:
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
                    timeout=timeout,
                )

                response.raise_for_status()

                try:
                    return response.json()["choices"][0]["message"]["content"]
                except Exception as e:
                    raise RuntimeError(f"Malformed response from Groq: {e}")
                    
            except requests.exceptions.Timeout:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt  # Exponential backoff: 1s, 2s, 4s
                    print(f"⏱️  Groq API timeout, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError(f"Groq API timed out after {max_retries} attempts")
                    
            except requests.exceptions.RequestException as e:
                if attempt < max_retries - 1:
                    wait_time = 2 ** attempt
                    print(f"⚠️  Groq API error: {e}, retrying in {wait_time}s... (attempt {attempt + 1}/{max_retries})")
                    time.sleep(wait_time)
                    continue
                else:
                    raise RuntimeError(f"Groq API failed after {max_retries} attempts: {e}")
        
        raise RuntimeError("Failed to complete API request")

