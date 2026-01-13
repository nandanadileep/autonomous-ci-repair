from tools.base import Tool


class ReadFile(Tool):
    name = "read_file"
    description = "Read the contents of a file from disk"

    def run(self, path: str):
        try:
            with open(path, "r") as f:
                return {
                    "success": True,
                    "path": path,
                    "content": f.read()
                }
        except Exception as e:
            return {
                "success": False,
                "path": path,
                "error": str(e)
            }
