#!/usr/bin/env python3
"""Interactive-capable OpenCode runner for Hybrid SDD orchestration.

Default mode uses the OpenCode background service (`opencode api`) so that
dynamic interactive `question` forms (`session.form.list` / `session.form.reply`)
and permission requests (`session.permission.list`) are preserved instead of
being cancelled.

Supports:
  1. Running a Spec Kit command from `.opencode/commands/<name>.md`
     (expanding `$ARGUMENTS`, pre-executing `!...` shell directives, and
     honoring frontmatter `agent:` / `model:`).
  2. Running any OpenCode agent directly (`--agent product-owner`,
     `--agent tech-lead`, `--agent sdt-tester`, etc.) with `--prompt`.
  3. Continuing a session with `--session <id> --prompt "..."`.
  4. Replying to a pending dynamic question form with
     `--session <id> --reply-form <form_id> --answer '{"q0": "..."}'`.
  5. Optional `--standalone` fallback using `opencode run --standalone`
     (supports `--worktree`, though OpenCode cancels `question` tools in `run`).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
BANG_SHELL_RE = re.compile(r"!`([^`]+)`")


def find_opencode_bin() -> str:
    """Resolve the OpenCode binary path across PATH and common install locations."""
    env_bin = os.environ.get("OPENCODE_BIN")
    if env_bin and os.path.isfile(env_bin) and os.access(env_bin, os.X_OK):
        return env_bin

    found = shutil.which("opencode")
    if found:
        return found

    home = Path.home()
    candidates = [
        home / ".local/share/mise/installs/opencode/latest/node_modules/.bin/opencode",
        home / ".local/share/mise/shims/opencode",
        home / ".opencode/bin/opencode",
        home / ".local/bin/opencode",
    ]
    for cand in candidates:
        if cand.is_file() and os.access(cand, os.X_OK):
            return str(cand)

    raise FileNotFoundError(
        "opencode binary not found on PATH or standard install locations; set OPENCODE_BIN"
    )


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Extract simple key: value fields from YAML frontmatter and return body."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("-"):
            key, val = line.split(":", 1)
            meta[key.strip()] = val.strip().strip('"').strip("'")
    return meta, text[match.end() :]


def expand_bang_shell(text: str, cwd: Path) -> str:
    """Expand OpenCode !`cmd` command directives in command markdown."""

    def _run(match: re.Match[str]) -> str:
        cmd = match.group(1)
        proc = subprocess.run(
            cmd,
            shell=True,
            cwd=str(cwd),
            capture_output=True,
            text=True,
        )
        out = proc.stdout.strip()
        if proc.returncode != 0:
            err = proc.stderr.strip()
            return f"[Pre-executed `{cmd}` failed (exit {proc.returncode})]\n{out}\n{err}".strip()
        return f"[Pre-executed `{cmd}` (exit 0)]\n{out}".strip()

    return BANG_SHELL_RE.sub(_run, text)


def load_command_prompt(
    project_dir: Path, command_name: str, user_args: str
) -> tuple[dict[str, str], str]:
    """Load and expand a command from .opencode/commands/<name>.md.

    Accepts both dotted OpenCode names (`speckit.clarify`) and hyphenated
    Spec Kit doc names (`speckit-clarify`).
    """
    cmd_name = command_name.lstrip("/")
    commands_dir = project_dir / ".opencode" / "commands"
    candidates = [cmd_name]
    if cmd_name.startswith("speckit-"):
        candidates.append("speckit." + cmd_name[len("speckit-") :])
    elif cmd_name.startswith("speckit."):
        candidates.append("speckit-" + cmd_name[len("speckit.") :])

    cmd_path: Path | None = None
    for cand in candidates:
        probe = commands_dir / f"{cand}.md"
        if probe.is_file():
            cmd_path = probe
            cmd_name = cand
            break
    if cmd_path is None:
        raise FileNotFoundError(
            f"Command file not found in {commands_dir} for {command_name!r}"
        )

    raw = cmd_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)
    body = body.replace("$ARGUMENTS", user_args)
    body = expand_bang_shell(body, project_dir)
    prompt = (
        f"Execute the following OpenCode command (`/{cmd_name}`) in `{project_dir}`.\n"
        f"Do not search for or re-read `{cmd_path.relative_to(project_dir)}` because its "
        "full expanded specification is provided below.\n\n"
        f"{body}"
    )
    return meta, prompt


def api_call(opencode_bin: str, args: list[str], server: str | None = None) -> Any:
    """Invoke `opencode api` and parse JSON response if present."""
    cmd = [opencode_bin, "api"]
    if server:
        cmd.extend(["--server", server])
    cmd.extend(args)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"opencode api failed ({proc.returncode}): {' '.join(args)}\n"
            f"STDOUT: {proc.stdout}\nSTDERR: {proc.stderr}"
        )
    if not proc.stdout.strip():
        return None
    return json.loads(proc.stdout)


def ensure_service(opencode_bin: str) -> None:
    """Ensure the OpenCode background service is running."""
    status = subprocess.run(
        [opencode_bin, "service", "status"], capture_output=True, text=True
    )
    if status.returncode == 0 and status.stdout.strip().startswith("http"):
        return
    start = subprocess.run(
        [opencode_bin, "service", "start"], capture_output=True, text=True
    )
    if start.returncode != 0:
        raise RuntimeError(
            f"Failed to start opencode service: {start.stdout}\n{start.stderr}"
        )


def parse_model_ref(model: str) -> dict[str, str]:
    """Convert `provider/model#variant` or `provider/model` into Model.Ref."""
    if "/" not in model:
        raise ValueError(f"Model must be provider/model[#variant], got: {model}")
    provider_id, rest = model.split("/", 1)
    model_id = rest.split("#", 1)[0]
    ref = {"providerID": provider_id, "id": model_id}
    if "#" in rest:
        ref["variant"] = rest.split("#", 1)[1]
    return ref


def extract_session_messages(
    opencode_bin: str, session_id: str, server: str | None
) -> dict[str, Any]:
    """Read assistant text and tools used from a session in chronological order."""
    msgs = api_call(
        opencode_bin,
        [
            "session.message.list",
            "--param",
            f"sessionID={session_id}",
            "--param",
            "order=asc",
        ],
        server,
    )["data"]
    tools: list[dict[str, Any]] = []
    last_assistant_text = ""
    all_assistant_texts: list[str] = []
    session_error: Any = None

    for msg in msgs:
        mtype = msg.get("type")
        if mtype == "idle" and msg.get("outcome") == "failed" and msg.get("error"):
            session_error = msg["error"]
            continue
        if mtype != "assistant":
            continue
        msg_texts: list[str] = []
        for part in msg.get("content", []):
            ptype = part.get("type")
            if ptype == "text" and isinstance(part.get("text"), str):
                msg_texts.append(part["text"])
            elif ptype == "tool":
                state = part.get("state") if isinstance(part.get("state"), dict) else {}
                tools.append(
                    {
                        "tool": part.get("name"),
                        "status": state.get("status"),
                        "input": state.get("input"),
                    }
                )
        if msg_texts:
            joined = "\n".join(msg_texts).strip()
            all_assistant_texts.append(joined)
            last_assistant_text = joined

    return {
        "tools_used": tools,
        "response_text": last_assistant_text,
        "assistant_turns": len(all_assistant_texts),
        "error": session_error,
    }


def collect_session_tree(
    opencode_bin: str,
    root_session_id: str,
    project_dir: Path,
    server: str | None,
) -> tuple[set[str], bool]:
    """Return all session IDs in the tree rooted at `root_session_id` and whether any child is busy."""
    tree_ids: set[str] = {root_session_id}
    frontier: list[str] = [root_session_id]
    any_child_busy = False

    while frontier:
        parent_id = frontier.pop()
        children = api_call(
            opencode_bin,
            [
                "session.list",
                "--param",
                f"directory={project_dir}",
                "--param",
                f"parentID={parent_id}",
                "--param",
                "limit=100",
            ],
            server,
        ).get("data", [])
        for child in children:
            cid = child.get("id")
            if not cid or cid in tree_ids:
                continue
            tree_ids.add(cid)
            frontier.append(cid)
            tinfo = child.get("time") or {}
            b_ts = tinfo.get("busy") or 0
            i_ts = tinfo.get("idle") or 0
            if b_ts and not (i_ts >= b_ts and i_ts > 0):
                any_child_busy = True

    return tree_ids, any_child_busy


def wait_for_session_or_form(
    opencode_bin: str,
    session_id: str,
    project_dir: Path,
    server: str | None,
    auto_approve_permissions: bool,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Wait until session tree completes, handling child subagent permissions and forms."""
    deadline = time.time() + timeout_seconds
    approved_permissions: list[dict[str, Any]] = []
    loc_param = f"location[directory]={project_dir}"

    while time.time() < deadline:
        all_forms = api_call(
            opencode_bin, ["form.list", "--param", loc_param], server
        ).get("data", [])
        all_perms = api_call(
            opencode_bin, ["permission.request.list", "--param", loc_param], server
        ).get("data", [])

        tree_ids: set[str] | None = None
        if all_forms or all_perms:
            tree_ids, _ = collect_session_tree(
                opencode_bin, session_id, project_dir, server
            )

        if all_forms and tree_ids is not None:
            tree_forms = [f for f in all_forms if f.get("sessionID") in tree_ids]
            if tree_forms:
                form = tree_forms[0]
                return {
                    "status": "awaiting_form",
                    "session_id": session_id,
                    "form_session_id": form.get("sessionID"),
                    "form_id": form["id"],
                    "form": form,
                    "approved_permissions": approved_permissions,
                    "exit_code": 0,
                }

        if all_perms and tree_ids is not None:
            tree_perms = [p for p in all_perms if p.get("sessionID") in tree_ids]
            if tree_perms:
                if not auto_approve_permissions:
                    return {
                        "status": "awaiting_permission",
                        "session_id": session_id,
                        "permissions": tree_perms,
                        "exit_code": 0,
                    }
                for perm in tree_perms:
                    target_sid = perm.get("sessionID") or session_id
                    api_call(
                        opencode_bin,
                        [
                            "session.permission.reply",
                            "--param",
                            f"sessionID={target_sid}",
                            "--param",
                            f"requestID={perm['id']}",
                            "--data",
                            json.dumps({"decision": "always"}),
                        ],
                        server,
                    )
                    approved_permissions.append(
                        {
                            "id": perm.get("id"),
                            "session_id": target_sid,
                            "action": perm.get("action"),
                            "resources": perm.get("resources"),
                        }
                    )

        info = api_call(
            opencode_bin,
            ["session.get", "--param", f"sessionID={session_id}"],
            server,
        )["data"]
        time_info = info.get("time") or {}
        busy_ts = time_info.get("busy") or 0
        idle_ts = time_info.get("idle") or 0
        is_root_idle = (not busy_ts) or (idle_ts >= busy_ts and idle_ts > 0)
        if is_root_idle:
            tree_ids_after, any_child_busy = collect_session_tree(
                opencode_bin, session_id, project_dir, server
            )
            forms_after = [
                f
                for f in api_call(
                    opencode_bin, ["form.list", "--param", loc_param], server
                ).get("data", [])
                if f.get("sessionID") in tree_ids_after
            ]
            if forms_after:
                form = forms_after[0]
                return {
                    "status": "awaiting_form",
                    "session_id": session_id,
                    "form_session_id": form.get("sessionID"),
                    "form_id": form["id"],
                    "form": form,
                    "approved_permissions": approved_permissions,
                    "exit_code": 0,
                }
            perms_after = [
                p
                for p in api_call(
                    opencode_bin,
                    ["permission.request.list", "--param", loc_param],
                    server,
                ).get("data", [])
                if p.get("sessionID") in tree_ids_after
            ]
            if perms_after or any_child_busy:
                time.sleep(0.5)
                continue

            extracted = extract_session_messages(opencode_bin, session_id, server)
            outcome = info.get("outcome")
            failed = outcome == "failed" or extracted.get("error") is not None
            result = {
                "status": "failed" if failed else "completed",
                "outcome": outcome,
                "session_id": session_id,
                "tokens": info.get("tokens"),
                "cost": info.get("cost"),
                "approved_permissions": approved_permissions,
                **extracted,
                "exit_code": 1 if failed else 0,
            }
            if result["error"] is None:
                result.pop("error", None)
            return result

        time.sleep(1.0)

    return {
        "status": "timeout",
        "session_id": session_id,
        "approved_permissions": approved_permissions,
        "exit_code": 124,
    }


