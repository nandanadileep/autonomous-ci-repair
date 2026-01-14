from typing import Dict, Any

from agent.state import AgentState


class Agent:
    def __init__(self, reader_llm, coder_llm, tools: Dict[str, Any]):
        self.reader = reader_llm
        self.coder = coder_llm
        self.tools = tools

    def run(self, state: AgentState) -> AgentState:
        while state.can_continue():
            
            # 🛡️ GUARDRAIL 1: Auto-Pilot Patching
            # If we just generated a patch, force apply it immediately.
            last_obs = state.observations[-1] if state.observations else {}
            if last_obs.get("success") and "patch" in last_obs:
                print("🤖 AUTO-PILOT: Patch detected. Applying immediately...")
                action = {
                    "type": "tool", 
                    "name": "apply_patch", 
                    "args": {"patch": last_obs["patch"]}
                }
            
            # 🛡️ GUARDRAIL 2: Auto-Commit on Success
            # If we just ran tests and they PASSED, force commit immediately.
            # Relaxed logic: Check truthiness of success, case-insensitive output check
            last_tool = last_obs.get("tool")
            last_result_success = last_obs.get("result", {}).get("success")
            last_stdout = last_obs.get("result", {}).get("stdout", "").lower()

            # DEBUG: Print checking state
            # print(f"DEBUG CHECK: Tool={last_tool}, Success={last_result_success}, PassedInLog={'passed' in last_stdout}")

            if (last_tool == "run_tests" and 
                last_result_success and 
                "passed" in last_stdout):
                print("🤖 AUTO-PILOT: Tests passed. Committing immediately...")
                action = {
                    "type": "tool",
                    "name": "git_commit",
                    "args": {"message": "[ci-auto-fix] Fix failing tests automatically"}
                }

            # 🛡️ GUARDRAIL 3: Partial Success Retry
            # If we just ran tests, they failed, but we had applied a patch before,
            # it means the patch was incomplete. Force another patch attempt.
            elif (last_tool == "run_tests" and 
                  not last_result_success and
                  len(state.observations) >= 2):
                # Check if we applied a patch recently (within last 3 observations)
                recent_patch_applied = False
                for obs in state.observations[-3:]:
                    if obs.get("tool") == "apply_patch" and obs.get("success"):
                        recent_patch_applied = True
                        break
                
                if recent_patch_applied:
                    print("🔄 RETRY: Patch was incomplete. Forcing another fix attempt...")
                    # Count failures to show progress
                    failed_count = last_stdout.count("FAILED")
                    print(f"   Still {failed_count} test(s) failing. Generating additional patch...")
                    # Skip normal LLM reasoning, go straight to generating another patch
                    # by letting the normal flow handle it but with a hint
                    llm_output = self.think(state)
                    action = self.decide(llm_output, state)
                else:
                    # Normal LLM reasoning loop
                    llm_output = self.think(state)
                    action = self.decide(llm_output, state)


            # 🛡️ GUARDRAIL 4: Anti-Loop Forcing
            # If we've read files 2+ times in a row without generating a patch,
            # force patch generation to prevent analysis paralysis.
            elif len(state.observations) >= 3:
                # Count consecutive read_file calls
                recent_reads = 0
                for obs in reversed(state.observations[-5:]):  # Check last 5
                    if obs.get("tool") == "read_file":
                        recent_reads += 1
                    else:
                        break  # Stop at first non-read
                
                if recent_reads >= 2:
                    print("⚡ FORCE: Too many file reads. Forcing patch generation...")
                    print(f"   Detected {recent_reads} consecutive reads. Taking action now.")
                    
                    # Extract error and file content from observations
                    build_log_obs = next((o for o in state.observations if 
                                         o.get("result", {}).get("path") == "build.log"), None)
                    test_file_obs = next((o for o in reversed(state.observations) if 
                                         o.get("result", {}).get("path", "").endswith("test_utils.py")), None)
                    
                    if build_log_obs and test_file_obs:
                        error = build_log_obs.get("result", {}).get("content", "")
                        code = test_file_obs.get("result", {}).get("content", "")
                        file_path = test_file_obs.get("result", {}).get("path", "tests/test_utils.py")
                        
                        # Force generate_patch action
                        action = {
                            "type": "generate_patch",
                            "file_path": file_path,
                            "code": code,
                            "error": error
                        }
                    else:
                        # Fallback to normal flow if we can't extract needed info
                        llm_output = self.think(state)
                        action = self.decide(llm_output, state)
                else:
                    # Normal LLM reasoning loop
                    llm_output = self.think(state)
                    action = self.decide(llm_output, state)

            else:
                # Normal LLM reasoning loop
                llm_output = self.think(state)
                action = self.decide(llm_output, state)

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
        prompt = f"""You are an autonomous CI repair agent that fixes failing tests.

Goal: {state.goal}
Attempts: {state.attempts}/{state.max_attempts}

Previous observations:
{state.observations}

CRITICAL WORKFLOW RULES:
1. ALWAYS read the actual test file BEFORE generating any patch
2. NEVER guess or hallucinate what code looks like
3. Use the EXACT file contents you read to generate patches
4. Generate patches ONLY after reading the file
5. Apply patches, then run tests, then commit if passing

ALLOWED ACTIONS:

1. Read a file (USE THIS FIRST before generating patches):
{{"type": "tool", "name": "read_file", "args": {{"path": "<file_path>"}}}}

2. Generate a patch (ONLY after reading the file):
{{"type": "generate_patch", "file_path": "<file_path>", "code": "<actual_file_contents_you_read>", "error": "<error_from_build_log>"}}

3. Apply a patch (use the patch you just generated):
{{"type": "tool", "name": "apply_patch", "args": {{"patch": "<unified_diff>"}}}}

4. Run tests (to verify your fix worked):
{{"type": "tool", "name": "run_tests", "args": {{}}}}

5. Commit fix (ONLY if tests passed):
{{"type": "tool", "name": "git_commit", "args": {{"message": "[ci-auto-fix] <description>"}}}}

EXAMPLE WORKFLOW:
- Step 1: Read build.log → See "tests/test_utils.py:4: assert add(1,2) == 192"
- Step 2: Read tests/test_utils.py → Get ACTUAL file contents
- Step 3: Generate patch using ACTUAL contents (not guessed!)
- Step 4: Apply the patch
- Step 5: Run tests to verify
- Step 6: If tests pass, commit with [ci-auto-fix] message

DECISION LOGIC (Check observations carefully!):
- Look at your observations - do you see a 'patch' key in any observation? → If YES, apply that patch NOW!
- If you haven't read the failing test file yet → Read it first!
- If you've read the file but no patch in observations → Generate patch with EXACT file contents
- If you just applied a patch but tests not verified → Run tests
- If tests passed (exit code 0) → Commit with [ci-auto-fix] message
- If tests still fail → Read file again and generate better patch

CRITICAL: If you see {{'success': True, 'patch': '...'}} in observations, your NEXT action MUST be apply_patch!

CRITICAL INSTRUCTIONS:
- Do NOT output markdown code blocks (no ```json).
- Do NOT write explanations or thoughts.
- Output ONLY the following format:
ACTION: {{"type": "...", ...}}
"""


        return self.reader.complete(prompt)


    def decide(self, llm_output: str, state: AgentState) -> dict:
        """Parse the LLM output to determine the next action."""
        import json
        import re

        json_str = ""
        
        # Strategy 1: Look for ACTION: prefix
        if "ACTION:" in llm_output:
            try:
                candidate = llm_output.split("ACTION:", 1)[1].strip()
                # Remove markdown code blocks if present
                candidate = re.sub(r"^```json", "", candidate).strip()
                candidate = re.sub(r"^```", "", candidate).strip()
                if candidate.endswith("```"):
                    candidate = candidate[:-3].strip()
                json_str = candidate
            except Exception:
                pass

        # Strategy 2: If finding by prefix failed, look for the first {...} block
        if not json_str:
            # Use re.DOTALL to allow '.' to match newlines within the JSON block
            matches = re.search(r"(\{.*\})", llm_output, re.DOTALL)
            if matches:
                json_str = matches.group(1)

        if not json_str:
             # If no JSON string was found by either strategy, return an unknown action
             print("=" * 80)
             print("CRITICAL DEBUG: LLM OUTPUT PARSING FAILED")
             print("Raw LLM Output:")
             print(llm_output)
             print("=" * 80)
             return {"type": "unknown", "error": "No JSON action found in output"}

        # Attempt to parse the found JSON string
        try:
            json_str = json_str.strip()
            action = json.loads(json_str)
            return action
        except json.JSONDecodeError as e:
            # If JSON parsing fails, return an error action with details
            print(f"DECIDE JSON PARSE ERROR: {e}")
            print("Output was:", llm_output)
            return {"type": "unknown", "error": f"Invalid JSON: {str(e)}", "raw": json_str}
        except Exception as e:
            # Catch any other unexpected errors during parsing
            print(f"DECIDE PARSE ERROR: {e}")
            print(llm_output)
            return {"type": "unknown", "error": f"Unexpected error during parsing: {str(e)}", "raw": json_str}




    def act(self, action: Dict[str, Any], state: AgentState) -> Dict[str, Any]:

        action_type = action.get("type")

        if action_type == "tool":
            return self._run_tool(action, state)

        if action_type == "generate_patch":
            return self._generate_patch(action, state)

        # Handle direct tool invocations (e.g., {"type": "read_file", "args": {...}})
        # Convert to wrapped format and delegate to _run_tool
        if action_type in ["read_file", "run_tests", "apply_patch", "git_commit"]:
            wrapped_action = {
                "type": "tool",
                "name": action_type,
                "args": action.get("args", {})
            }
            return self._run_tool(wrapped_action, state)
    
        print("=" * 80)
        print("CRITICAL DEBUG: Unknown action type received")
        print(f"Action dict: {action}")
        print(f"Action type: {action_type}")
        print("=" * 80)
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

CRITICAL: Generate a SINGLE unified diff patch that fixes ALL failing test assertions shown in the error above.
The patch must:
1. Fix EVERY failing assertion (not just one of them)
2. Use the EXACT function names and line structure from the code above
3. Change ONLY the incorrect expected values to match what the function actually returns
4. Be in standard unified diff format (no markdown, no code blocks)
5. The context lines (lines starting with space) MUST match the provided code EXACTLY

Example format (fixing multiple assertions):
--- {file_path}
+++ {file_path}
@@ -3,7 +3,7 @@
 def test_add():
     assert add(1, 2) == 3
-    assert add(424, 2) == 428
+    assert add(424, 2) == 426
-    assert add(987, 0) == 988
+    assert add(987, 0) == 987

Output ONLY the unified diff patch that fixes ALL errors, nothing else."""

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

