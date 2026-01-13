class LLM:
    def complete(self, prompt: str) -> str:
        raise NotImplementedError("LLM must implement complete()")
