import subprocess
from tools.base import Tool


class GitCommit(Tool):
    name = "git_commit"
    description = "Commit changes to the repository"

    def run(self, message: str):
        try:
            final_message = f"[ci-auto-fix] {message}"

            subprocess.run(["git", "add", "."], check=True)
            subprocess.run(
                ["git", "commit", "-m", final_message],
                check=True
            )

            return {"success": True}

        except subprocess.CalledProcessError as e:
            return {"success": False, "error": str(e)}