def parse_ndjson_events(stdout: str) -> dict[str, Any]:
    """Summarize OpenCode `run --format json` NDJSON output (standalone fallback)."""
    session_id: str | None = None
    tools: list[dict[str, Any]] = []
    texts: list[str] = []
    finish_reason: str | None = None
    tokens: dict[str, Any] = {}
    cost: float = 0.0

    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            ev = json.loads(stripped)
        except json.JSONDecodeError:
            continue
        if not session_id and isinstance(ev.get("sessionID"), str):
            session_id = ev["sessionID"]
        ev_type = ev.get("type")
        part = ev.get("part") if isinstance(ev.get("part"), dict) else {}
        if ev_type == "text" and isinstance(part.get("text"), str):
            texts.append(part["text"])
        elif ev_type == "tool_use":
            state = part.get("state") if isinstance(part.get("state"), dict) else {}
            tools.append(
                {
                    "tool": part.get("tool"),
                    "status": state.get("status"),
                    "input": state.get("input"),
                }
            )
        elif ev_type == "step_finish":
            finish_reason = part.get("reason") or finish_reason
            if isinstance(part.get("cost"), (int, float)):
                cost += float(part["cost"])
            if isinstance(part.get("tokens"), dict):
                tokens = part["tokens"]

    return {
        "status": "completed",
        "session_id": session_id,
        "finish_reason": finish_reason,
        "cost": cost,
        "tokens": tokens,
        "tools_used": tools,
        "response_text": "\n".join(texts).strip(),
    }


