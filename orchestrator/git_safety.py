import subprocess


def git_snapshot(root):
    def read(*args):
        try:
            p = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10)
            return p.stdout.strip() if p.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            return None
    inside = read("rev-parse", "--is-inside-work-tree") == "true"
    return {"is_repository": inside, "branch": read("branch", "--show-current") if inside else None,
            "commit": read("rev-parse", "HEAD") if inside else None,
            "uncommitted": read("status", "--short") if inside else None}
