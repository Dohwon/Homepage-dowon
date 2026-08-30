import subprocess
from pathlib import Path


def git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def init_repo(root: Path) -> Path:
    root.mkdir(parents=True)
    git(root, "init", "--quiet")
    git(root, "config", "user.name", "Atlas Test")
    git(root, "config", "user.email", "atlas@example.invalid")
    write(root / "README.md", "baseline\n")
    git(root, "add", "--", "README.md")
    git(root, "commit", "--quiet", "-m", "test: baseline")
    return root
