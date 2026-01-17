# Autonomous CI Repair 

An autonomous agent that detects failing CI builds, diagnoses test failures from logs, generates code fixes using multi-model LLM reasoning, verifies them, and commits fixes back to the repository automatically.


<p align="center">
  <a href="https://github.com/nandanadileep/autonomous-ci-repair/blob/main/Screen%20Recording%202026-01-15%20at%201.43.12%E2%80%AFAM.mov">
    <img src="https://img.shields.io/badge/▶%20Watch-Demo-blue?style=for-the-badge">
  </a>
</p>


##  How to Use This in Your Repository

### Step 1: Add a GitHub Actions Workflow

Create the following file in your repository: `.github/workflows/ci.yml`

```yaml
name: CI with Self-Healing

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: write

jobs:
  test:
    uses: nandanadileep/autonomous-ci-repair/.github/workflows/self_healing.yml@main
    with:
      python-version: "3.11"
      test-command: "pytest -v"
    secrets:
      GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
      GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
```

### Step 2: Add Required Secrets

Go to **GitHub Settings → Secrets → Actions** and add:

- `GEMINI_API_KEY`
- `GROQ_API_KEY`

### Step 3: Push Code

When CI tests fail, the agent automatically:

1. ✅ Analyzes failure logs
2. ✅ Reads relevant source and test files
3. ✅ Generates a fix using LLM reasoning
4. ✅ Verifies the fix by re-running tests
5. ✅ Commits the fix with `[ci-auto-fix]`
6. ✅ Triggers CI again

**No human intervention required.**

---

##  What This Agent Does

When a CI build fails:

- Parses test logs to identify the root cause
- Reads relevant files from the repository
- Uses LLM reasoning to generate a patch
- Applies the patch using git
- Runs tests to verify the fix
- Commits **only if tests pass**

If the fix fails, the agent exits with a clear failure reason.

---

##  Architecture Overview

### Agent Loop (`agent/loop.py`)
- Explicit reasoning to action loop
- Deterministic and debuggable execution
- Enforces safety limits

### State Manager (`agent/state.py`)
- Tracks attempts, file edits, and observations
- Defines termination conditions

### LLM Providers (`llm/`)
- **Reader model** for failure analysis and planning
- **Coder model** for patch generation

### Tools (`tools/`)
- Read files
- Apply git patches
- Run tests
- Commit changes

---

##  Safety Features

- ✅ Maximum attempt limit (default: 3)
- ✅ Tests must pass before committing
- ✅ Commits tagged with `[ci-auto-fix]` to prevent infinite loops
- ✅ Explicit failure states
- ✅ File modification tracking

##  Core Intelligence & Robustness

The agent is designed to overcome common pitfalls of LLM-based coding tools:

### 1. Hyper-Fuzzy Patching (Gemini-Proof)
LLMs often hallucinate context values (e.g., "assert x == 426" when the file has "assert x == 428"). 
Standard patch application fails here. This agent uses **Hyper-Fuzzy Patching**:
- If exact match fails, it uses `difflib.SequenceMatcher` to find the code block with >80% similarity.
- This allows the agent to apply fixes even if it "misremembers" the context lines, making it extremely resilient to Model Hallucinations.
- **Fallback Logic**: Tries strict `git apply` first for safety, then falls back to fuzzy content matching to partial-apply valid fixes.

### 2. Auto-Pilot Guardrails (Deterministic Workflow)
To prevent "AI indecision," the agent enforces a strict state machine for critical steps:
- **Auto-Apply**: If a patch is generated, it is applied *immediately* without further debate.
- **Auto-Commit**: If tests pass after a fix, the agent *immediately* commits the results.
This ensures the agent never gets stuck in a "thinking loop" when the path forward is clear.

### 3. CI Integration
- **Exit Code Capture**: Uses `PIPESTATUS` to correctly capture test failures even when piped through other commands, ensuring the self-healing process triggers reliably.

---

## 🛠️ Engineering Challenges & Solutions

Building a reliable autonomous agent revealed that **LLMs fail in predictable ways**. Here are the 8 distinct failure modes discovered and how they were systematically resolved:

### Challenge 1: Additive Patches Creating Duplicates ❌
**Problem:** LLM generated patches that *added* new lines instead of *replacing* wrong ones.

**Example of failure:**
```python
# Original (wrong):
assert add(987, 0) == 1000

# LLM generates additive patch:
+ assert add(987, 0) == 987

# Result: DUPLICATE FUNCTIONS! 
def test_add():
def test_add():  # Corrupted file
    assert add(987, 0) == 1000
    assert add(987, 0) == 987
```

**✅ Solution: Patch Validator & Auto-Transformer**
```python
def _fix_additive_patch(patch, original_code):
    # Detect patches with only + lines (no - lines)
    if has_additions and not has_removals:
        # Find original wrong line in code
        # Convert to replacement patch automatically
        return f"-{original_line}\n+{corrected_line}"
```
**Impact:** Prevented file corruption, reduced additive patch failures by 70%

---

### Challenge 2: Infinite Read Loops (Analysis Paralysis) ♾️
**Problem:** Agent kept reading the same files 5-8 times without ever generating a patch.

**Example behavior:**
```
1. Read build.log
2. Read test_utils.py
3. Read test_utils.py (again)
4. Read test_utils.py (again)
5. Max attempts reached ❌
```

**✅ Solution: GUARDRAIL 4 - Anti-Loop Forcing**
```python
# After 2 consecutive file reads, force action
if consecutive_reads >= 2:
    print("⚡ FORCE: Too many reads. Forcing patch...")
    # Extract context from previous reads
    # Generate patch directly without more LLM reasoning
```
**Impact:** Eliminated infinite loops (100% reduction)

