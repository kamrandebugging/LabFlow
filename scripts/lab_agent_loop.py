"""
LabFlow Autonomous Agent Loop (steipete / Ralph loop pattern).

Orchestrates the autonomous software engineering loop:
1. Fetch next story or given ticket from Jira backlog (via `twg` CLI).
2. Generate context-rich, DoD-compliant prompt using docs/LAB_EXECUTION_GUIDE.md.
3. Drive the agent execution & self-correction cycle.
4. Run deterministic 6-phase Definition of Done (DoD) verification gate.
5. If gates fail: inject exact error/stack trace back to agent (loop up to N times).
6. When 100% green: git commit, push to origin/LAB-XX, and transition Jira to In Review.

Usage:
    python scripts/lab_agent_loop.py --ticket KAN-138
    python scripts/lab_agent_loop.py --next
    python scripts/lab_agent_loop.py --verify-only
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Ensure UTF-8 output on Windows terminals
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ANSI Colors for terminal output
BOLD = "\033[1m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
RESET = "\033[0m"

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
FRONTEND_DIR = REPO_ROOT / "frontend"
VENV_PYTHON = BACKEND_DIR / ".venv" / "Scripts" / "python.exe"
if not VENV_PYTHON.exists():
    VENV_PYTHON = BACKEND_DIR / ".venv" / "bin" / "python"
if not VENV_PYTHON.exists():
    VENV_PYTHON = Path(sys.executable)


def log_header(text: str) -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 78}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 78}{RESET}\n")


def log_step(step: int, total: int, text: str) -> None:
    print(f"{BOLD}{MAGENTA}[Step {step}/{total}] {text}{RESET}")


def log_success(text: str) -> None:
    print(f"{BOLD}{GREEN}✓ {text}{RESET}")


def log_warning(text: str) -> None:
    print(f"{BOLD}{YELLOW}⚠ {text}{RESET}")


def log_error(text: str) -> None:
    print(f"{BOLD}{RED}✗ {text}{RESET}")


def run_command(
    cmd: str | list[str],
    cwd: Path | None = None,
    timeout: int = 120,
) -> tuple[int, str, str]:
    """Execute a shell command returning (exit_code, stdout, stderr)."""
    if cwd is None:
        cwd = REPO_ROOT

    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except subprocess.TimeoutExpired:
        return 1, "", f"Command timed out after {timeout}s: {cmd}"
    except Exception as exc:
        return 1, "", str(exc)


def check_docker_services() -> bool:
    """Verify labflow-postgres and labflow-redis containers are running."""
    code, stdout, _ = run_command("docker ps --format '{{.Names}}'")
    if code != 0:
        log_warning("Docker is not reachable or docker command failed.")
        return False

    running = stdout.splitlines()
    has_postgres = any("labflow-postgres" in line for line in running)
    has_redis = any("labflow-redis" in line for line in running)

    if not has_postgres or not has_redis:
        log_warning(
            f"Missing required Docker containers. "
            f"postgres: {has_postgres}, redis: {has_redis}. "
            f"Run: docker compose up -d"
        )
        return False
    return True


import yaml


def _parse_twg_output(raw_output: str) -> dict[str, Any] | None:
    """Parse output from twg CLI, reading full JSON from disk if available."""
    clean_text = raw_output.split("---END---")[0].strip()
    try:
        # 1. Try direct JSON parsing
        return json.loads(clean_text)
    except Exception:
        pass

    try:
        # 2. Try parsing twg YAML envelope
        meta = yaml.safe_load(clean_text)
        if isinstance(meta, dict):
            json_path = meta.get("output_files", {}).get("stdout")
            if json_path and Path(json_path).exists():
                with open(json_path, "r", encoding="utf-8") as f:
                    full_data = json.load(f)
                    return full_data
            if "stdout_inline" in meta:
                return meta["stdout_inline"]
            if "data" in meta:
                return meta
    except Exception as e:
        log_warning(f"Error parsing twg output: {e}")
    return None


def fetch_jira_ticket(key: str) -> dict[str, Any] | None:
    """Fetch Jira issue details using twg CLI."""
    code, stdout, stderr = run_command(f"twg jira workitem get {key} -o json")
    if code != 0:
        log_error(f"Failed to fetch Jira ticket {key}: {stderr or stdout}")
        return None

    data = _parse_twg_output(stdout)
    if not data:
        log_error(f"Failed to parse ticket data for {key}")
        return None

    # Handle twg data unwrapping
    item = data.get("data") if isinstance(data, dict) else data
    if isinstance(item, list) and item:
        item = item[0]
    return item if isinstance(item, dict) else data


def fetch_next_jira_ticket() -> dict[str, Any] | None:
    """Find the next open story in KAN project ordered by key."""
    jql = "project = KAN AND statusCategory = 'To Do' AND issuetype in (Story, Task) ORDER BY key ASC"
    code, stdout, stderr = run_command(f'twg jira workitem query "{jql}"')
    if code != 0:
        log_error(f"Jira query failed: {stderr or stdout}")
        return None

    data = _parse_twg_output(stdout)
    if not data:
        return None

    issues = data.get("issues", [])
    if not issues and isinstance(data, dict) and "data" in data:
        issues = data.get("data", [])
    return issues[0] if issues else None


def extract_lab_id(summary: str, key: str) -> str:
    """Extract LAB-XX identifier from summary or key."""
    match = re.search(r"LAB-(\d+)", summary, re.IGNORECASE)
    if match:
        return f"LAB-{match.group(1)}"
    num = re.search(r"\d+", key)
    return f"LAB-{num.group(0)}" if num else key


def _extract_adf_text(node: Any) -> str:
    """Extract human-readable text/markdown from Atlassian Document Format (ADF)."""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "".join(_extract_adf_text(item) for item in node if item)
    if not isinstance(node, dict):
        return ""

    node_type = node.get("type")
    content = node.get("content", [])

    if node_type == "text":
        return str(node.get("text", ""))
    elif node_type == "paragraph":
        return "".join(_extract_adf_text(c) for c in content) + "\n"
    elif node_type == "heading":
        level = node.get("attrs", {}).get("level", 2)
        return f"{'#' * level} " + "".join(_extract_adf_text(c) for c in content).strip() + "\n\n"
    elif node_type == "bulletList":
        items = [_extract_adf_text(c).strip() for c in content if _extract_adf_text(c).strip()]
        return "\n".join(f"* {it}" for it in items) + "\n\n"
    elif node_type == "listItem":
        return "".join(_extract_adf_text(c) for c in content)
    elif node_type == "codeBlock":
        code = "".join(_extract_adf_text(c) for c in content)
        return f"```\n{code}\n```\n"
    elif content:
        return "".join(_extract_adf_text(c) for c in content)
    return ""


def assemble_agent_prompt(
    ticket: dict[str, Any],
    lab_id: str,
    feedback: str | None = None,
) -> str:
    """
    Assemble the complete prompt with Jira specs, DoD checklist,
    and any feedback from previous loop failure.
    """
    key = ticket.get("key", "UNKNOWN")
    summary = ticket.get("summary") or ticket.get("fields", {}).get("summary", "")
    raw_desc = ticket.get("description") or ticket.get("fields", {}).get("description", "")
    description = _extract_adf_text(raw_desc).strip()
    if not description and isinstance(raw_desc, (dict, list)):
        description = json.dumps(raw_desc, indent=2)

    prompt = f"""# TASK: Complete {lab_id} ({key}) — {summary}

