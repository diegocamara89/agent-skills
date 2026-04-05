from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path
from typing import Any, Iterable


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_ai_cli import (  # noqa: E402
    CallResult,
    build_provider_command,
    discover_provider_command,
    extract_first_json,
    run_command,
)


HANDOFF_KEYS = [
    "status",
    "task_summary",
    "changed_files",
    "tests_run",
    "risks",
    "analyst_summary",
    "next_action",
    "backend_used",
    "failure_kind",
    "account_switch_recommended",
    "next_backend",
]

DEFAULT_QUOTA_PATTERNS = [
    "quota exceeded",
    "usage limit reached",
    "rate limit reached",
    "rate limit exceeded",
    "monthly usage limit",
    "daily usage limit",
    "please try again later",
    "too many requests",
]

DEFAULT_SHARED_CLAUDE_SUBDIRS = ["skills", "plugins", "commands"]
DEFAULT_SHARED_CLAUDE_FILES = ["settings.json", "trustedFolders.json"]
DEFAULT_HIGH_RISK_FLAGS = [
    "auth",
    "billing",
    "compliance",
    "data-loss",
    "infra",
    "migration",
    "multi-file",
    "pii",
    "privacy",
    "refactor",
    "schema",
    "security",
    "sensitive-data",
]

DEFAULT_MAX_CLAUDE_PROFILES = 10


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def expand_path(value: str | None) -> str:
    if not value:
        return ""
    return str(Path(os.path.expandvars(os.path.expanduser(value))).resolve())


