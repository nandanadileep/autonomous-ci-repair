import subprocess
from tools.base import Tool


class RunTests(Tool):
    name = "run_tests"
    description = "Run pytest to verify the fix"

    def run(self):
        try:
            process = subprocess.run(
                ["pytest"],
                capture_output=True
            )

            return {
                "success": process.returncode == 0,
                "stdout": process.stdout.decode(),
                "stderr": process.stderr.decode()
            }

        except Exception as e:
            return {"success": False, "error": str(e)}