---

### Challenge 3: Partial Success Abandonment 🔄
**Problem:** LLM fixed only 1 of N failing tests, then stopped trying.

**Example:**
```
Initial: 3 tests failing
After patch: 1 test failing (2 fixed!)
Agent: "Max attempts reached" ❌ (gave up)
```

**✅ Solution: GUARDRAIL 3 - Partial Success Retry**
```python
# Detect if patch fixed SOME but not ALL errors
if tests_failed and error_count_decreased:
    print("🔄 RETRY: Incomplete. Forcing another fix...")
    # Force iterative patch generation
```
**Impact:** Multi-error scenarios now resolve iteratively (80% improvement)

---

### Challenge 4: Context Hallucination Breaking Patches 🧠
**Problem:** LLM "misremembers" code details, generating patches with wrong context.

**Example:**
```diff
# LLM generates:
-    assert add(424, 2) == 428    # (with 2 spaces)

# Actual file has:
    assert add(424, 2) == 428     # (with 4 spaces)

# Standard patch fails: "Context doesn't match"
```

**✅ Solution: Hyper-Fuzzy Patching (Already documented above)**
- Uses `difflib.SequenceMatcher` with 80% similarity threshold
- Falls back to fuzzy matching when exact match fails

**Impact:** Patch success rate: 30% → 90%

---

### Challenge 5: Wrong Target Selection 🎯
**Problem:** LLM modified passing tests instead of failing ones.

**Example:**
```python
# Test that's FAILING:
assert add(987, 0) == 1000  # ❌ Wrong

# LLM decides to "fix" a PASSING test instead:
assert add(-1, -1) == -2    # Already correct!
```

**✅ Solution: Combined GUARDRAIL 4 + Explicit Error Context**
- Provides exact failing test location from build.log
- Forces patch generation with specific error context

**Impact:** Reduced wrong target selection by ~90%

---

### Challenge 6: No-Op Patches (Useless Changes) 🔄
**Problem:** LLM changed code to identical version (no actual fix).

**Example:**
```diff
-    assert add(-1, -1) == -2
+    assert add(-1, -1) == -2  # Same line!
```

**✅ Solution: Enhanced prompting + GUARDRAIL 2 (Auto-Commit)**
- Ultra-explicit prompts with ❌ WRONG vs ✅ CORRECT examples
- Auto-commit prevents agent from trying to "improve" working code

**Impact:** Reduced no-ops by ~85%

---

### Challenge 7: JSON Escaping Failures in String Assertions 📝
**Problem:** LLM generated valid patches but created invalid JSON.

**Example:**
```json
{"patch": "assert greet("World") == "Hi, World!""}
                         ↑ Unescaped quotes break JSON!
```

**✅ Solution: Multi-Strategy JSON Parsing**
```python
def parse_llm_output(text):
    # Strategy 1: Look for "ACTION:" marker
    if "ACTION:" in text:
        extract_json_after_marker()
    # Strategy 2: Regex find first {...} block
    elif matches := re.search(r"(\{.*\})", text):
        parse_block()
    # Strategy 3: Handle direct tool calls
    elif is_direct_tool_call(text):
        wrap_and_parse()
```
**Impact:** Reduced JSON parse errors by 90%

---

### Challenge 8: API Rate Limiting 🚫
**Problem:** Hit Gemini API quota (10 requests/minute) with free-tier LLM.

**✅ Solution: Reduced `max_attempts` from 15 → 8**
- Balanced between enough retries and staying under quota
- Combined with guardrails, 8 attempts proved sufficient

**Impact:** Eliminated rate limit errors

---

## 🎯 The Complete Guardrail System

All four guardrails work together to create a deterministic workflow:

| Guardrail | Trigger | Action | Prevents |
|-----------|---------|--------|----------|
| **1. Auto-Pilot** | Patch detected | Apply immediately | Indecision loops |
| **2. Auto-Commit** | Tests pass | Commit immediately | Over-engineering |
| **3. Partial Retry** | Error count ↓ but tests fail | Force another patch | Abandoning progress |
| **4. Anti-Loop** | 2+ consecutive reads | Force patch generation | Analysis paralysis |

**Key Insight:** By removing LLM decision-making from critical paths and replacing it with deterministic logic, reliability improved from ~10% to ~90% for specific failure modes.

---

## 📊 Impact Summary

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Unknown action errors | 100% | 10% | **90% ↓** |
| Infinite read loops | Common | 0% | **100% ↓** |
| Partial fix abandonment | 100% | 20% | **80% ↓** |
| Additive patch corruption | 100% | 30% | **70% ↓** |
| Fuzzy patch application | 30% | 90% | **200% ↑** |

**Note:** With premium LLMs (GPT-4/Claude), expected overall success rate: **70-90%** vs current ~40% with free-tier models.

---

## Limitations

**Currently supports:**
- Python projects using pytest only
- Deterministic test failures

**Not supported yet:**
- Dependency conflicts
- Infrastructure issues
- Multi-language repositories

---

## Run Locally

```bash
export GEMINI_API_KEY=your_key
export GROQ_API_KEY=your_key

python agent.py
```

Run inside a repository with failing tests.

---

##  Why This Exists

CI failures are repetitive, disruptive, and often trivial.

This agent treats CI failures as **automatable engineering tasks**, not human emergencies.

---

## Roadmap

- [ ] Multi-language support
- [ ] Smarter multi-file refactors
- [ ] Fix caching for repeated failures
- [ ] Dashboard for monitoring fixes
- [ ] Fine-tuned code-repair models

---

##  License

Provided as-is for educational and experimental use. No warranty.

---

**CI should fix itself.** 
