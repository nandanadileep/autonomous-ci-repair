from agent.state import AgentState
from agent.loop import Agent

from llm.gemini import GeminiFlash
from llm.llama import LlamaGroq

from tools.read_file import ReadFile
from tools.apply_patch import ApplyPatch
from tools.run_tests import RunTests
from tools.git_ops import GitCommit


def main():
    state = AgentState()

    reader_llm = GeminiFlash()   # planning / analysis
    coder_llm = LlamaGroq()      # code generation

    tools = {
        "read_file": ReadFile(),
        "apply_patch": ApplyPatch(),
        "run_tests": RunTests(),
        "git_commit": GitCommit(),
    }

    agent = Agent(
        reader_llm=reader_llm,
        coder_llm=coder_llm,
        tools=tools
    )

    final_state = agent.run(state)

    if final_state.success:
        print("✅ CI self-healing successful")
    else:
        print("❌ CI self-healing failed")
        print(f"Reason: {final_state.failure_reason}")
        print("Observations:")
        for obs in final_state.observations:
            print(obs)


if __name__ == "__main__":
    main()
