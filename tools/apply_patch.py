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
        Ignores line numbers and is whitespace-forgiving.
        """
        lines = patch.split('\n')
        target_file = None
        
        # 1. Find target file
        for line in lines:
            if line.startswith('+++ '):
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
            file_lines = f.readlines()

        # 2. Extract chunks
        chunks = [] # List of (search_lines, replace_lines)
        current_search = []
        current_replace = []
        in_chunk = False

        for line in lines:
            if line.startswith('@@'):
                if in_chunk:
                    chunks.append((current_search, current_replace))
                current_search = []
                current_replace = []
                in_chunk = True
                continue
            
            if not in_chunk:
                continue

            # Handle No newline at end of file
            if line.startswith('\\ No newline'):
                continue

            if line.startswith(' '):
                context = line[1:]
                current_search.append(context)
                current_replace.append(context)
            elif line.startswith('-'):
                current_search.append(line[1:])
            elif line.startswith('+'):
                current_replace.append(line[1:])
        
        if in_chunk and (current_search or current_replace):
            chunks.append((current_search, current_replace))

        if not chunks:
            raise ValueError("No valid chunks found in patch")

        # 3. Apply chunks
        # We process chunks one by one, updating file_lines
        changes_made = False

        for search_lines, replace_lines in chunks:
            # Try to find the search_lines in file_lines (ignoring whitespace)
            match_index = -1
            
            # Helper to strip whitespace for comparison
            search_stripped = [s.strip() for s in search_lines if s.strip()]
            if not search_stripped:
                continue # Skip empty chunks

            # Naive search for the block
            for i in range(len(file_lines) - len(search_lines) + 1):
                # Check if this window matches
                match = True
                search_idx = 0
                file_idx = 0
                
                # Careful line-by-line check with whitespace normalization
                # We need to match all non-empty search lines
                current_window_file_lines = []
                
                # Logic: iterate through search_lines, find corresponding match in file starting at i
                # This is tricky because we want to preserve file's original indentation if possible?
                # Actually, simpler: Exact match on .strip() content
                
                # Let's verify strict stripped match for all lines
                match = True
                for k, s_line in enumerate(search_lines):
                    if i + k >= len(file_lines):
                        match = False
                        break
                    f_line = file_lines[i + k]
                    if s_line.strip() != f_line.strip():
                        match = False
                        break
                
                if match:
                    match_index = i
                    break
            
            if match_index != -1:
                # Found it! Replace file_lines[match_index : match_index + len(search_lines)]
                # BUT we need to handle formatting of replace_lines. 
                # LLM patches provided replace_lines with some indentation.
                # simpler approach: just insert the replace_lines as strings (adding newlines if needed)
                
                # Prepare replace lines with newlines
                final_replace = [L + '\n' if not L.endswith('\n') else L for L in replace_lines]
                
                # Replace the slice
                file_lines[match_index : match_index + len(search_lines)] = final_replace
                changes_made = True
            else:
                # Failed to find matches
                error_context = '\n'.join(search_lines)
                raise ValueError(f"Could not locate block in file (whitespace ignore):\n{error_context}")

        if changes_made:
            with open(target_file, 'w') as f:
                f.writelines(file_lines)
            return True
        
        return False

