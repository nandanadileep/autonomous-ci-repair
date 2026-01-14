from dataclasses import dataclass, field
from typing import List, Dict, Any, Set


@dataclass
class AgentState:
    """
    Represents the complete, explicit state of the self-healing CI agent.
    This state is mutated only by the agent loop.
    """

    # High-level objective
    goal: str = "Fix failing CI build. The test failure log is in build.log in the current directory."

    # Iteration control
    max_attempts: int = 15  # Increased for retry logic resilience
    attempts: int = 0

    # Termination flags
    done: bool = False
    success: bool = False

    # Memory / observations
    observations: List[Dict[str, Any]] = field(default_factory=list)

    # Safety / tracking
    files_touched: Set[str] = field(default_factory=set)

    # Failure reason (if any)
    failure_reason: str | None = None

    def record_observation(self, observation: Dict[str, Any]) -> None:
        """
        Append an observation from a tool or model call.
        """
        self.observations.append(observation)

    def record_file_touch(self, path: str) -> None:
        """
        Track which files the agent has modified.
        Prevents runaway multi-file edits later.
        """
        self.files_touched.add(path)

    def increment_attempts(self) -> None:
        """
        Increment attempt counter and enforce max attempts.
        """
        self.attempts += 1
        if self.attempts >= self.max_attempts:
            self.fail("Maximum attempts reached")

    def mark_success(self) -> None:
        """
        Mark the agent run as successful and stop execution.
        """
        self.done = True
        self.success = True

    def fail(self, reason: str) -> None:
        """
        Fail the agent safely with an explicit reason.
        """
        self.done = True
        self.success = False
        self.failure_reason = reason

    def can_continue(self) -> bool:
        """
        Check whether the agent is allowed to continue running.
        """
        return not self.done and self.attempts < self.max_attempts
