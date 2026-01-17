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
