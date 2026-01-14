import subprocess
from tools.base import Tool


class ApplyPatch(Tool):
    name = "apply_patch"
    description = "Apply a unified diff patch using git"

    def run(self, patch: str):
        try:
            # Strip any markdown code blocks
            patch = patch.strip()
            if patch.startswith("```"):
                lines = patch.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                patch = "\n".join(lines)

            # Try to apply the patch
            process = subprocess.run(
                ["git", "apply", "--verbose"],
                input=patch.encode(),
                capture_output=True,
                text=False
            )

            if process.returncode != 0:
                error_msg = process.stderr.decode()
                return {
                    "success": False,
                    "error": f"Failed to apply patch: {error_msg}",
                    "patch_preview": patch[:500]  # Show first 500 chars
                }

            return {
                "success": True,
                "message": "Patch applied successfully"
            }

        except Exception as e:
            return {"success": False, "error": f"Exception: {str(e)}"}

