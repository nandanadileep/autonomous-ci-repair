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
        Ignores line numbers, whitespace, and blank lines.
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
        chunks = [] 
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
        changes_made = False

        for search_lines, replace_lines in chunks:
            # SUPER FUZZY MATCHING: Ignore empty lines
            
            # 1. Map file lines to non-empty indices
            # file_map = [(original_index, stripped_content), ...]
            file_map = []
            for i, line in enumerate(file_lines):
                stripped = line.strip()
                if stripped:
                    file_map.append((i, stripped))

            # 2. Prepare search block (stripped, non-empty)
            search_stripped = [s.strip() for s in search_lines if s.strip()]
            
            if not search_stripped:
                continue

            # 3. Find sequence match in file_map
            match_start_idx = -1
            match_end_idx = -1
            
            for i in range(len(file_map) - len(search_stripped) + 1):
                match = True
                for k, s_content in enumerate(search_stripped):
                    if file_map[i + k][1] != s_content:
                        match = False
                        break
                
                if match:
                    # Found match!
                    # Start index in original file is the index of the first matched line
                    match_start_idx = file_map[i][0]
                    # End index is the index of the last matched line
                    match_end_idx = file_map[i + len(search_stripped) - 1][0]
                    
                    # But wait! We need to handle the case where the replace block REPLACES 
                    # the chunk. We should probably expand the match range to include 
                    # interstitial blank lines?
                    
                    # Actually, a safer way is:
                    # We found the block from match_start_idx to match_end_idx
                    # But there might be blank lines *before* match_start_idx that were 
                    # part of the "context" conceptually, or *after*.
                    # However, strictly replacing the *content* lines is safest for code.
                    
                    # One Edge Case: If the search block HAD blank lines in the middle
                    # we want to include them in the replaced range.
                    # e.g. Search: "A", "", "B". File: "A", "", "", "B".
                    # Our match finds "A" and "B". 
                    # Replaced range should be from "A" to "B" inclusive.
                    break
            
            if match_start_idx != -1:
                # We found the start and end lines of the content.
                # Replace everything between match_start_idx and match_end_idx + 1
                
                # Construct replacement text
                # We simply use the replace_lines as provided
                final_replace = [L + '\n' if not L.endswith('\n') else L for L in replace_lines]
                
                # Perform replacement
                # Note: modifying list in place changes indices for subsequent chunks?
                # Yes. But usually patches flow top-to-bottom. 
                # Ideally we track offset, but here we assume chunks are ordered.
                # However, since we re-read file_lines only once at start, we might desync 
                # if we have multiple chunks.
                # BUT this tool restarts logic for each chunk? 
                # No, the loop runs on `file_lines`. We must account for index shift?
                # Actually, `file_map` is computed based on CURRENT `file_lines`.
                # So we should re-compute file_map inside the loop? 
                # YES.
                
                # Re-reading or Re-computing is needed.
                # Let's just modify the code to restart the search for each chunk 
                # on the *current* state of file_lines.
                
                # RECURSIVE/ITERATIVE FIX:
                # We found indices in current `file_lines`.
                file_lines[match_start_idx : match_end_idx + 1] = final_replace
                changes_made = True
                
                # Since we modified file_lines, we must continue to next chunk 
                # but careful about indices. The loop `for search_lines...` continues.
                # We should re-scan file for next chunk?
                # The next chunk search will re-build file_map correctly because 
                # it's built inside the loop? NO, it was built outside.
                # I need to move file_map construction INSIDE the loop.
                pass 
            else:
                error_context = '\n'.join(search_lines)
                raise ValueError(f"Could not locate block in file (super fuzzy):\n{error_context}")

        if changes_made:
            with open(target_file, 'w') as f:
                f.writelines(file_lines)
            return True
        
        return False

