from typing import Dict, Any

from agent.state import AgentState


class Agent:
    def __init__(self, reader_llm, coder_llm, tools: Dict[str, Any]):
        self.reader = reader_llm
        self.coder = coder_llm
        self.tools = tools

    def run(self, state: AgentState) -> AgentState:
        while state.can_continue():
            thought = self.think(state)
            action = self.decide(thought, state)

            if action is None:
                state.fail("Failed to decide next action")
                break

            observation = self.act(action, state)
            state.record_observation(observation)

            if observation.get("terminal_success"):
                state.mark_success()
                break

            state.increment_attempts()

        if not state.success and state.failure_reason is None:
            state.fail("Agent stopped without success")

        return state

    def think(self, state: AgentState) -> str:
        prompt = f"""
You are an autonomous CI repair agent.

Goal:
{state.goal}

Attempts:
{state.attempts}/{state.max_attempts}

Observations so far:
{state.observations}

You MUST choose exactly ONE action.

Allowed actions (JSON only):

1. Read a file:
{{
  "type": "tool",
  "name": "read_file",
  "args": {{"path": "<file_path>"}}
}}

2. Generate a patch:
{{
  "type": "generate_patch",
  "code": "<file_contents>",
  "error": "<error_description>"
}}

3. Apply a patch:
{{
  "type": "tool",
  "name": "apply_patch",
  "args": {{"patch": "<unified_diff>"}}
}}

4. Run tests:
{{
  "type": "tool",
  "name": "run_tests",
  "args": {{}}
}}

5. Commit fix (ONLY if tests passed):
{{
  "type": "tool",
  "name": "git_commit",
  "args": {{"message": "<commit_message>"}}
}}

Rules:
- Output EXACTLY one ACTION JSON
- No explanations
- No extra text
- No markdown

Respond ONLY in this format:

THOUGHT: <one sentence>
ACTION: <json>
"""


        return self.reader.complete(prompt)

    def decide(self, llm_output: str, state: AgentState) -> Dict[str, Any] | None:

        try:
            lines = llm_output.splitlines()
            action_line = next(l for l in lines if l.startswith("ACTION:"))
            action = action_line.replace("ACTION:", "").strip()
            return eval(action)  # controlled format
        except Exception as e:
            print("DECIDE PARSE ERROR:", llm_output)
            return None



    def act(self, action: Dict[str, Any], state: AgentState) -> Dict[str, Any]:

        action_type = action.get("type")

        if action_type == "tool":
            return self._run_tool(action, state)

        if action_type == "generate_patch":
            return self._generate_patch(action, state)

        return {"success": False, "error": "Unknown action type"}

    def _run_tool(self, action: Dict[str, Any], state: AgentState) -> Dict[str, Any]:
        tool_name = action.get("name")
        tool_args = action.get("args", {})

        tool = self.tools.get(tool_name)
        if tool is None:
            return {"success": False, "error": f"Unknown tool: {tool_name}"}

        result = tool.run(**tool_args)

        if tool_name == "apply_patch" and result:
            state.record_file_touch(tool_args.get("path", ""))

        return {
            "success": bool(result),
            "tool": tool_name,
            "result": result
        }


    def _generate_patch(self, action: Dict[str, Any], state: AgentState) -> Dict[str, Any]:
        """
        Use the coder LLM to generate a patch.
        """
        code = action.get("code")
        error = action.get("error")

        prompt = f"""
        You are a senior Python engineer.

        Bug description:
        {error}

        Code:
        ```python
        {code}
        Return ONLY a unified diff patch.
        """
        patch = self.coder.complete(prompt)

        if not patch:
            return {"success": False, "error": "Patch generation failed"}

        return {
            "success": True,
            "patch": patch
        }