def ensure_directory(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write_text(path: str, content: str) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def read_json(path: str, default: Any) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        return default
    with file_path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def write_json(path: str, data: Any) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


def safe_discover(provider: str) -> str:
    try:
        return discover_provider_command(provider)
    except Exception:
        return ""


def normalize_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        stripped = value.strip()
        return [stripped] if stripped else []
    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for item in value:
            items.extend(normalize_text_list(item))
        return items
    return [str(value).strip()]


def normalize_flag(value: str) -> str:
    return value.strip().lower().replace("_", "-").replace(" ", "-")


def first_non_empty(*values: Any) -> str:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            stripped = value.strip()
            if stripped:
                return stripped
            continue
        text = str(value).strip()
        if text:
            return text
    return ""


def summarize_text(text: str, limit: int = 280) -> str:
    flattened = " ".join(text.split())
    if len(flattened) <= limit:
        return flattened
    return flattened[: limit - 3].rstrip() + "..."


def build_default_config() -> dict[str, Any]:
    home = Path.home()
    orchestrator_root = home / ".claude-orchestrator"
    profile_root = home / ".claude-profiles"
    profile_names = [f"claude-{chr(ord('a') + index)}" for index in range(DEFAULT_MAX_CLAUDE_PROFILES)]
    return {
        "version": 1,
        "claude_base_dir": str(home / ".claude"),
        "profile_root": str(profile_root),
        "state_file": str(orchestrator_root / "state.json"),
        "shared_claude_subdirs": list(DEFAULT_SHARED_CLAUDE_SUBDIRS),
        "shared_claude_files": list(DEFAULT_SHARED_CLAUDE_FILES),
        "profiles": [
            {"name": name, "config_dir": str(profile_root / name)}
            for name in profile_names
        ],
        "commands": {
            "claude": {"path": safe_discover("claude")},
            "codex": {"path": safe_discover("codex")},
            "gemini": {"path": safe_discover("gemini")},
            "qwen": {"path": safe_discover("qwen")},
        },
        "quota_patterns": list(DEFAULT_QUOTA_PATTERNS),
        "validation": {
            "max_changed_files_without_validation": 3,
            "require_tests_when_files_change": True,
            "always_validate_flags": list(DEFAULT_HIGH_RISK_FLAGS),
        },
    }


def merge_config(defaults: dict[str, Any], incoming: dict[str, Any]) -> dict[str, Any]:
    merged = dict(defaults)
    merged.update({k: v for k, v in incoming.items() if k != "commands"})

    commands = dict(defaults.get("commands", {}))
    for provider, value in incoming.get("commands", {}).items():
        if isinstance(value, dict):
            commands[provider] = {**commands.get(provider, {}), **value}
        else:
            commands[provider] = {"path": str(value)}
    merged["commands"] = commands
    return merged


def load_config(config_path: str | None = None) -> tuple[dict[str, Any], str]:
    default_config = build_default_config()
    resolved_path = expand_path(config_path) if config_path else str(Path.home() / ".claude-orchestrator" / "config.json")
    existing = read_json(resolved_path, None)
    config = merge_config(default_config, existing or {})

    config["claude_base_dir"] = expand_path(config.get("claude_base_dir"))
    config["profile_root"] = expand_path(config.get("profile_root"))
    config["state_file"] = expand_path(config.get("state_file"))
    config["shared_claude_subdirs"] = normalize_text_list(config.get("shared_claude_subdirs"))
    config["shared_claude_files"] = normalize_text_list(config.get("shared_claude_files"))
    config["quota_patterns"] = normalize_text_list(config.get("quota_patterns")) or list(DEFAULT_QUOTA_PATTERNS)

    profiles = []
    for profile in config.get("profiles", []):
        name = first_non_empty(profile.get("name"))
        config_dir = expand_path(profile.get("config_dir"))
        if not name or not config_dir:
            continue
        profiles.append({"name": name, "config_dir": config_dir})
    if not profiles:
        raise ValueError("A configuracao do orquestrador precisa de pelo menos um perfil Claude.")
    config["profiles"] = profiles
    return config, resolved_path


def new_profile_runtime_state(profile_name: str, config_dir: str) -> dict[str, Any]:
    return {
        "profileId": str(profile_name),
        "configDir": str(config_dir),
        "loggedIn": False,
        "state": "auth_required",
        "leaseOwner": "",
        "leaseExpiresAt": None,
        "cooldownUntil": None,
        "lastSuccessAt": None,
        "lastFailureAt": None,
        "lastFailureKind": "",
        "lastKnownModel": "",
        "quotaNote": "",
    }


def normalize_profile_runtime_state(profile_state: dict[str, Any], *, source: str = "state") -> dict[str, Any]:
    if source == "cli":
        if "loggedIn" in profile_state:
            if not bool(profile_state["loggedIn"]):
                profile_state["state"] = "auth_required"
            elif not profile_state.get("state") or profile_state.get("state") == "auth_required":
                profile_state["state"] = "available"
    else:
        if not profile_state.get("state"):
            profile_state["state"] = "available" if bool(profile_state.get("loggedIn")) else "auth_required"
        if profile_state.get("state") == "auth_required":
            profile_state["loggedIn"] = False

    if not profile_state.get("state"):
        profile_state["state"] = "auth_required"
    return profile_state


def new_state_store() -> dict[str, Any]:
    return {
        "version": 1,
        "updatedAt": None,
        "active_profile": None,
        "last_updated_at": None,
        "profiles": {},
    }


def ensure_profile_runtime_entry(state: dict[str, Any], profile_name: str, config_dir: str) -> dict[str, Any]:
    profiles = state.setdefault("profiles", {})
    existing = profiles.get(profile_name)
    runtime_state = dict(existing) if isinstance(existing, dict) else {}

    if "config_dir" in runtime_state and "configDir" not in runtime_state:
        runtime_state["configDir"] = runtime_state["config_dir"]

    runtime_state.setdefault("profileId", str(profile_name))
    runtime_state.setdefault("configDir", str(config_dir))
    runtime_state.setdefault("loggedIn", False)
    runtime_state.setdefault("state", "auth_required")
    normalize_profile_runtime_state(runtime_state, source="state")
    profiles[profile_name] = runtime_state
    return runtime_state


def load_state(state_file: str, profiles: list[dict[str, str]] | None = None) -> dict[str, Any]:
    raw = read_json(state_file, None)
    state = new_state_store()
    if isinstance(raw, dict):
        state.update(raw)
    if not isinstance(state.get("profiles"), dict):
        state["profiles"] = {}
    for profile_name, runtime_state in list(state["profiles"].items()):
        if not isinstance(runtime_state, dict):
            state["profiles"][profile_name] = new_profile_runtime_state(str(profile_name), "")
            continue
        normalize_profile_runtime_state(runtime_state, source="state")
    for profile in profiles or []:
        ensure_profile_runtime_entry(state, profile["name"], profile["config_dir"])
    return state


def save_state(state_file: str, state: dict[str, Any]) -> None:
    timestamp = _now_iso()
    state["version"] = int(state.get("version") or 1)
    state["updatedAt"] = timestamp
    state["last_updated_at"] = timestamp
    if not isinstance(state.get("profiles"), dict):
        state["profiles"] = {}
    for profile_name, runtime_state in list(state["profiles"].items()):
        if not isinstance(runtime_state, dict):
            state["profiles"][profile_name] = new_profile_runtime_state(str(profile_name), "")
            continue
        normalize_profile_runtime_state(runtime_state, source="state")
    write_json(state_file, state)


def get_command_path(config: dict[str, Any], provider: str) -> str | None:
    provider_cfg = config.get("commands", {}).get(provider, {})
    if isinstance(provider_cfg, dict):
        path = first_non_empty(provider_cfg.get("path"))
        return path or None
    if isinstance(provider_cfg, str) and provider_cfg.strip():
        return provider_cfg.strip()
    return None


def profile_order(
    profiles: list[dict[str, str]],
    state: dict[str, Any],
    preferred_profile: str | None = None,
    *,
    now: Any = None,
) -> list[dict[str, str]]:
    if not preferred_profile and state.get("active_profile"):
        preferred_profile = str(state["active_profile"])

    if not preferred_profile:
        ordered = list(profiles)
    else:
        ordered = [profile for profile in profiles if profile["name"] == preferred_profile]
        ordered.extend(profile for profile in profiles if profile["name"] != preferred_profile)

    bootstrap_candidates: list[dict[str, str]] = []
    available: list[dict[str, str]] = []
    for profile in ordered or list(profiles):
        runtime_state = ensure_profile_runtime_entry(state, profile["name"], profile["config_dir"])
        expire_lease_if_stale(runtime_state, now=now)
        if is_profile_available(runtime_state, now=now):
            available.append(profile)
            continue
        if (
            runtime_state.get("state") == "auth_required"
            and not first_non_empty(runtime_state.get("lastFailureKind"))
            and not runtime_state.get("lastFailureAt")
        ):
            bootstrap_candidates.append(profile)
    return available or bootstrap_candidates


def mklink_junction(link_path: Path, target_path: Path) -> bool:
    if os.name != "nt":
        return False
    if link_path.exists():
        return True
    link_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        os.environ.get("COMSPEC", "cmd.exe"),
        "/d",
        "/s",
        "/c",
        f'mklink /J "{link_path}" "{target_path}"',
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    return proc.returncode == 0


def ensure_shared_directory(source: Path, dest: Path, prefer_junction: bool) -> str:
    if dest.exists():
        return "existing"
    if prefer_junction and mklink_junction(dest, source):
        return "junction"
    shutil.copytree(source, dest, dirs_exist_ok=True)
    return "copy"


def bootstrap_profiles(config: dict[str, Any], *, prefer_junction: bool = True) -> dict[str, Any]:
    base_dir = Path(config["claude_base_dir"])
    ensure_directory(config["profile_root"])
    ensure_directory(str(Path(config["state_file"]).parent))

    results = []
    for profile in config["profiles"]:
        profile_dir = Path(profile["config_dir"])
        ensure_directory(str(profile_dir))
        shared_dirs: dict[str, str] = {}
        shared_files: list[str] = []

        for subdir in config["shared_claude_subdirs"]:
            source = base_dir / subdir
            dest = profile_dir / subdir
            if not source.exists():
                shared_dirs[subdir] = "missing-source"
                continue
            shared_dirs[subdir] = ensure_shared_directory(source, dest, prefer_junction=prefer_junction)

        for filename in config["shared_claude_files"]:
            source = base_dir / filename
            dest = profile_dir / filename
            if not source.exists():
                continue
            if not dest.exists():
                shutil.copy2(source, dest)
                shared_files.append(filename)

        results.append(
            {
                "profile": profile["name"],
                "config_dir": str(profile_dir),
                "shared_dirs": shared_dirs,
                "shared_files": shared_files,
            }
        )

    state = load_state(config["state_file"], profiles=config["profiles"])
    if not state.get("active_profile"):
        state["active_profile"] = config["profiles"][0]["name"]
        save_state(config["state_file"], state)

    return {
        "status": "ok",
        "profile_root": config["profile_root"],
        "state_file": config["state_file"],
        "profiles": results,
    }


def is_quota_error(stdout: str, stderr: str, patterns: Iterable[str]) -> bool:
    haystack = f"{stdout}\n{stderr}".lower()
    return any(pattern.lower() in haystack for pattern in patterns)


def get_claude_failure_kind(
    stdout: str,
    stderr: str,
    returncode: int,
    quota_patterns: Iterable[str] | None = None,
) -> str:
    haystack = f"{stdout}\n{stderr}".lower()

    if "not logged in" in haystack or "/login" in haystack or "session expired" in haystack:
        return "auth_required"
    if "rate limit" in haystack or "too many requests" in haystack or "429" in haystack:
        return "rate_limited_transient"

    quota_markers = [
        "usage limit reached",
        "quota exceeded",
        "monthly usage limit",
        "daily usage limit",
        "weekly usage limit",
    ]
    if any(marker in haystack for marker in quota_markers):
        return "quota_exhausted"
    if "please try again later" in haystack or "try again later" in haystack:
        return "backend_unavailable"

    for pattern in quota_patterns or []:
        normalized = pattern.lower().strip()
        if not normalized:
            continue
        if "rate limit" in normalized or "too many requests" in normalized or "try again later" in normalized:
            continue
        if normalized in haystack:
            return "quota_exhausted"

    if "/codex:" in haystack or "plugin" in haystack:
        return "plugin_backend_failure"
    if "codex exec" in haystack or "not recognized" in haystack or "executable" in haystack:
        return "cli_backend_failure"
    if "temporarily unavailable" in haystack or "service unavailable" in haystack or "timeout" in haystack:
        return "backend_unavailable"
    if returncode != 0:
        return "local_host_failure"
    return ""


def _parse_iso_timestamp(value: Any) -> Any:
    from datetime import datetime

    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _coerce_now(now: Any = None) -> Any:
    from datetime import datetime, timezone

    if now is None:
        return datetime.now(timezone.utc)
    if isinstance(now, datetime):
        return now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    parsed = _parse_iso_timestamp(now)
    if parsed is not None:
        return parsed
    return datetime.now(timezone.utc)


def set_profile_lease(
    profile_state: dict[str, Any],
    lease_owner: str,
    *,
    now: Any = None,
    lease_seconds: int = 300,
) -> dict[str, Any]:
    from datetime import timedelta

    current_time = _coerce_now(now)
    profile_state["leaseOwner"] = lease_owner
    profile_state["leaseExpiresAt"] = (current_time + timedelta(seconds=lease_seconds)).isoformat().replace("+00:00", "Z")
    profile_state["state"] = "active"
    normalize_profile_runtime_state(profile_state, source="state")
    return profile_state


def expire_lease_if_stale(profile_state: dict[str, Any], *, now: Any = None) -> dict[str, Any]:
    current_time = _coerce_now(now)
    lease_expires_at = _parse_iso_timestamp(profile_state.get("leaseExpiresAt"))

    if profile_state.get("state") == "active" and lease_expires_at and lease_expires_at <= current_time:
        profile_state["state"] = "available" if bool(profile_state.get("loggedIn")) else "auth_required"
        profile_state["leaseOwner"] = ""
        profile_state["leaseExpiresAt"] = None
        normalize_profile_runtime_state(profile_state, source="state")
    return profile_state


def is_profile_available(profile_state: dict[str, Any], *, now: Any = None) -> bool:
    current_time = _coerce_now(now)

    expire_lease_if_stale(profile_state, now=current_time)
    state_value = first_non_empty(profile_state.get("state")) or "auth_required"
    cooldown_until = _parse_iso_timestamp(profile_state.get("cooldownUntil"))

    if state_value == "cooling":
        if cooldown_until and cooldown_until <= current_time:
            profile_state["state"] = "available"
            profile_state["cooldownUntil"] = None
            state_value = "available"
        else:
            return False

    if state_value == "exhausted":
        if cooldown_until and cooldown_until <= current_time:
            profile_state["state"] = "available"
            profile_state["cooldownUntil"] = None
            state_value = "available"
        else:
            return False

    return state_value == "available"


def apply_profile_failure(
    profile_state: dict[str, Any],
    failure_kind: str,
    *,
    cooldown_seconds: int = 300,
) -> dict[str, Any]:
    from datetime import datetime, timedelta, timezone

    profile_state["lastFailureAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    profile_state["lastFailureKind"] = failure_kind
    profile_state["leaseOwner"] = ""
    profile_state["leaseExpiresAt"] = None

    if failure_kind == "quota_exhausted":
        profile_state["state"] = "exhausted"
        profile_state["cooldownUntil"] = None
    elif failure_kind in {"rate_limited_transient", "backend_unavailable"}:
        profile_state["state"] = "cooling"
        profile_state["cooldownUntil"] = (
            datetime.now(timezone.utc) + timedelta(seconds=cooldown_seconds)
        ).isoformat().replace("+00:00", "Z")
    elif failure_kind == "auth_required":
        profile_state["state"] = "auth_required"
        profile_state["loggedIn"] = False
        profile_state["cooldownUntil"] = None
    elif failure_kind == "local_host_failure":
        profile_state["state"] = "unhealthy"
        profile_state["cooldownUntil"] = None

    normalize_profile_runtime_state(profile_state, source="state")
    return profile_state


def mark_profile_success(profile_state: dict[str, Any]) -> dict[str, Any]:
    from datetime import datetime, timezone

    profile_state["loggedIn"] = True
    profile_state["state"] = "available"
    profile_state["cooldownUntil"] = None
    profile_state["leaseOwner"] = ""
    profile_state["leaseExpiresAt"] = None
    profile_state["lastSuccessAt"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    profile_state["lastFailureKind"] = ""
    normalize_profile_runtime_state(profile_state, source="state")
    return profile_state


def build_planner_prompt(task: str) -> str:
    return textwrap.dedent(
        f"""
        Voce e o planejador principal do fluxo Claude -> Codex -> Claude.
        Analise a tarefa abaixo e responda em JSON valido.

        Campos obrigatorios:
        - mode: "claude_only" ou "codex"
        - task_summary: resumo curto
        - execution_required: boolean
        - execution_prompt: prompt objetivo para o Codex se houver execucao
        - risks: lista curta de riscos
        - force_validation: boolean
        - validation_prompt: prompt curto para validacao final do Claude quando aplicavel
        - next_action: proximo passo recomendado

        Tarefa:
        {task}
        """
    ).strip()


def build_validation_prompt(task: str, planner: dict[str, Any], handoff: dict[str, Any]) -> str:
    planner_json = json.dumps(planner, ensure_ascii=False, indent=2)
    handoff_json = json.dumps(handoff, ensure_ascii=False, indent=2)
    return textwrap.dedent(
        f"""
        Voce esta validando um trabalho executado pelo Codex.
        Responda em JSON valido com:
        - verdict: "approve", "needs_changes" ou "blocked"
        - summary: resumo curto
        - concerns: lista de pontos de atencao
        - next_action: proximo passo recomendado

        Tarefa original:
        {task}

        Plano:
        {planner_json}

        Handoff do executor:
        {handoff_json}
        """
    ).strip()


def build_rehydration_payload(task_context: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "task_summary": first_non_empty(task_context.get("task_summary")),
        "current_goal": first_non_empty(task_context.get("current_goal")),
        "constraints": normalize_text_list(task_context.get("constraints")),
        "relevant_files": list(task_context.get("relevant_files") or []),
        "last_plan_summary": first_non_empty(task_context.get("last_plan_summary")),
        "executor_or_validator_checkpoint": first_non_empty(task_context.get("executor_or_validator_checkpoint")),
        "pending_decision": first_non_empty(task_context.get("pending_decision")),
    }
    raw_budget = task_context.get("token_budget_hint", 4000)
    budget = max(int(4000 if raw_budget is None else raw_budget), 1)
    estimate = len(json.dumps(payload, ensure_ascii=False)) // 4

    if estimate > budget:
        payload["relevant_files"] = []
        estimate = len(json.dumps(payload, ensure_ascii=False)) // 4
        if estimate > budget:
            return {
                "status": "blocked",
                "blocking_reason": "rehydration_budget_exceeded",
                "estimated_tokens": estimate,
            }

    return {
        "status": "ok",
        "payload": payload,
        "estimated_tokens": estimate,
    }


def normalize_planner_decision(
    original_task: str,
    raw_text: str,
    *,
    force_validation: bool = False,
    skip_validation: bool = False,
) -> dict[str, Any]:
    payload = extract_first_json(raw_text)
    if not isinstance(payload, dict):
        payload = {}

    task_summary = first_non_empty(
        payload.get("task_summary"),
        payload.get("summary"),
        summarize_text(original_task, limit=180),
    )
    risks = [normalize_flag(item) for item in normalize_text_list(payload.get("risks"))]
    mode = first_non_empty(payload.get("mode")).lower() or "codex"
    if mode not in {"claude_only", "codex"}:
        mode = "codex"

    decision = {
        "mode": mode,
        "task_summary": task_summary,
        "execution_required": bool(payload.get("execution_required", mode != "claude_only")),
        "execution_prompt": first_non_empty(payload.get("execution_prompt"), payload.get("executor_prompt"), original_task),
        "risks": risks,
        "force_validation": bool(payload.get("force_validation")) or force_validation,
        "validation_prompt": first_non_empty(payload.get("validation_prompt")),
        "next_action": first_non_empty(payload.get("next_action"), "executar"),
        "planner_excerpt": summarize_text(raw_text, limit=400),
    }

    if skip_validation:
        decision["force_validation"] = False

    return decision


def normalize_executor_failure(
    *,
    backend_used: str,
    failure_kind: str,
    plugin_failed: bool,
    cli_failed: bool,
) -> dict[str, Any]:
    if failure_kind == "plugin_backend_failure" and not cli_failed:
        return {
            "backend_used": backend_used,
            "failure_kind": failure_kind,
            "account_switch_recommended": False,
            "next_backend": "cli",
        }
    if failure_kind == "cli_backend_failure" and plugin_failed:
        return {
            "backend_used": backend_used,
            "failure_kind": failure_kind,
            "account_switch_recommended": False,
            "next_backend": "",
        }
    return {
        "backend_used": backend_used,
        "failure_kind": failure_kind,
        "account_switch_recommended": failure_kind in {"quota_exhausted", "rate_limited_transient"},
        "next_backend": "",
    }


def normalize_handoff(
    result: CallResult,
    *,
    task_summary: str,
    planner_risks: Iterable[str],
    backend_used: str = "",
    failure_kind: str = "",
    plugin_failed: bool = False,
    cli_failed: bool = False,
) -> dict[str, Any]:
    payload = extract_first_json(result.stdout)
    if not isinstance(payload, dict):
        payload = {}

    changed_files = normalize_text_list(
        payload.get("changed_files")
        or payload.get("files")
        or payload.get("modified_files")
    )
    tests_run = normalize_text_list(payload.get("tests_run") or payload.get("tests"))
    risks = {normalize_flag(item) for item in normalize_text_list(payload.get("risks"))}
    risks.update(normalize_flag(item) for item in planner_risks)

    if changed_files and not tests_run:
        risks.add("tests-missing")

    analyst_summary = first_non_empty(
        payload.get("analyst_summary"),
        payload.get("summary"),
        summarize_text(result.stdout or result.stderr, limit=320),
    )

    handoff = {
        "status": first_non_empty(payload.get("status"), "ok" if result.ok else "error").lower(),
        "task_summary": first_non_empty(payload.get("task_summary"), task_summary),
        "changed_files": changed_files,
        "tests_run": tests_run,
        "risks": sorted(risks),
        "analyst_summary": analyst_summary,
        "next_action": first_non_empty(
            payload.get("next_action"),
            "validar no Claude" if result.ok else "corrigir falha do executor",
        ),
    }
    handoff.update(
        normalize_executor_failure(
            backend_used=backend_used,
            failure_kind=failure_kind,
            plugin_failed=plugin_failed,
            cli_failed=cli_failed,
        )
    )
    return {key: handoff[key] for key in HANDOFF_KEYS}


def should_validate(
    handoff: dict[str, Any],
    planner: dict[str, Any],
    validation_cfg: dict[str, Any],
    *,
    force_validation: bool = False,
    skip_validation: bool = False,
) -> tuple[bool, list[str]]:
    if skip_validation:
        return False, []

    reasons: list[str] = []
    risks = {normalize_flag(item) for item in normalize_text_list(handoff.get("risks"))}
    always_validate_flags = {normalize_flag(item) for item in normalize_text_list(validation_cfg.get("always_validate_flags"))}
    changed_files = normalize_text_list(handoff.get("changed_files"))
    tests_run = normalize_text_list(handoff.get("tests_run"))
    threshold = int(validation_cfg.get("max_changed_files_without_validation", 3))

    if force_validation or planner.get("force_validation"):
        reasons.append("forced")
    if len(changed_files) > threshold:
        reasons.append("multi-file")
    if always_validate_flags.intersection(risks):
        reasons.append("high-risk")
    if changed_files and not tests_run and validation_cfg.get("require_tests_when_files_change", True):
        reasons.append("tests-missing")
    if handoff.get("status") not in {"ok", "success"}:
        reasons.append("executor-error")

    return bool(reasons), reasons


def call_provider(
    provider: str,
    prompt: str,
    config: dict[str, Any],
    *,
    model: str | None = None,
    timeout_s: int,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> CallResult:
    executable = get_command_path(config, provider)
    cmd = build_provider_command(
        provider,
        model,
        prompt,
        None,
        False,
        executable=executable,
    )
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    if provider == "codex":
        merged_env.pop("OPENAI_BASE_URL", None)
        merged_env.pop("OPENAI_API_KEY", None)
    return run_command(cmd, timeout_s=timeout_s, env=merged_env, cwd=cwd)


def call_claude_with_failover(
    prompt: str,
    config: dict[str, Any],
    *,
    model: str | None = None,
    timeout_s: int,
    preferred_profile: str | None = None,
    allow_failover: bool = True,
    simulate_quota_profiles: set[str] | None = None,
) -> dict[str, Any]:
    state = load_state(config["state_file"], profiles=config["profiles"])
    attempts = []
    ordered_profiles = profile_order(config["profiles"], state, preferred_profile=preferred_profile)
    quota_patterns = normalize_text_list(config["quota_patterns"])
    simulate_quota_profiles = simulate_quota_profiles or set()

    if not ordered_profiles:
        save_state(config["state_file"], state)
        return {
            "profile": None,
            "result": CallResult(
                ok=False,
                returncode=1,
                stdout="",
                stderr="no available claude profiles",
                command=["claude"],
            ),
            "quota_hit": False,
            "failure_kind": "no_available_profiles",
            "attempts": attempts,
        }

    for index, profile in enumerate(ordered_profiles):
        profile_name = profile["name"]
        profile_dir = profile["config_dir"]
        runtime_state = ensure_profile_runtime_entry(state, profile_name, profile_dir)
        set_profile_lease(runtime_state, f"claude:{profile_name}", lease_seconds=max(timeout_s, 300))
        save_state(config["state_file"], state)

        if profile_name in simulate_quota_profiles:
            result = CallResult(
                ok=False,
                returncode=1,
                stdout="",
                stderr=f"usage limit reached for profile {profile_name}",
                command=["simulate", profile_name],
            )
        else:
            result = call_provider(
                "claude",
                prompt,
                config,
                model=model,
                timeout_s=timeout_s,
                env={"CLAUDE_CONFIG_DIR": profile_dir},
            )

        failure_kind = "" if result.ok else get_claude_failure_kind(
            result.stdout,
            result.stderr,
            result.returncode,
            quota_patterns=quota_patterns,
        )
        quota_hit = failure_kind == "quota_exhausted"
        attempts.append(
            {
                "profile": profile_name,
                "config_dir": profile_dir,
                "returncode": result.returncode,
                "ok": result.ok,
                "quota_hit": quota_hit,
                "failure_kind": failure_kind,
                "stderr_excerpt": summarize_text(result.stderr, limit=200),
            }
        )

        if result.ok:
            state["active_profile"] = profile_name
            mark_profile_success(runtime_state)
            save_state(config["state_file"], state)
            return {
                "profile": profile_name,
                "result": result,
                "quota_hit": False,
                "failure_kind": "",
                "attempts": attempts,
            }

        apply_profile_failure(runtime_state, failure_kind)
        save_state(config["state_file"], state)

        should_switch = failure_kind in {"quota_exhausted", "rate_limited_transient", "backend_unavailable"}
        if not should_switch or not allow_failover or index == len(ordered_profiles) - 1:
            return {
                "profile": profile_name,
                "result": result,
                "quota_hit": quota_hit,
                "failure_kind": failure_kind,
                "attempts": attempts,
            }

    last_attempt = attempts[-1]
    return {
        "profile": last_attempt["profile"],
        "result": CallResult(
            ok=False,
            returncode=last_attempt["returncode"],
            stdout="",
            stderr=last_attempt["stderr_excerpt"],
            command=["claude"],
        ),
        "quota_hit": bool(last_attempt.get("quota_hit")),
        "failure_kind": str(last_attempt.get("failure_kind") or ""),
        "attempts": attempts,
    }


def route_task(
    task: str,
    config: dict[str, Any],
    *,
    working_dir: str | None,
    preferred_profile: str | None,
    force_validation: bool,
    skip_validation: bool,
    timeout_claude_s: int,
    timeout_codex_s: int,
    simulate_quota_profiles: set[str] | None,
    planner_model: str | None = None,
    executor_provider: str = "codex",
    executor_model: str | None = None,
    validation_model: str | None = None,
) -> dict[str, Any]:
    planner_prompt = build_planner_prompt(task)
    planner_call = call_claude_with_failover(
        planner_prompt,
        config,
        model=planner_model,
        timeout_s=timeout_claude_s,
        preferred_profile=preferred_profile,
        allow_failover=True,
        simulate_quota_profiles=simulate_quota_profiles,
    )
    planner_result = planner_call["result"]
    planner = normalize_planner_decision(
        task,
        planner_result.stdout or planner_result.stderr,
        force_validation=force_validation,
        skip_validation=skip_validation,
    )

    if planner["mode"] == "claude_only" or not planner["execution_required"]:
        task_context = {
            "task_summary": planner["task_summary"],
            "current_goal": "Concluir a tarefa sem executor adicional",
            "constraints": ["Nao replayar transcript inteiro"],
            "relevant_files": [],
            "last_plan_summary": planner["task_summary"],
            "executor_or_validator_checkpoint": "",
            "pending_decision": planner["next_action"],
            "token_budget_hint": 4000,
        }
        return {
            "status": "ok" if planner_result.ok else "error",
            "flow": {"planner": "claude", "executor": "skipped", "validation": "skipped"},
            "active_claude_profile": planner_call["profile"],
            "planner": planner,
            "planner_attempts": planner_call["attempts"],
            "rehydration": build_rehydration_payload(task_context),
            "handoff": None,
            "validation": None,
        }

    executor_provider = executor_provider.strip().lower() or "codex"
    if executor_provider not in {"codex", "claude"}:
        raise ValueError("executor_provider precisa ser 'codex' ou 'claude'.")

    executor_profile = None
    executor_backend_used = executor_provider
    executor_failure_kind = ""
    plugin_failed = False
    cli_failed = False
    if executor_provider == "claude":
        executor_call = call_claude_with_failover(
            planner["execution_prompt"],
            config,
            model=executor_model,
            timeout_s=timeout_claude_s,
            preferred_profile=preferred_profile,
            allow_failover=True,
            simulate_quota_profiles=simulate_quota_profiles,
        )
        executor_result = executor_call["result"]
        executor_profile = executor_call["profile"]
        executor_failure_kind = first_non_empty(executor_call.get("failure_kind"))
    else:
        executor_result = call_provider(
            "codex",
            planner["execution_prompt"],
            config,
            model=executor_model,
            timeout_s=timeout_codex_s,
            cwd=working_dir,
        )
        executor_backend_used = "cli"
        cli_failed = not executor_result.ok
        executor_failure_kind = "" if executor_result.ok else get_claude_failure_kind(
            executor_result.stdout,
            executor_result.stderr,
            executor_result.returncode,
            quota_patterns=config.get("quota_patterns"),
        )

    handoff = normalize_handoff(
        executor_result,
        task_summary=planner["task_summary"],
        planner_risks=planner["risks"],
        backend_used=executor_backend_used,
        failure_kind=executor_failure_kind,
        plugin_failed=plugin_failed,
        cli_failed=cli_failed,
    )
    validation_cfg = config.get("validation", {})
    use_validation, validation_reasons = should_validate(
        handoff,
        planner,
        validation_cfg,
        force_validation=force_validation,
        skip_validation=skip_validation,
    )

    validation_result = None
    validation_profile = None
    validation_attempts: list[dict[str, Any]] = []
    if use_validation:
        validation_prompt = planner["validation_prompt"] or build_validation_prompt(task, planner, handoff)
        validation_call = call_claude_with_failover(
            validation_prompt,
            config,
            model=validation_model,
            timeout_s=timeout_claude_s,
            preferred_profile=preferred_profile,
            allow_failover=True,
            simulate_quota_profiles=simulate_quota_profiles,
        )
        validation_profile = validation_call["profile"]
        validation_attempts = validation_call["attempts"]
        validation_raw = validation_call["result"].stdout or validation_call["result"].stderr
        payload = extract_first_json(validation_raw)
        if not isinstance(payload, dict):
            payload = {}
        validation_result = {
            "verdict": first_non_empty(payload.get("verdict"), "needs_changes" if not executor_result.ok else "approve").lower(),
            "summary": first_non_empty(payload.get("summary"), summarize_text(validation_raw, limit=240)),
            "concerns": normalize_text_list(payload.get("concerns")),
            "next_action": first_non_empty(payload.get("next_action"), handoff["next_action"]),
            "reasons": validation_reasons,
        }

    final_status = "ok" if executor_result.ok else "error"
    if validation_result and validation_result["verdict"] in {"needs_changes", "blocked"}:
        final_status = "needs_changes"

    task_context = {
        "task_summary": planner["task_summary"],
        "current_goal": first_non_empty(planner.get("next_action"), "Executar a proxima etapa do fluxo"),
        "constraints": ["Nao replayar transcript inteiro"],
        "relevant_files": [
            {
                "path": path,
                "reason": "Arquivo alterado pelo executor",
                "content_mode": "diff_only",
            }
            for path in normalize_text_list(handoff.get("changed_files"))
        ],
        "last_plan_summary": planner["task_summary"],
        "executor_or_validator_checkpoint": first_non_empty(
            validation_result.get("summary") if validation_result else "",
            handoff.get("analyst_summary"),
        ),
        "pending_decision": first_non_empty(
            validation_result.get("next_action") if validation_result else "",
            handoff.get("next_action"),
        ),
        "token_budget_hint": 4000,
    }

    return {
        "status": final_status,
        "flow": {
            "planner": "claude",
            "executor": executor_provider,
            "validation": "claude" if use_validation else "skipped",
        },
        "active_claude_profile": planner_call["profile"],
        "planner": planner,
        "planner_attempts": planner_call["attempts"],
        "rehydration": build_rehydration_payload(task_context),
        "handoff": handoff,
        "executor_profile": executor_profile,
        "validation": validation_result,
        "validation_profile": validation_profile,
        "validation_attempts": validation_attempts,
    }


def require_text_input(value: str | None, file_path: str | None, field_name: str) -> str:
    if value:
        return value
    if file_path:
        return read_text(expand_path(file_path))
    raise ValueError(f"Forneca --{field_name} ou --{field_name}-file")


def cmd_print_template_config(args: argparse.Namespace) -> int:
    config = build_default_config()
    output = json.dumps(config, ensure_ascii=False, indent=2)
    if args.output:
        write_text(expand_path(args.output), output + "\n")
    else:
        print(output)
    return 0


def cmd_bootstrap_profiles(args: argparse.Namespace) -> int:
    config, config_path = load_config(args.config)
    if args.write_config and not Path(config_path).exists():
        write_json(config_path, config)
    result = bootstrap_profiles(config, prefer_junction=not args.copy_only)
    result["config_file"] = config_path
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def cmd_call_claude(args: argparse.Namespace) -> int:
    config, _config_path = load_config(args.config)
    prompt = require_text_input(args.prompt, args.prompt_file, "prompt")
    result = call_claude_with_failover(
        prompt,
        config,
        model=args.model,
        timeout_s=args.timeout_s,
        preferred_profile=args.profile,
        allow_failover=not args.disable_failover,
        simulate_quota_profiles=set(args.simulate_quota_profile or []),
    )
    envelope = {
        "status": "ok" if result["result"].ok else "error",
        "profile": result["profile"],
        "quota_hit": result["quota_hit"],
        "attempts": result["attempts"],
        "returncode": result["result"].returncode,
        "stdout": result["result"].stdout,
        "stderr": result["result"].stderr,
    }
    print(json.dumps(envelope, ensure_ascii=False, indent=2))
    return 0 if result["result"].ok else 1


def cmd_call_codex(args: argparse.Namespace) -> int:
    config, _config_path = load_config(args.config)
    prompt = require_text_input(args.prompt, args.prompt_file, "prompt")
    result = call_provider(
        "codex",
        prompt,
        config,
        timeout_s=args.timeout_s,
        cwd=expand_path(args.working_dir) if args.working_dir else None,
    )
    failure_kind = "" if result.ok else get_claude_failure_kind(
        result.stdout,
        result.stderr,
        result.returncode,
        quota_patterns=config.get("quota_patterns"),
    )
    handoff = normalize_handoff(
        result,
        task_summary=first_non_empty(args.task_summary, summarize_text(prompt, limit=180)),
        planner_risks=normalize_text_list(args.risk),
        backend_used="cli",
        failure_kind=failure_kind,
        plugin_failed=False,
        cli_failed=not result.ok,
    )
    print(json.dumps(handoff, ensure_ascii=False, indent=2))
    return 0 if result.ok else 1


def cmd_route(args: argparse.Namespace) -> int:
    config, _config_path = load_config(args.config)
    task = require_text_input(args.task, args.task_file, "task")
    result = route_task(
        task,
        config,
        working_dir=expand_path(args.working_dir) if args.working_dir else None,
        preferred_profile=args.profile,
        force_validation=args.force_validation,
        skip_validation=args.skip_validation,
        timeout_claude_s=args.timeout_claude_s,
        timeout_codex_s=args.timeout_codex_s,
        simulate_quota_profiles=set(args.simulate_quota_profile or []),
        planner_model=args.planner_model,
        executor_provider=args.executor_provider,
        executor_model=args.executor_model,
        validation_model=args.validation_model,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Orquestrador Windows para o fluxo Claude planeja -> Codex executa -> Claude valida."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    print_template = subparsers.add_parser("print-template-config", help="Mostra a configuracao exemplo.")
    print_template.add_argument("--output", default=None, help="Arquivo opcional para gravar o JSON.")
    print_template.set_defaults(func=cmd_print_template_config)

    bootstrap = subparsers.add_parser("bootstrap-profiles", help="Prepara os perfis Claude isolados.")
    bootstrap.add_argument("--config", default=None, help="Caminho do config.json do orquestrador.")
    bootstrap.add_argument("--write-config", action="store_true", help="Grava o config padrao se ele ainda nao existir.")
    bootstrap.add_argument("--copy-only", action="store_true", help="Forca copia em vez de junction para assets compartilhados.")
    bootstrap.set_defaults(func=cmd_bootstrap_profiles)

    call_claude = subparsers.add_parser("call-claude", help="Chama o Claude com failover opcional de perfil.")
    call_claude.add_argument("--config", default=None)
    call_claude.add_argument("--prompt", default=None)
    call_claude.add_argument("--prompt-file", default=None)
    call_claude.add_argument("--profile", default=None)
    call_claude.add_argument("--model", default=None)
    call_claude.add_argument("--timeout-s", type=int, default=900)
    call_claude.add_argument("--disable-failover", action="store_true")
    call_claude.add_argument("--simulate-quota-profile", action="append", default=[])
    call_claude.set_defaults(func=cmd_call_claude)

    call_codex = subparsers.add_parser("call-codex", help="Chama o Codex e normaliza o handoff.")
    call_codex.add_argument("--config", default=None)
    call_codex.add_argument("--prompt", default=None)
    call_codex.add_argument("--prompt-file", default=None)
    call_codex.add_argument("--task-summary", default=None)
    call_codex.add_argument("--risk", action="append", default=[])
    call_codex.add_argument("--working-dir", default=None)
    call_codex.add_argument("--timeout-s", type=int, default=1800)
    call_codex.set_defaults(func=cmd_call_codex)

    route = subparsers.add_parser("route", help="Executa o fluxo completo Claude -> Codex -> Claude.")
    route.add_argument("--config", default=None)
    route.add_argument("--task", default=None)
    route.add_argument("--task-file", default=None)
    route.add_argument("--working-dir", default=None)
    route.add_argument("--profile", default=None)
    route.add_argument("--planner-model", default=None, help="Modelo Claude para a etapa de planejamento.")
    route.add_argument("--executor-provider", default="codex", choices=["codex", "claude"])
    route.add_argument("--executor-model", default=None, help="Modelo do executor quando aplicavel.")
    route.add_argument("--validation-model", default=None, help="Modelo Claude para a validacao final.")
    route.add_argument("--timeout-claude-s", type=int, default=900)
    route.add_argument("--timeout-codex-s", type=int, default=1800)
    route.add_argument("--force-validation", action="store_true")
    route.add_argument("--skip-validation", action="store_true")
    route.add_argument("--simulate-quota-profile", action="append", default=[])
    route.set_defaults(func=cmd_route)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return int(args.func(args))
    except Exception as exc:
        print(json.dumps({"status": "error", "message": str(exc)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
