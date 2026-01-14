import subprocess
import os
import re
from tools.base import Tool


class ApplyPatch(Tool):
    name = "apply_patch"
    description = "Apply a unified diff patch using git, with fuzzy fallback"

    def run(self, patch: str):
        try:
            # Cleanup markdown
            patch = patch.strip()
            if patch.startswith("```"):
                lines = patch.split("\n")
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                patch = "\n".join(lines)

            # Attempt 1: Git Apply (Strict)
            process = subprocess.run(
                ["git", "apply", "--verbose"],
                input=patch.encode(),
                capture_output=True,
                text=False
            )

            if process.returncode == 0:
                return {"success": True, "message": "Patch applied successfully (git)"}

            git_error = process.stderr.decode()

            # Attempt 2: Fuzzy Python Patching
            # LLMs often mess up line numbers or headers, so we'll try to find the content block and replace it.
            try:
                if self._fuzzy_apply(patch):
                    return {"success": True, "message": "Patch applied successfully (fuzzy fallback)"}
            except Exception as e:
                return {
                    "success": False, 
                    "error": f"Git apply failed: {git_error}\nFuzzy apply failed: {str(e)}",
                    "patch_preview": patch
                }

            return {
                "success": False,
                "error": f"Failed to apply patch. Git error: {git_error}. Fuzzy match not found.",
                "patch_preview": patch
            }

        except Exception as e:
            return {"success": False, "error": f"Exception: {str(e)}"}

    def _fuzzy_apply(self, patch: str) -> bool:
        """
        Manually parses a unified diff and applies changes by searching for context blocks.
        Ignores line numbers in the diff.
        """
        lines = patch.split('\n')
        target_file = None
        
        # 1. Find target file
        for line in lines:
            if line.startswith('+++ '):
                # Format: +++ b/path/to/file or +++ path/to/file
                clean_path = line[4:].strip()
                if clean_path.startswith('b/'):
                    clean_path = clean_path[2:]
                target_file = clean_path
                break
        
        if not target_file:
            raise ValueError("Could not extract file path from patch header")

        if not os.path.exists(target_file):
            raise FileNotFoundError(f"Target file {target_file} not found")

        with open(target_file, 'r') as f:
            content = f.read()

        # 2. Extract chunks
        chunks = [] # List of (search_block, replace_block)
        current_search = []
        current_replace = []
        in_chunk = False

        for line in lines:
            if line.startswith('@@'):
                if in_chunk:
                    chunks.append(("\n".join(current_search), "\n".join(current_replace)))
                current_search = []
                current_replace = []
                in_chunk = True
                continue
            
            if not in_chunk:
                continue

            if line.startswith(' '):
                # Context line: appears in both
                code = line[1:]
                current_search.append(code)
                current_replace.append(code)
            elif line.startswith('-'):
                # Deletion: appears in search only
                current_search.append(line[1:])
            elif line.startswith('+'):
                # Addition: appears in replace only
                current_replace.append(line[1:])
        
        # Access last chunk
        if in_chunk and (current_search or current_replace):
            chunks.append(("\n".join(current_search), "\n".join(current_replace)))

        if not chunks:
            raise ValueError("No valid chunks found in patch")

        # 3. Apply chunks
        modified_content = content
        changes_made = False

        for search_block, replace_block in chunks:
            if search_block in modified_content:
                modified_content = modified_content.replace(search_block, replace_block, 1)
                changes_made = True
            else:
                # Try more lenient whitespace matching? For now, fail if strict match fails
                # Often LLM adds/removes trailing newlines
                if search_block.strip() in modified_content:
                     modified_content = modified_content.replace(search_block.strip(), replace_block, 1)
                     changes_made = True
                else:
                    raise ValueError(f"Could not locate original code block for chunk:\n{search_block}")

        if changes_made:
            with open(target_file, 'w') as f:
                f.write(modified_content)
            return True
        
        return False

