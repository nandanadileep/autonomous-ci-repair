import subprocess
from tools.base import Tool


class ApplyPatch(Tool):
    name = "apply_patch"
    description = "Apply a unified diff patch using git"

    def run(self, patch: str):
        try:
            process = subprocess.run(
                ["git", "apply"],
                input=patch.encode(),
                capture_output=True
            )

            if process.returncode != 0:
                return {
                    "success": False,
                    "error": process.stderr.decode()
                }

            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}
