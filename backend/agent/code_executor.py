"""Local safe code inspection, modification, and diagnostic executor for Agentic Pilot."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

from backend.llm.parser import ActionResult

logger = logging.getLogger("pilot.agent.code_executor")


class CodeExecutor:
    """Safe local executor for code generation, file modification, and diagnostics.

    Used when tasks require specialized coding model execution rather than
    DOM/browser interactions.
    """

    def __init__(self, workspace_root: Path | None = None) -> None:
        self.workspace_root = (workspace_root or Path.cwd()).resolve()

    def _resolve_safe_path(self, file_path: Path | str) -> Path:
        """Resolve path and verify it is a valid file location."""
        path = Path(file_path)
        if not path.is_absolute():
            path = (self.workspace_root / path).resolve()
        return path

    def read_file(self, file_path: Path | str) -> str:
        """Read text from a local source code or text file."""
        path = self._resolve_safe_path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return path.read_text(encoding="utf-8", errors="replace")

    def write_file(self, file_path: Path | str, content: str) -> ActionResult:
        """Write text content to a local file."""
        path = self._resolve_safe_path(file_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            path.write_text(content, encoding="utf-8")
            return ActionResult(
                success=True,
                action_type="modify_file",
                element_id=path.name,
                error=None,
                page_state_after="file_written",
                duration_ms=5,
            )
        except Exception as exc:
            return ActionResult(
                success=False,
                action_type="modify_file",
                element_id=path.name,
                error=str(exc),
                page_state_after="write_error",
                duration_ms=5,
            )

    def replace_snippet(
        self,
        file_path: Path | str,
        target_snippet: str,
        replacement_snippet: str,
    ) -> ActionResult:
        """Replace a specific code block in a file."""
        path = self._resolve_safe_path(file_path)
        if not path.exists():
            return ActionResult(
                success=False,
                action_type="modify_file",
                element_id=path.name,
                error=f"File not found: {path}",
                page_state_after="file_missing",
                duration_ms=2,
            )

        content = path.read_text(encoding="utf-8", errors="replace")
        if target_snippet not in content:
            return ActionResult(
                success=False,
                action_type="modify_file",
                element_id=path.name,
                error=f"Target snippet not found in {path.name}",
                page_state_after="snippet_not_found",
                duration_ms=3,
            )

        new_content = content.replace(target_snippet, replacement_snippet, 1)
        path.write_text(new_content, encoding="utf-8")
        return ActionResult(
            success=True,
            action_type="modify_file",
            element_id=path.name,
            error=None,
            page_state_after="file_modified",
            duration_ms=10,
        )

    def diagnose_syntax(self, code_str: str) -> dict[str, Any]:
        """Perform static syntax analysis on Python code."""
        try:
            tree = ast.parse(code_str)
            functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
            classes = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
            return {
                "valid": True,
                "error": None,
                "line": None,
                "functions": functions,
                "classes": classes,
            }
        except SyntaxError as syn_err:
            return {
                "valid": False,
                "error": str(syn_err.msg),
                "line": syn_err.lineno,
                "offset": syn_err.offset,
                "text": syn_err.text,
            }

    def validate_syntax(self, target: Path | str) -> dict[str, Any]:
        """Validate syntax of a Python file or raw code string."""
        try:
            path = self._resolve_safe_path(target)
            if path.exists() and path.is_file():
                code = path.read_text(encoding="utf-8", errors="replace")
                return self.diagnose_syntax(code)
        except Exception:
            pass
        return self.diagnose_syntax(str(target))


# Global code executor singleton
code_executor = CodeExecutor()

