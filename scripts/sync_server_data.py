# -*- coding: utf-8 -*-
"""Pull configured server data into the active personal data root.

Server addresses, identity-file paths, and remote directories live only in the
ignored config.json. This script never contains or persists credentials.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from data_paths import PROJECT_ROOT, load_project_config, portable_path, resolve_data_context


def now_text() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def tail_text(value: str, limit: int = 2000) -> str:
    value = value.strip()
    return value if len(value) <= limit else value[-limit:]


def local_target(data_root: Path, relative: str) -> Path:
    requested = Path(relative)
    if requested.is_absolute():
        raise ValueError(f"同步目标必须是相对于数据目录的路径：{relative}")
    resolved = (data_root / requested).resolve()
    try:
        resolved.relative_to(data_root.resolve())
    except ValueError as exc:
        raise ValueError(f"同步目标超出数据目录：{relative}") from exc
    return resolved


def identity_path(value: str) -> Path | None:
    if not value.strip():
        return None
    expanded = os.path.expandvars(value.strip())
    path = Path(expanded).expanduser()
    return path.resolve() if path.is_absolute() else (PROJECT_ROOT / path).resolve()


def enabled_targets(config: dict[str, Any]) -> list[dict[str, str]]:
    raw_targets = config.get("targets")
    if not isinstance(raw_targets, list):
        return []
    targets: list[dict[str, str]] = []
    for index, item in enumerate(raw_targets, start=1):
        if not isinstance(item, dict) or item.get("enabled") is False:
            continue
        name = str(item.get("name") or f"target-{index}").strip()
        remote = str(item.get("remote") or "").strip()
        local = str(item.get("local") or "").strip()
        if not remote or not local:
            raise ValueError(f"服务器同步目标 {name} 缺少 remote 或 local")
        if "\n" in remote or "\r" in remote:
            raise ValueError(f"服务器同步目标 {name} 的 remote 无效")
        targets.append({"name": name, "remote": remote, "local": local})
    return targets


def build_ssh_command(host: str, key: Path | None, remote_command: str, connect_timeout: int) -> list[str]:
    command = [
        "ssh",
        "-o",
        "BatchMode=yes",
        "-o",
        f"ConnectTimeout={connect_timeout}",
    ]
    if key is not None:
        command.extend(["-i", str(key), "-o", "IdentitiesOnly=yes"])
    command.extend([host, remote_command])
    return command


def remote_archive_command(remote: str, lookback_days: int) -> str:
    cutoff = int(time.time()) - lookback_days * 86400
    inner = (
        "set -o pipefail; "
        f"cd {shlex.quote(remote)}; "
        f"find . -type f -newermt '@{cutoff}' -print0 | tar --null -T - -czf -"
    )
    return f"bash -lc {shlex.quote(inner)}"


def decode_bytes(value: bytes | None) -> str:
    if not value:
        return ""
    for encoding in ("utf-8", "gbk"):
        try:
            return value.decode(encoding)
        except UnicodeDecodeError:
            continue
    return value.decode("utf-8", errors="replace")


def extract_archive(archive_path: Path, destination: Path) -> int:
    extracted = 0
    root = destination.resolve()
    with tarfile.open(archive_path, mode="r:gz") as archive:
        for member in archive:
            if member.issym() or member.islnk():
                raise RuntimeError(f"服务器归档包含不允许的链接：{member.name}")
            if not member.isfile() and not member.isdir():
                raise RuntimeError(f"服务器归档包含不允许的文件类型：{member.name}")
            target = (root / member.name).resolve()
            try:
                target.relative_to(root)
            except ValueError as exc:
                raise RuntimeError(f"服务器归档路径超出同步目录：{member.name}") from exc
            if sys.version_info >= (3, 12):
                archive.extract(member, path=root, filter="data")
            else:
                archive.extract(member, path=root)
            if member.isfile():
                extracted += 1
    return extracted


def sync_target(
    host: str,
    key: Path | None,
    remote: str,
    destination: Path,
    connect_timeout: int,
    transfer_timeout: int,
    lookback_days: int,
    dry_run: bool,
) -> dict[str, Any]:
    remote_command = remote_archive_command(remote, lookback_days)
    command = build_ssh_command(host, key, remote_command, connect_timeout)
    if dry_run:
        return {"returncode": 0, "stderr_tail": "", "files_updated": 0, "lookback_days": lookback_days}

    with tempfile.TemporaryDirectory(prefix="self-media-sync-") as temporary:
        archive_path = Path(temporary) / "changed-files.tar.gz"
        try:
            with archive_path.open("wb") as output:
                completed = subprocess.run(
                    command,
                    cwd=str(PROJECT_ROOT),
                    stdout=output,
                    stderr=subprocess.PIPE,
                    timeout=transfer_timeout,
                    check=False,
                )
        except subprocess.TimeoutExpired as exc:
            return {
                "returncode": 124,
                "stderr_tail": f"增量传输超过 {transfer_timeout} 秒：{tail_text(decode_bytes(exc.stderr))}",
                "files_updated": 0,
                "lookback_days": lookback_days,
            }
        stderr = tail_text(decode_bytes(completed.stderr))
        if completed.returncode != 0:
            return {
                "returncode": completed.returncode,
                "stderr_tail": stderr,
                "files_updated": 0,
                "lookback_days": lookback_days,
            }
        try:
            files_updated = extract_archive(archive_path, destination)
        except (OSError, tarfile.TarError, RuntimeError) as exc:
            return {
                "returncode": 1,
                "stderr_tail": f"服务器归档解包失败：{exc}",
                "files_updated": 0,
                "lookback_days": lookback_days,
            }
    return {
        "returncode": 0,
        "stderr_tail": stderr,
        "files_updated": files_updated,
        "lookback_days": lookback_days,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    context = resolve_data_context()
    report_path = context.dashboard_dir / "server_sync_refresh_report.json"
    report: dict[str, Any] = {
        "schema": "self-media-sync-report.v1",
        "status": "running",
        "data_mode": context.mode,
        "generated_at": now_text(),
        "data_root": portable_path(context.root),
        "results": [],
    }

    try:
        if context.is_demo:
            raise RuntimeError("模拟数据模式不连接服务器")

        project_config = load_project_config()
        sync_config = project_config.get("server_sync")
        if not isinstance(sync_config, dict) or sync_config.get("enabled") is not True:
            raise RuntimeError("尚未在 config.json 中启用 server_sync")

        host = str(sync_config.get("host") or "").strip()
        if not host or "\n" in host or "\r" in host:
            raise RuntimeError("server_sync.host 未配置或格式无效")
        key = identity_path(str(sync_config.get("identity_file") or ""))
        if key is not None and not key.is_file():
            raise RuntimeError(f"SSH 密钥文件不存在：{key}")
        targets = enabled_targets(sync_config)
        if not targets:
            raise RuntimeError("server_sync.targets 没有可用的同步目录")
        if not args.dry_run and shutil.which("ssh") is None:
            raise RuntimeError("当前电脑未找到 ssh，请先启用 Windows OpenSSH Client")

        connect_timeout = max(5, min(int(sync_config.get("connect_timeout") or 20), 120))
        transfer_timeout = max(30, min(int(sync_config.get("transfer_timeout") or 600), 3600))
        lookback_days = max(1, min(int(sync_config.get("lookback_days") or 3), 90))
        initial_lookback_days = max(lookback_days, min(int(sync_config.get("initial_lookback_days") or 90), 3650))

        for target in targets:
            destination = local_target(context.root, target["local"])
            destination.mkdir(parents=True, exist_ok=True)
            has_local_files = any(item.is_file() for item in destination.rglob("*"))
            selected_lookback = lookback_days if has_local_files else initial_lookback_days
            result = sync_target(
                host,
                key,
                target["remote"],
                destination,
                connect_timeout,
                transfer_timeout,
                selected_lookback,
                args.dry_run,
            )
            item = {
                "name": target["name"],
                "remote": target["remote"],
                "local": portable_path(destination),
                "status": "dry_run" if args.dry_run else ("success" if result["returncode"] == 0 else "failed"),
                **result,
            }
            report["results"].append(item)
            if result["returncode"] != 0:
                detail = result["stderr_tail"] or "未知错误"
                raise RuntimeError(f"{target['name']} 拉取失败：{detail}")

        report["status"] = "dry_run" if args.dry_run else "success"
        return_code = 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        report["status"] = "failed"
        report["error"] = str(exc)
        return_code = 1

    report["finished_at"] = now_text()
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False))
    return return_code


if __name__ == "__main__":
    raise SystemExit(main())
