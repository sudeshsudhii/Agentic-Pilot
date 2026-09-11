"""GitHub Wiki synchronization and validation tool for Agentic Pilot."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def get_git_remote_url(repo_root: Path) -> str | None:
    """Retrieve origin remote URL from git config."""
    try:
        res = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=True,
        )
        return res.stdout.strip()
    except Exception:
        return None


def get_wiki_url(remote_url: str) -> str:
    """Derive wiki git URL from repository remote URL."""
    if remote_url.endswith(".git"):
        return remote_url[:-4] + ".wiki.git"
    return remote_url + ".wiki.git"


def validate_wiki_files(wiki_dir: Path) -> bool:
    """Validate that all markdown files in wiki/ are present and correctly formatted."""
    print("Validating Wiki files...")
    files = list(wiki_dir.glob("*.md"))
    if not files:
        print("ERROR: No markdown files found in wiki/ directory.")
        return False

    required_pages = [
        "Home.md",
        "Architecture.md",
        "Agent-Execution-Lifecycle.md",
        "Local-LLM-and-Model-Routing.md",
        "Vision-System.md",
        "Browser-Automation.md",
        "Evidence-and-Verification.md",
        "Agent-Observatory.md",
        "Experience-and-Learning.md",
        "CAPTCHA-and-Failure-Recovery.md",
        "Configuration.md",
        "Installation-and-Setup.md",
        "API-Reference.md",
        "Development-Guide.md",
        "Testing-and-Evaluation.md",
        "Troubleshooting.md",
        "Roadmap.md",
        "_Sidebar.md",
        "_Footer.md",
    ]

    all_valid = True
    page_names = {f.name for f in files}

    for req in required_pages:
        if req not in page_names:
            print(f"  [MISSING] {req}")
            all_valid = False
        else:
            print(f"  [OK] {req}")

    mermaid_count = 0
    for f in files:
        content = f.read_text(encoding="utf-8")
        mermaid_blocks = re.findall(r"```mermaid(.*?)```", content, re.DOTALL)
        mermaid_count += len(mermaid_blocks)

    print(f"\nValidation passed: {len(files)} pages validated with {mermaid_count} Mermaid diagrams.")
    return all_valid


def sync_to_github_wiki(wiki_dir: Path, wiki_url: str) -> bool:
    """Push wiki files to the GitHub wiki git repository."""
    print(f"\nChecking remote Wiki repository: {wiki_url}")

    # Check if remote wiki exists
    probe = subprocess.run(
        ["git", "ls-remote", wiki_url],
        capture_output=True,
        text=True,
    )
    if probe.returncode != 0:
        repo_web = wiki_url.replace(".wiki.git", "/wiki")
        print("\n" + "=" * 70)
        print("NOTICE: GitHub Wiki repository is not yet initialized.")
        print("=" * 70)
        print("GitHub requires creating the first page via the web interface")
        print("before the git remote can accept pushes.")
        print(f"\n1. Open your browser and navigate to:\n   {repo_web}")
        print("\n2. Click 'Create the first page' (or Save page).")
        print("\n3. Re-run this sync script:\n   python scripts/sync_wiki.py")
        print("=" * 70)
        return False

    with tempfile.TemporaryDirectory() as tmp_dir:
        clone_path = Path(tmp_dir) / "wiki_repo"
        print(f"Cloning wiki repository into temporary workspace...")
        subprocess.run(["git", "clone", wiki_url, str(clone_path)], check=True)

        # Copy all files from wiki/ into cloned repository
        for f in wiki_dir.glob("*.md"):
            shutil.copy2(f, clone_path / f.name)

        # Commit and push
        subprocess.run(["git", "add", "."], cwd=clone_path, check=True)
        status_res = subprocess.run(["git", "status", "--porcelain"], cwd=clone_path, capture_output=True, text=True)
        if not status_res.stdout.strip():
            print("Remote Wiki is already up to date with local wiki/ files.")
            return True

        subprocess.run(
            ["git", "commit", "-m", "docs(wiki): sync documentation suite from wiki/"],
            cwd=clone_path,
            check=True,
        )
        print("Pushing updated documentation to GitHub Wiki...")
        subprocess.run(["git", "push", "origin", "master"], cwd=clone_path, check=True)
        print("\nSuccessfully synchronized all Wiki pages to GitHub Wiki!")
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate and sync GitHub Wiki documentation.")
    parser.add_argument("--check-only", action="store_true", help="Only validate local wiki files without pushing")
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    wiki_dir = repo_root / "wiki"

    if not wiki_dir.exists():
        print(f"ERROR: Wiki directory not found at {wiki_dir}")
        sys.exit(1)

    if not validate_wiki_files(wiki_dir):
        sys.exit(1)

    if args.check_only:
        sys.exit(0)

    remote_url = get_git_remote_url(repo_root)
    if not remote_url:
        print("ERROR: Could not detect git remote origin URL.")
        sys.exit(1)

    wiki_url = get_wiki_url(remote_url)
    success = sync_to_github_wiki(wiki_dir, wiki_url)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()