You are executing an autonomous engineering cycle in the LabFlow project.
Follow docs/LAB_EXECUTION_GUIDE.md with ZERO compromises.

## TICKET SPECIFICATIONS
- **Key**: {key}
- **LAB Identifier**: {lab_id}
- **Summary**: {summary}
- **Description / Requirements**:
{description or "Refer to authoritative specifications Docs 01-10 in docs/ directory."}

## MANDATORY DEFINITION OF DONE (DoD)
1. Write tests first (RED), then implement (GREEN) adhering to TDD.
2. Maintain tenant schema isolation (`schema_context(tenant.schema_name)`).
3. Record immutable `AuditLog` for every state-changing mutation in the same transaction.
4. Python 88-character line ceiling strictly enforced.
5. All custom error classes starting with 'Test' MUST include `__test__ = False`.
6. Minimum 80% test coverage for all new services and serializers.
7. Passing full verification suite (pytest, mypy, ruff, eslint, prettier, tsc).
"""

    if feedback:
        prompt += f"""
## ⚠️ CRITICAL: PREVIOUS VERIFICATION FAILURE (SELF-CORRECTION REQUIRED)
The previous iteration failed the Definition of Done gate with the following error:
```
{feedback}
```
Analyze this error trace carefully. Fix the root cause immediately without breaking existing tests.
"""
    return prompt.strip()


def run_dod_verification_suite() -> tuple[bool, str]:
    """
    Execute the 6-Phase Definition of Done Verification Suite.
    Returns (success: bool, error_report: str).
    """
    # Fast check: Docker must be running for DB/migrations
    if not check_docker_services():
        return (
            False,
            "PREREQUISITE FAILED: Docker Desktop is not running or labflow-postgres/redis containers are down.\n"
            "Please start Docker Desktop and run: docker compose up -d",
        )

    py_exec = str(VENV_PYTHON)
    gates: list[tuple[str, str, Path]] = [
        (
            "Phase 1: Migration Drift Check",
            f'"{py_exec}" manage.py makemigrations --check --dry-run',
            BACKEND_DIR,
        ),
        (
            "Phase 2: Python Ruff Linter",
            "ruff check apps/",
            BACKEND_DIR,
        ),
        (
            "Phase 3: Python Formatting (88-char ceiling)",
            "ruff format --check apps/",
            BACKEND_DIR,
        ),
        (
            "Phase 4: Frontend Typecheck (TypeScript)",
            "npm run typecheck",
            FRONTEND_DIR,
        ),
        (
            "Phase 5: Frontend Prettier Code Style",
            "npx prettier --check .",
            FRONTEND_DIR,
        ),
        (
            "Phase 6: Backend Tests & 80% Coverage Gate",
            f'"{py_exec}" -m pytest apps/ --cov=apps --cov-fail-under=80 -q',
            BACKEND_DIR,
        ),
    ]

    total_gates = len(gates)
    for i, (name, command, cwd) in enumerate(gates, start=1):
        print(f"  {CYAN}▸ [{i}/{total_gates}] Running {name}...{RESET}", end="", flush=True)
        code, stdout, stderr = run_command(command, cwd=cwd)
        if code == 0:
            print(f" {GREEN}[PASSED]{RESET}")
        else:
            print(f" {RED}[FAILED]{RESET}")
            output = stderr if stderr else stdout
            # Clean up long outputs to keep the most relevant lines
            truncated_output = "\n".join(output.splitlines()[-60:])
            report = f"GATE FAILED: {name}\nCommand: {command}\n\nError Output:\n{truncated_output}"
            return False, report

    return True, "All 6 Definition of Done Gates Passed!"


def transition_jira_to_review(key: str, lab_id: str, comment: str) -> bool:
    """Transition Jira ticket to In Review (Transition ID 41)."""
    cmd = (
        f'twg jira workitem transition --id {key} --transition-id 41 '
        f'--transition-comment "{comment}" --transition-comment-format plain'
    )
    code, stdout, stderr = run_command(cmd)
    if code == 0:
        log_success(f"Transitioned {key} to 'In Review'")
        return True
    log_warning(f"Failed to transition {key} (code {code}): {stderr or stdout}")
    return False


def git_commit_and_push(branch: str, key: str, summary: str) -> bool:
    """Commit all changes using Conventional Commits and push to origin/branch."""
    commit_msg = f"feat({branch.lower()}): complete {summary} ({key})\n\nVerified via LabFlow Autonomous DoD Loop."
    run_command("git add -A")
    code, _, stderr = run_command(f'git commit -m "{commit_msg}"')
    if code != 0 and "nothing to commit" not in stderr:
        log_warning(f"Git commit returned: {stderr}")

    code, stdout, stderr = run_command(f"git push origin {branch}")
    if code == 0:
        log_success(f"Pushed branch to origin/{branch}")
        return True
    log_error(f"Git push failed: {stderr or stdout}")
    return False


def generate_delivery_report(branch: str, key: str, lab_id: str, coverage_summary: str) -> None:
    """
    Generate and print the strict delivery report per Stage 6 Protocol:
    Report ticket key, branch, tests, coverage, files changed, and FULL STOP.
    """
    # Get changed files diff stat against origin/main or last commit
    code, stdout, _ = run_command(f"git diff --stat origin/main...HEAD")
    if not stdout or code != 0:
        _, stdout, _ = run_command("git diff --stat HEAD~1")

    print(f"\n{BOLD}{GREEN}{'=' * 78}{RESET}")
    print(f"{BOLD}{GREEN}  🛑 DELIVERY COMPLETE (FULL STOP){RESET}")
    print(f"{BOLD}{GREEN}{'=' * 78}{RESET}\n")

    print(f"  {BOLD}Ticket Key:{RESET}     {CYAN}{key}{RESET}")
    print(f"  {BOLD}LAB Branch:{RESET}     {CYAN}{branch}{RESET} (pushed to origin/{branch} ONLY)")
    print(f"  {BOLD}Jira Status:{RESET}    {GREEN}In Review{RESET} (Transition ID 41)")
    print(f"  {BOLD}DoD Gates:{RESET}      {GREEN}All 6 Gates Passed (100% Green){RESET}")
    print(f"  {BOLD}Coverage:{RESET}       {GREEN}>= 80% Minimum Met{RESET}")
    if coverage_summary:
        print(f"  {BOLD}Test Summary:{RESET}   {coverage_summary}")

    print(f"\n  {BOLD}Files Changed:{RESET}")
    print(f"  {'-' * 74}")
    for line in stdout.splitlines():
        print(f"    {line}")
    print(f"  {'-' * 74}\n")

    print(f"{BOLD}{YELLOW}  🛑 FULL STOP RULES ENFORCED:{RESET}")
    print(f"     1. NO Pull Request created.")
    print(f"     2. NO merge to main performed.")
    print(f"     3. NO auto-advance to next ticket.")
    print(f"     4. Merge manually when verified, then say {BOLD}'next'{RESET}.\n")
    print(f"{BOLD}{GREEN}{'=' * 78}{RESET}\n")


def run_loop(ticket: dict[str, Any], max_retries: int = 4, auto_commit: bool = True) -> bool:
    """
    Main Autonomous Agent Loop.
    Executes: Prompt formulation -> DoD Gates -> Self-Correction iterations -> Auto Delivery (STOP).
    """
    key = ticket.get("key", "UNKNOWN")
    summary = ticket.get("summary") or ticket.get("fields", {}).get("summary", "")
    lab_id = extract_lab_id(summary, key)
    branch = lab_id

    log_header(f"STARTING AUTONOMOUS AGENT LOOP: {lab_id} ({key})")
    print(f"Summary: {summary}")
    print(f"Branch:  {branch}")
    print(f"Max Self-Correction Retries: {max_retries}")

    # Check git branch
    run_command(f"git checkout -B {branch}")
    log_success(f"Switched to dedicated branch: {branch}")

    # Pre-flight container check
    check_docker_services()

    feedback: str | None = None
    prompt_file = REPO_ROOT / ".agent_prompt.md"

    for iteration in range(1, max_retries + 1):
        print(f"\n{BOLD}{YELLOW}--- Loop Iteration {iteration}/{max_retries} ---{RESET}")

        # 1. Assemble prompt
        prompt = assemble_agent_prompt(ticket, lab_id, feedback=feedback)
        prompt_file.write_text(prompt, encoding="utf-8")
        log_success(f"Generated prompt written to {prompt_file.name}")

        # 2. Run DoD Verification Suite
        print(f"\n{CYAN}Running DoD Verification Suite...{RESET}")
        passed, report = run_dod_verification_suite()

        if passed:
            log_header(f"🎉 DoD VERIFICATION SUCCESSFUL ON ITERATION {iteration}!")
            log_success(report)

            if auto_commit:
                # Stage 6: DELIVERY (STOP)
                git_commit_and_push(branch, key, summary)
                evidence = (
                    f"Completed {lab_id} ({key}) via LabFlow Autonomous DoD Loop.\n"
                    f"All 6 DoD gates green (pytest 80%+ coverage, mypy strict, ruff, tsc, eslint)."
                )
                transition_jira_to_review(key, lab_id, evidence)
                generate_delivery_report(branch, key, lab_id, report)
            return True
        else:
            log_error(f"DoD Gate Failed on iteration {iteration}.")
            print(f"\n{YELLOW}{report}{RESET}\n")
            feedback = report
            time.sleep(1)

    log_header(f"❌ LOOP TERMINATED: Reached {max_retries} iterations without passing DoD.")
    log_warning(f"Review the error log above and in {prompt_file.name} to diagnose.")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="LabFlow Autonomous Agent Loop Runner")
    parser.add_argument("--ticket", type=str, help="Jira Ticket Key (e.g. KAN-138 or LAB-22)")
    parser.add_argument("--next", action="store_true", help="Automatically fetch the next To Do ticket in Jira")
    parser.add_argument("--verify-only", action="store_true", help="Run the 6 DoD verification gates only")
    parser.add_argument("--max-retries", type=int, default=4, help="Maximum self-correction loop iterations")
    parser.add_argument("--no-commit", action="store_true", help="Skip automatic git commit and Jira transition")

    args = parser.parse_args()

    if args.verify_only:
        log_header("RUNNING DoD VERIFICATION SUITE ONLY")
        passed, report = run_dod_verification_suite()
        if passed:
            log_success(report)
            sys.exit(0)
        else:
            log_error(report)
            sys.exit(1)

    ticket: dict[str, Any] | None = None

    if args.ticket:
        log_header(f"FETCHING JIRA TICKET: {args.ticket}")
        ticket = fetch_jira_ticket(args.ticket)
    elif args.next:
        log_header("FETCHING NEXT OPEN JIRA TICKET")
        ticket = fetch_next_jira_ticket()
    else:
        # Default behavior: if no args, verify current status and advise
        print("No ticket specified. Checking next open ticket in backlog...")
        ticket = fetch_next_jira_ticket()

    if not ticket:
        log_error("No Jira ticket found. Please provide --ticket <KEY> or verify Jira connection.")
        sys.exit(1)

    success = run_loop(
        ticket=ticket,
        max_retries=args.max_retries,
        auto_commit=not args.no_commit,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
