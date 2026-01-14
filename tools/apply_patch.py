import subprocess
import os
import re
import difflib
from typing import List, Tuple
from tools.base import Tool


class ApplyPatch(Tool):
    name = "apply_patch"
    description = "Apply a unified diff patch using git, with hyper-fuzzy fallback"

    def run(self, patch: str):
        try:
            # Cleanup markdown
            patch = patch.strip()
            if patch.startswith("```"):
                lines = patch.split("\n")
                # Remove first line if it is ```xxx
                if lines[0].startswith("```"):
                    lines = lines[1:]
                # Remove last line if it is ```
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

            # Attempt 2: Hyper-Fuzzy Patching
            # Handles whitespace diffs and minor LLM hallucinations in context
            try:
                if self._fuzzy_apply(patch):
                    return {"success": True, "message": "Patch applied successfully (hyper-fuzzy fallback)"}
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

    def _normalize(self, line: str) -> str:
        """Strip whitespace and ignore blank lines logic helper"""
        return line.strip()

    def _find_block_start(self, lines: List[str], search_lines: List[str]) -> int:
        """
        Find the start index of the search_block in lines using:
        1. Exact match (ignoring whitespace).
        2. Fuzzy match (SequenceMatcher) to handle minor context hallucinations.
        """
        # Filter out empty search lines for matching
        search_stripped = [s for s in search_lines if s.strip()]
        if not search_stripped:
            return -1
            
        search_len = len(search_lines) # We search for the FULL block span
        # But for 'exact' matching we might want to skip empty lines? 
        # Simpler: Use the SequenceMatcher on the whole block str.

        search_block_str = "\n".join(search_lines).strip()
        
        best_ratio = 0.0
        best_idx = -1
        threshold = 0.8 # 80% similarity required

        for i in range(len(lines) - search_len + 1):
            window = lines[i : i + search_len]
            window_str = "\n".join(window).strip()
            
            # Optimization: Length check
            if abs(len(window_str) - len(search_block_str)) > max(len(search_block_str), 10) * 0.5:
                continue

            # Check for exact whitespace-insensitive match first (Performance)
            if window_str == search_block_str:
                return i
            
            normalized_window = "".join(window_str.split())
            normalized_search = "".join(search_block_str.split())
            if normalized_window == normalized_search:
                return i

            # Fallback to slower fuzzy match
            ratio = difflib.SequenceMatcher(None, window_str, search_block_str).ratio()
            
            if ratio > best_ratio:
                best_ratio = ratio
                best_idx = i
        
        if best_ratio >= threshold:
            print(f"Hyper-Fuzzy match found at line {best_idx+1} with confidence {best_ratio:.2f}")
            return best_idx

        return -1

    def _fuzzy_apply(self, patch: str) -> bool:
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
            # Fallback: look for ---
            for line in lines:
                if line.startswith('--- '):
                    clean_path = line[4:].strip()
                    if clean_path.startswith('a/'):
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
            # Re-read lines relative to current buffer content? 
            # We assume find_block_start works on the *modified* buffer if we modify it in place.
            # Yes, passing `file_lines` is by reference, but slicing creates copies.
            
            match_idx = self._find_block_start(file_lines, search_lines)
            
            if match_idx != -1:
                # Replace
                # Ensure new lines have newlines
                final_replace = [L + '\n' if not L.endswith('\n') else L for L in replace_lines]
                file_lines[match_idx : match_idx + len(search_lines)] = final_replace
                changes_made = True
            else:
                error_context = '\n'.join(search_lines)
                raise ValueError(f"Could not locate block in file (hyper-fuzzy):\n{error_context}")

        if changes_made:
            with open(target_file, 'w') as f:
                f.writelines(file_lines)
            return True
        
        return False
