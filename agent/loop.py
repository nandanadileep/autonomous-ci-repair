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
  "file_path": "<file_path>",
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
        code = action.get("code", "")
        error = action.get("error", "")
        file_path = action.get("file_path", "")

        prompt = f"""You are a senior Python engineer fixing test failures.

File: {file_path}

Current code:
```python
{code}
```

Error from test output:
{error}

Generate a unified diff patch to fix the test assertions. The patch must:
1. Use the EXACT function names from the code above
2. Fix the assertion values to match what the function actually returns
3. Be in standard unified diff format (no markdown, no code blocks)

Example format:
--- {file_path}
+++ {file_path}
@@ -3,5 +3,5 @@
 def test_add():
-    assert add(1, 2) == 192
+    assert add(1, 2) == 3

Output ONLY the unified diff patch, nothing else."""

        patch = self.coder.complete(prompt)

        if not patch:
            return {"success": False, "error": "Patch generation failed"}

        # Strip markdown code blocks if present  
        patch = patch.strip()
        if patch.startswith("```"):
            lines = patch.split("\n")
            # Remove first and last lines if they're code block markers
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            patch = "\n".join(lines)

        return {
            "success": True,
            "patch": patch
        }