def run_standalone(args: argparse.Namespace, opencode_bin: str, project_dir: Path) -> int:
    """Fallback execution using `opencode run --standalone` (no interactive forms)."""
    cmd_meta: dict[str, str] = {}
    if args.command:
        cmd_meta, prompt_text = load_command_prompt(project_dir, args.command, args.args)
    elif args.prompt_file:
        prompt_text = Path(args.prompt_file).read_text(encoding="utf-8")
    else:
        prompt_text = args.prompt

    agent = args.agent or cmd_meta.get("agent")
    if not args.agent and agent and agent.startswith("speckit."):
        agent = None
    model = args.model or cmd_meta.get("model")

    cli_cmd: list[str] = [opencode_bin, "run", "--standalone", "--auto", "--format", "json"]
    if not args.no_archived:
        cli_cmd.append("--archived")
    if args.session:
        cli_cmd.extend(["--session", args.session])
    if args.worktree:
        cli_cmd.extend(["--worktree", args.worktree])
    if agent:
        cli_cmd.extend(["--agent", agent])
    if model:
        cli_cmd.extend(["--model", model])
    if args.title:
        cli_cmd.extend(["--title", args.title])
    for fpath in args.file:
        cli_cmd.extend(["--file", fpath])
    cli_cmd.append(prompt_text)

    proc = subprocess.run(cli_cmd, cwd=str(project_dir), capture_output=True, text=True)
    summary = parse_ndjson_events(proc.stdout)
    summary["exit_code"] = proc.returncode
    summary["agent_used"] = agent or "default"
    summary["model_used"] = model or "default"
    if proc.stderr.strip():
        summary["stderr"] = proc.stderr.strip()
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute OpenCode commands, agents, or form replies for Hybrid SDD."
    )
    parser.add_argument("--project", default=".", help="Project or worktree root directory.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--command", help="Spec Kit command name (e.g. speckit.specify).")
    group.add_argument("--prompt", help="Direct prompt text (e.g. with --agent or --session).")
    group.add_argument("--prompt-file", help="Read direct prompt text from a file.")
    group.add_argument("--reply-form", help="Pending form ID (frm_...) to answer.")

    parser.add_argument("--args", default="", help="Arguments for $ARGUMENTS with --command.")
    parser.add_argument("--answer", help="JSON object of answers when using --reply-form.")
    parser.add_argument("--agent", help="OpenCode agent name (e.g. product-owner, tech-lead).")
    parser.add_argument("--model", help="Model in provider/model[#variant] format.")
    parser.add_argument("--session", "-s", help="Existing OpenCode session ID.")
    parser.add_argument("--worktree", "-w", help="Worktree name (used with --standalone).")
    parser.add_argument("--file", "-f", action="append", default=[], help="Attach file(s).")
    parser.add_argument("--title", help="Optional session title.")
    parser.add_argument("--server", help="Optional explicit OpenCode server URL.")
    parser.add_argument("--timeout", type=int, default=1800, help="Wait timeout in seconds.")
    parser.add_argument("--no-auto-permission", action="store_true", help="Do not auto-approve permission asks.")
    parser.add_argument("--no-archived", action="store_true", help="Do not archive session after completion.")
    parser.add_argument(
        "--standalone",
        action="store_true",
        help="Use `opencode run --standalone` instead of the OpenCode service (cancels `question` forms).",
    )
    args = parser.parse_args()

    project_dir = Path(args.project).resolve()
    opencode_bin = find_opencode_bin()

    if args.standalone:
        if args.reply_form:
            parser.error("--reply-form requires the OpenCode service (cannot use --standalone).")
        return run_standalone(args, opencode_bin, project_dir)

    if not args.server:
        ensure_service(opencode_bin)

    if args.reply_form:
        if not args.session or not args.answer:
            parser.error("--reply-form requires both --session and --answer '<json>'.")
        answer_obj = json.loads(args.answer)
        form_session_id = args.session
        all_forms = api_call(
            opencode_bin,
            ["form.list", "--param", f"location[directory]={project_dir}"],
            args.server,
        ).get("data", [])
        for f in all_forms:
            if f.get("id") == args.reply_form and f.get("sessionID"):
                form_session_id = f["sessionID"]
                break
        api_call(
            opencode_bin,
            [
                "session.form.reply",
                "--param",
                f"sessionID={form_session_id}",
                "--param",
                f"formID={args.reply_form}",
                "--data",
                json.dumps({"answer": answer_obj}),
            ],
            args.server,
        )
        result = wait_for_session_or_form(
            opencode_bin,
            args.session,
            project_dir,
            args.server,
            auto_approve_permissions=not args.no_auto_permission,
            timeout_seconds=args.timeout,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return result.get("exit_code", 0)

    cmd_meta: dict[str, str] = {}
    if args.command:
        cmd_meta, prompt_text = load_command_prompt(project_dir, args.command, args.args)
    elif args.prompt_file:
        prompt_text = Path(args.prompt_file).read_text(encoding="utf-8")
    else:
        prompt_text = args.prompt

    agent = args.agent or cmd_meta.get("agent")
    if not args.agent and agent and agent.startswith("speckit."):
        agent = None
    model = args.model or cmd_meta.get("model")

    session_id = args.session
    if not session_id:
        create_payload: dict[str, Any] = {"location": {"directory": str(project_dir)}}
        if args.title:
            create_payload["title"] = args.title
        elif args.command:
            create_payload["title"] = f"hybrid-sdd: {args.command}"
        elif agent:
            create_payload["title"] = f"hybrid-sdd: @{agent}"
        if agent:
            create_payload["agent"] = agent
        if model:
            create_payload["model"] = parse_model_ref(model)

        created = api_call(
            opencode_bin,
            ["session.create", "--data", json.dumps(create_payload)],
            args.server,
        )
        session_id = created["data"]["id"]

    prompt_payload: dict[str, Any] = {"text": prompt_text}
    if args.file:
        attachments = []
        for fpath in args.file:
            p = Path(fpath)
            if not p.is_absolute():
                p = (project_dir / p).resolve()
            attachments.append(
                {
                    "type": "file",
                    "url": p.as_uri(),
                    "filename": p.name,
                    "mime": "text/plain",
                }
            )
        prompt_payload["files"] = attachments

    api_call(
        opencode_bin,
        [
            "session.prompt",
            "--param",
            f"sessionID={session_id}",
            "--data",
            json.dumps(prompt_payload),
        ],
        args.server,
    )

    result = wait_for_session_or_form(
        opencode_bin,
        session_id,
        project_dir,
        args.server,
        auto_approve_permissions=not args.no_auto_permission,
        timeout_seconds=args.timeout,
    )
    result["agent_used"] = agent or "default"
    result["model_used"] = model or "default"
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result.get("exit_code", 0)


if __name__ == "__main__":
    sys.exit(main())
