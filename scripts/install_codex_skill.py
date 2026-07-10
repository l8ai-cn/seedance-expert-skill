#!/usr/bin/env python3
"""Install the reviewed Seedance runtime package transactionally."""
from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path


sys.dont_write_bytecode = True


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.runtime_package import (  # noqa: E402
    GENERATED_MANIFEST_NAME,
    PACKAGE_NAME,
    PackageError,
    format_size,
    is_special_path,
    materialize_package,
    package_plan,
    render_generated_manifest,
    verify_package,
)


SKILL_NAME = PACKAGE_NAME
LOCK_NAME = f".{SKILL_NAME}.install.lock"
BACKUP_NAME = f".{SKILL_NAME}.rollback"
LEGACY_BACKUP_NAME = f".{SKILL_NAME}.legacy-rollback"
JOURNAL_NAME = f".{SKILL_NAME}.transaction.json"
STAGE_PREFIX = f".{SKILL_NAME}.stage-"
OLD_PREFIX = f".{SKILL_NAME}.old-"
FAILED_PREFIX = f".{SKILL_NAME}.failed-"
SWAP_PREFIX = f".{SKILL_NAME}.swap-"
LEGACY_NAME = re.compile(r"(?m)^name:\s*[\"']?seedance-20[\"']?\s*$")


class InstallError(RuntimeError):
    """Raised when installation safety or transaction checks fail."""


def default_skills_dir() -> Path:
    codex_home = os.environ.get("CODEX_HOME")
    if codex_home:
        return Path(codex_home).expanduser() / "skills"
    return Path.home() / ".codex" / "skills"


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def _resolved(path: Path) -> Path:
    return path.expanduser().absolute().resolve(strict=False)


def assert_safe_layout(repo_root: Path, skills_dir: Path) -> tuple[Path, Path]:
    source = repo_root.resolve()
    skills = _resolved(skills_dir)
    destination = skills / SKILL_NAME
    destination_resolved = destination.resolve(strict=False)
    if destination.name != SKILL_NAME:
        raise InstallError(f"destination must end with {SKILL_NAME}: {destination}")
    if (
        source == destination_resolved
        or source in destination_resolved.parents
        or destination_resolved in source.parents
    ):
        raise InstallError(
            f"source and destination trees must be disjoint: source={source}, destination={destination_resolved}"
        )
    if _lexists(destination):
        if is_special_path(destination):
            raise InstallError(f"destination cannot be a symlink, junction, or mount: {destination}")
        if not destination.is_dir():
            raise InstallError(f"destination exists but is not a directory: {destination}")
    return skills, destination


def _scan_plain_tree(root: Path) -> set[str]:
    if not root.is_dir() or is_special_path(root):
        raise InstallError(f"installation tree is missing or special: {root}")
    files_found: set[str] = set()
    for current, directories, files in os.walk(root, followlinks=False):
        current_path = Path(current)
        for name in directories:
            path = current_path / name
            if is_special_path(path):
                raise InstallError(f"installation contains a symlink, junction, or mount: {path}")
        for name in files:
            path = current_path / name
            if is_special_path(path) or not path.is_file():
                raise InstallError(f"installation contains a special file: {path}")
            files_found.add(path.relative_to(root).as_posix())
    return files_found


def _validate_skill_identity(path: Path) -> None:
    skill = path / "SKILL.md"
    if not skill.is_file() or skill.is_symlink():
        raise InstallError(f"existing directory is not a Seedance installation: {path}")
    try:
        head = "\n".join(skill.read_text(encoding="utf-8").splitlines()[:24])
    except (OSError, UnicodeError) as exc:
        raise InstallError(f"cannot read existing SKILL.md: {exc}") from exc
    if not LEGACY_NAME.search(head):
        raise InstallError(f"existing SKILL.md does not declare name: {SKILL_NAME}")


def validate_existing_install(path: Path, *, allow_drift: bool = False) -> str:
    _scan_plain_tree(path)
    generated = path / GENERATED_MANIFEST_NAME
    if generated.is_file():
        try:
            verify_package(path)
            return "verified"
        except PackageError:
            if not allow_drift:
                raise
            _validate_skill_identity(path)
            return "dirty"
    _validate_skill_identity(path)
    return "legacy"


def _installation_fingerprint(path: Path) -> str:
    files = sorted(_scan_plain_tree(path))
    digest = hashlib.sha256()
    for relative in files:
        content = path.joinpath(*relative.split("/")).read_bytes()
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(content).digest())
        digest.update(b"\0")
        digest.update(str(len(content)).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _assert_owned_child(path: Path, skills_dir: Path, names: set[str] | None = None, prefix: str | None = None) -> None:
    if path.parent.resolve() != skills_dir.resolve():
        raise InstallError(f"transaction path is outside the skills directory: {path}")
    if names is not None and path.name not in names:
        raise InstallError(f"transaction path is not installer-owned: {path}")
    if prefix is not None and not path.name.startswith(prefix):
        raise InstallError(f"transaction path has an unexpected name: {path}")


def safe_remove_tree(path: Path, skills_dir: Path, *, names: set[str] | None = None, prefix: str | None = None) -> None:
    _assert_owned_child(path, skills_dir, names, prefix)
    if not _lexists(path):
        return
    _scan_plain_tree(path)
    shutil.rmtree(path)


def _acquire_os_lock(handle: object) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)  # type: ignore[attr-defined]
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)  # type: ignore[attr-defined]
        except OSError as exc:
            raise InstallError("another installer is active") from exc
        return

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
    except OSError as exc:
        raise InstallError("another installer is active") from exc


def _release_os_lock(handle: object) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)  # type: ignore[attr-defined]
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)  # type: ignore[attr-defined]
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]


class InstallLock:
    def __init__(self, skills_dir: Path, recover: bool) -> None:
        self.skills_dir = skills_dir
        self.path = skills_dir / LOCK_NAME
        self.recover = recover
        self.handle: object | None = None
        self.acquired = False

    def __enter__(self) -> "InstallLock":
        if _lexists(self.path) and (is_special_path(self.path) or not self.path.is_file()):
            raise InstallError(f"installer lock is a special or invalid path: {self.path}")
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path, flags, 0o600)
            metadata = os.fstat(descriptor)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                os.close(descriptor)
                raise InstallError(f"installer lock is not a private regular file: {self.path}")
            if hasattr(os, "fchmod"):
                os.fchmod(descriptor, 0o600)
            self.handle = os.fdopen(descriptor, "r+b", buffering=0)
            _acquire_os_lock(self.handle)
            self.acquired = True
            payload = (json.dumps({"pid": os.getpid()}, sort_keys=True) + "\n").encode("utf-8")
            self.handle.seek(0)  # type: ignore[attr-defined]
            self.handle.truncate(0)  # type: ignore[attr-defined]
            self.handle.write(payload)  # type: ignore[attr-defined]
            self.handle.flush()  # type: ignore[attr-defined]
            os.fsync(self.handle.fileno())  # type: ignore[attr-defined]
            return self
        except Exception:
            if self.handle is not None:
                self.handle.close()  # type: ignore[attr-defined]
                self.handle = None
            raise

    def __exit__(self, _type: object, _value: object, _traceback: object) -> None:
        if not self.acquired or self.handle is None:
            return
        try:
            _release_os_lock(self.handle)
        finally:
            self.handle.close()  # type: ignore[attr-defined]
            self.handle = None
            self.acquired = False


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        unsupported = {errno.EINVAL, getattr(errno, "ENOTSUP", -1), getattr(errno, "EOPNOTSUPP", -1)}
        if exc.errno in unsupported or (os.name == "nt" and exc.errno in {errno.EACCES, errno.EPERM}):
            return
        raise
    try:
        os.fsync(descriptor)
    except OSError as exc:
        unsupported = {errno.EINVAL, getattr(errno, "ENOTSUP", -1), getattr(errno, "EOPNOTSUPP", -1)}
        if exc.errno not in unsupported:
            raise
    finally:
        os.close(descriptor)


def _journal_path(skills_dir: Path) -> Path:
    return skills_dir / JOURNAL_NAME


def write_journal(skills_dir: Path, data: dict[str, object]) -> None:
    path = _journal_path(skills_dir)
    temporary = skills_dir / f"{JOURNAL_NAME}.tmp"
    payload = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    if _lexists(path) and (is_special_path(path) or not path.is_file()):
        raise InstallError(f"transaction journal is special: {path}")
    if _lexists(temporary):
        raise InstallError(f"transaction journal temporary path already exists: {temporary}")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)
    _fsync_directory(skills_dir)


def clear_journal(skills_dir: Path) -> None:
    path = _journal_path(skills_dir)
    if _lexists(path):
        if is_special_path(path) or not path.is_file():
            raise InstallError(f"transaction journal is special: {path}")
        path.unlink()
        _fsync_directory(skills_dir)


def atomic_replace(source: Path, destination: Path) -> None:
    os.replace(source, destination)
    _fsync_directory(destination.parent)


def _transaction_name(value: object, prefix: str) -> str:
    if not isinstance(value, str) or not value.startswith(prefix) or "/" in value or "\\" in value:
        raise InstallError(f"invalid transaction-owned name: {value!r}")
    return value


def recover_transaction(skills_dir: Path, destination: Path, recover: bool) -> None:
    journal = _journal_path(skills_dir)
    journal_temporary = skills_dir / f"{JOURNAL_NAME}.tmp"
    stages = sorted(path for path in skills_dir.iterdir() if path.name.startswith(STAGE_PREFIX))
    olds = sorted(path for path in skills_dir.iterdir() if path.name.startswith(OLD_PREFIX))
    swaps = sorted(path for path in skills_dir.iterdir() if path.name.startswith(SWAP_PREFIX))
    if (_lexists(journal) or _lexists(journal_temporary) or stages or olds or swaps) and not recover:
        raise InstallError("an incomplete installer transaction exists; rerun with --recover")
    if not recover:
        return

    if _lexists(journal):
        if is_special_path(journal) or not journal.is_file():
            raise InstallError(f"transaction journal is special: {journal}")
        try:
            data = json.loads(journal.read_text(encoding="utf-8"))
        except Exception as exc:
            raise InstallError(f"cannot read transaction journal: {exc}") from exc
        if not isinstance(data, dict) or data.get("version") != 1:
            raise InstallError("transaction journal has an unsupported format or version")
        phase = data.get("phase")
        backup_name = data.get("backup_name", BACKUP_NAME)
        if backup_name not in {BACKUP_NAME, LEGACY_BACKUP_NAME}:
            raise InstallError(f"journal names an invalid backup: {backup_name!r}")
        backup = skills_dir / str(backup_name)
        stage_name = data.get("stage_name")
        stage = skills_dir / _transaction_name(stage_name, STAGE_PREFIX) if stage_name else None
        old_name = data.get("old_name")
        old = skills_dir / _transaction_name(old_name, OLD_PREFIX) if old_name else None
        backup_kind = data.get("backup_kind", "none")
        if backup_kind not in {"none", "verified", "legacy", "dirty"}:
            raise InstallError(f"journal records an invalid rollback kind: {backup_kind!r}")
        swap_name = data.get("swap_name")
        swap = skills_dir / _transaction_name(swap_name, SWAP_PREFIX) if swap_name else None
        expected_tree = data.get("expected_tree_sha256")
        expected_count = data.get("expected_payload_file_count")
        expected_size = data.get("expected_payload_size_bytes")

        for owned in (stage, old, swap):
            if owned is not None and _lexists(owned) and (is_special_path(owned) or not owned.is_dir()):
                raise InstallError(f"transaction-owned path is special or invalid: {owned}")
        for fixed in (destination, backup):
            if _lexists(fixed) and (is_special_path(fixed) or not fixed.is_dir()):
                raise InstallError(f"transaction path is special or invalid: {fixed}")

        destination_exists = _lexists(destination)
        backup_exists = _lexists(backup)
        stage_exists = bool(stage and _lexists(stage))
        old_exists = bool(old and _lexists(old))
        swap_exists = bool(swap and _lexists(swap))

        if phase in {"prepared", "old_moved", "new_moved"}:
            if old is None or stage is None:
                raise InstallError("install journal is missing its stage or previous-active path")
            if (
                not isinstance(expected_tree, str)
                or not re.fullmatch(r"[a-f0-9]{64}", expected_tree)
                or not isinstance(expected_count, int)
                or isinstance(expected_count, bool)
                or expected_count < 0
                or not isinstance(expected_size, int)
                or isinstance(expected_size, bool)
                or expected_size < 0
            ):
                raise InstallError("install journal is missing its reviewed package identity")
            if destination_exists:
                try:
                    installed = verify_package(destination)
                    new_is_valid = (
                        installed.get("tree_sha256") == expected_tree
                        and installed.get("payload_file_count") == expected_count
                        and installed.get("payload_size_bytes") == expected_size
                    )
                except PackageError:
                    new_is_valid = False
            else:
                new_is_valid = False

            if phase == "prepared" and destination_exists and not old_exists:
                if stage_exists and stage is not None:
                    safe_remove_tree(stage, skills_dir, prefix=STAGE_PREFIX)
            elif not destination_exists and old_exists and old is not None:
                validate_existing_install(old, allow_drift=True)
                atomic_replace(old, destination)
                if stage_exists and stage is not None:
                    safe_remove_tree(stage, skills_dir, prefix=STAGE_PREFIX)
            elif destination_exists and old_exists and old is not None:
                if new_is_valid and not stage_exists:
                    if old != backup:
                        _rotate_committed_backup(skills_dir, backup, old, str(backup_kind))
                elif phase == "prepared" and stage_exists:
                    raise InstallError("ambiguous prepared install state; active, old, and stage all exist")
                else:
                    failed = Path(tempfile.mkdtemp(prefix=FAILED_PREFIX, dir=skills_dir))
                    failed.rmdir()
                    atomic_replace(destination, failed)
                    atomic_replace(old, destination)
                    validate_existing_install(destination, allow_drift=True)
                    if stage_exists and stage is not None:
                        safe_remove_tree(stage, skills_dir, prefix=STAGE_PREFIX)
            elif not old_exists and backup_exists and not stage_exists:
                # Backup rotation completed before the last journal update.
                validate_existing_install(backup, allow_drift=True)
                if not new_is_valid:
                    if destination_exists:
                        failed = Path(tempfile.mkdtemp(prefix=FAILED_PREFIX, dir=skills_dir))
                        failed.rmdir()
                        atomic_replace(destination, failed)
                    atomic_replace(backup, destination)
                    validate_existing_install(destination, allow_drift=True)
            else:
                raise InstallError(
                    "cannot recover install transaction from filesystem state: "
                    f"phase={phase!r}, active={destination_exists}, backup={backup_exists}, "
                    f"stage={stage_exists}, old={old_exists}"
                )
        elif phase in {"rollback_prepared", "rollback_current_moved", "rollback_backup_moved"}:
            if swap is None:
                raise InstallError("rollback journal is missing its swap path")
            if destination_exists and backup_exists and not swap_exists:
                validate_existing_install(destination, allow_drift=True)
                validate_existing_install(backup, allow_drift=True)
            elif not destination_exists and backup_exists and swap_exists:
                validate_existing_install(swap, allow_drift=True)
                atomic_replace(swap, destination)
            elif destination_exists and not backup_exists and swap_exists:
                validate_existing_install(destination, allow_drift=True)
                validate_existing_install(swap, allow_drift=True)
                atomic_replace(swap, backup)
            else:
                raise InstallError(
                    "cannot recover rollback transaction from filesystem state: "
                    f"phase={phase!r}, active={destination_exists}, backup={backup_exists}, swap={swap_exists}"
                )
        else:
            raise InstallError(f"unknown transaction phase: {phase!r}")
        clear_journal(skills_dir)

    if _lexists(journal_temporary):
        if journal_temporary.is_symlink() or not journal_temporary.is_file():
            raise InstallError(f"transaction journal temporary path is special: {journal_temporary}")
        journal_temporary.unlink()

    remaining_stages = sorted(path for path in skills_dir.iterdir() if path.name.startswith(STAGE_PREFIX))
    remaining_olds = sorted(path for path in skills_dir.iterdir() if path.name.startswith(OLD_PREFIX))
    remaining_swaps = sorted(path for path in skills_dir.iterdir() if path.name.startswith(SWAP_PREFIX))
    for stage in remaining_stages:
        safe_remove_tree(stage, skills_dir, prefix=STAGE_PREFIX)
    if remaining_olds or remaining_swaps:
        raise InstallError(
            "orphaned transaction trees require manual inspection: "
            f"old={[path.name for path in remaining_olds]}, swap={[path.name for path in remaining_swaps]}"
        )


def _inspect_backup_slot(skills_dir: Path) -> tuple[Path, str]:
    backup = skills_dir / BACKUP_NAME
    if not _lexists(backup):
        return backup, "none"
    if is_special_path(backup) or not backup.is_dir():
        raise InstallError(f"rollback slot is a special or invalid path: {backup}")
    kind = validate_existing_install(backup, allow_drift=True)
    if kind in {"legacy", "dirty"}:
        legacy = skills_dir / LEGACY_BACKUP_NAME
        if _lexists(legacy):
            raise InstallError(f"both rollback slots are occupied; preserve or remove manually: {legacy}")
    return backup, kind


def _rotate_committed_backup(
    skills_dir: Path,
    backup: Path,
    old: Path,
    backup_kind: str,
) -> None:
    if not _lexists(old):
        if not _lexists(backup):
            raise InstallError("committed install has neither previous active tree nor rollback backup")
        return
    validate_existing_install(old, allow_drift=True)
    if _lexists(backup):
        if backup_kind in {"legacy", "dirty"}:
            legacy = skills_dir / LEGACY_BACKUP_NAME
            if _lexists(legacy):
                raise InstallError(f"legacy rollback slot unexpectedly exists: {legacy}")
            atomic_replace(backup, legacy)
        elif backup_kind == "verified":
            safe_remove_tree(backup, skills_dir, names={BACKUP_NAME})
        elif backup_kind != "none":
            raise InstallError(f"invalid recorded rollback kind: {backup_kind!r}")
    if _lexists(backup):
        raise InstallError(f"rollback slot was not cleared safely: {backup}")
    atomic_replace(old, backup)
    validate_existing_install(backup, allow_drift=True)


def _dry_run_changes(destination: Path, plan: dict[str, object]) -> tuple[int, int, int]:
    new_records = {str(record["path"]): record for record in plan["files"]}
    generated = render_generated_manifest(plan)
    new_records[GENERATED_MANIFEST_NAME] = {
        "path": GENERATED_MANIFEST_NAME,
        "size": len(generated),
        "sha256": hashlib.sha256(generated).hexdigest(),
    }
    if not destination.exists():
        return len(new_records), 0, 0
    validate_existing_install(destination, allow_drift=True)
    existing = _scan_plain_tree(destination)
    add = len(set(new_records) - existing)
    remove = len(existing - set(new_records))
    update = 0
    for relative, record in new_records.items():
        if relative not in existing:
            continue
        content = (destination / relative).read_bytes()
        if len(content) != record["size"] or hashlib.sha256(content).hexdigest() != record["sha256"]:
            update += 1
    return add, update, remove


def install(
    repo_root: Path,
    skills_dir: Path,
    *,
    force: bool = False,
    dry_run: bool = False,
    recover: bool = False,
) -> int:
    skills, destination = assert_safe_layout(repo_root, skills_dir)
    if dry_run and recover:
        raise InstallError("--dry-run cannot recover or modify an interrupted transaction")

    plan: dict[str, object] | None = None
    if not recover:
        try:
            plan = package_plan(repo_root.resolve())
        except PackageError as exc:
            raise InstallError(str(exc)) from exc

    if dry_run:
        if plan is None:
            raise InstallError("dry-run package plan is unavailable")
        add, update, remove = _dry_run_changes(destination, plan)
        action = "replace" if destination.exists() else "install"
        print(f"Dry run: {action} {SKILL_NAME} at {destination}")
        print(f"Payload: {plan['payload_file_count']} files, {format_size(int(plan['payload_size_bytes']))}")
        print(f"Plan: add {add}, update {update}, remove {remove}")
        print(f"Tree SHA-256: {plan['tree_sha256']}")
        return 0

    if destination.exists() and not force and not recover:
        print(f"{SKILL_NAME} is already installed at {destination}")
        print("Run again with --force to replace it safely.")
        return 1

    skills.mkdir(parents=True, exist_ok=True)
    with InstallLock(skills, recover):
        recover_transaction(skills, destination, recover)
        if destination.exists() and not force:
            if recover:
                validate_existing_install(destination, allow_drift=True)
                print(f"Recovery complete; {SKILL_NAME} is active at {destination}")
                return 0
            return 1
        if plan is None:
            try:
                plan = package_plan(repo_root.resolve())
            except PackageError as exc:
                raise InstallError(str(exc)) from exc
        stage = Path(tempfile.mkdtemp(prefix=STAGE_PREFIX, dir=skills))
        try:
            staged_plan = materialize_package(repo_root.resolve(), stage)
            if staged_plan != plan:
                raise InstallError("runtime source changed between planning and staging")
            try:
                stage.chmod(0o755)
            except OSError:
                pass

            if not destination.exists():
                atomic_replace(stage, destination)
                try:
                    if verify_package(destination) != plan:
                        raise InstallError("installed package does not match the reviewed source plan")
                except Exception:
                    failed = Path(tempfile.mkdtemp(prefix=FAILED_PREFIX, dir=skills))
                    failed.rmdir()
                    atomic_replace(destination, failed)
                    raise
            else:
                validate_existing_install(destination, allow_drift=True)
                backup, backup_kind = _inspect_backup_slot(skills)
                old = Path(tempfile.mkdtemp(prefix=OLD_PREFIX, dir=skills))
                old.rmdir()
                transaction = {
                    "version": 1,
                    "backup_name": backup.name,
                    "backup_kind": backup_kind,
                    "stage_name": stage.name,
                    "old_name": old.name,
                    "expected_tree_sha256": plan["tree_sha256"],
                    "expected_payload_file_count": plan["payload_file_count"],
                    "expected_payload_size_bytes": plan["payload_size_bytes"],
                }
                try:
                    write_journal(skills, {**transaction, "phase": "prepared"})
                    atomic_replace(destination, old)
                    write_journal(skills, {**transaction, "phase": "old_moved"})
                    atomic_replace(stage, destination)
                    write_journal(skills, {**transaction, "phase": "new_moved"})
                    installed_plan = verify_package(destination)
                    if installed_plan != plan:
                        raise InstallError("installed package does not match the reviewed source plan")
                    _rotate_committed_backup(skills, backup, old, backup_kind)
                except Exception as install_error:
                    try:
                        recover_transaction(skills, destination, True)
                    except Exception as recovery_error:
                        raise InstallError(
                            f"installation failed and automatic recovery also failed: {recovery_error}"
                        ) from install_error
                    if verify_package(destination) != plan:
                        raise
                    print("Recovered a verified installation after an interrupted transaction.")
                clear_journal(skills)

            print(f"Installed {SKILL_NAME} to {destination}")
            print(f"Installed payload: {plan['payload_file_count']} files, {format_size(int(plan['payload_size_bytes']))}")
            print(f"Tree SHA-256: {plan['tree_sha256']}")
            print("Restart Codex to pick up new skills.")
            return 0
        finally:
            if _lexists(stage) and not _lexists(_journal_path(skills)):
                safe_remove_tree(stage, skills, prefix=STAGE_PREFIX)


def rollback(skills_dir: Path, *, legacy: bool = False, recover: bool = False) -> int:
    skills, destination = assert_safe_layout(REPO_ROOT, skills_dir)
    backup = skills / (LEGACY_BACKUP_NAME if legacy else BACKUP_NAME)
    if not skills.exists():
        raise InstallError(f"skills directory does not exist: {skills}")
    with InstallLock(skills, recover):
        pending_recovery = (
            _lexists(_journal_path(skills))
            or _lexists(skills / f"{JOURNAL_NAME}.tmp")
            or any(
                path.name.startswith((STAGE_PREFIX, OLD_PREFIX, SWAP_PREFIX))
                for path in skills.iterdir()
            )
        )
        recover_transaction(skills, destination, recover)
        if recover and pending_recovery:
            validate_existing_install(destination, allow_drift=True)
            print(f"Recovery complete; {SKILL_NAME} is active at {destination}")
            return 0
        if not destination.exists() or not backup.exists():
            raise InstallError(f"rollback requires both active and backup installations: {destination}, {backup}")
        validate_existing_install(destination, allow_drift=True)
        validate_existing_install(backup, allow_drift=True)
        active_before = _installation_fingerprint(destination)
        backup_before = _installation_fingerprint(backup)
        swap = Path(tempfile.mkdtemp(prefix=SWAP_PREFIX, dir=skills))
        swap.rmdir()
        write_journal(
            skills,
            {"version": 1, "phase": "rollback_prepared", "backup_name": backup.name, "swap_name": swap.name},
        )
        try:
            atomic_replace(destination, swap)
            write_journal(
                skills,
                {"version": 1, "phase": "rollback_current_moved", "backup_name": backup.name, "swap_name": swap.name},
            )
            atomic_replace(backup, destination)
            write_journal(
                skills,
                {"version": 1, "phase": "rollback_backup_moved", "backup_name": backup.name, "swap_name": swap.name},
            )
            atomic_replace(swap, backup)
            validate_existing_install(destination, allow_drift=True)
            validate_existing_install(backup, allow_drift=True)
            clear_journal(skills)
        except Exception as rollback_error:
            try:
                recover_transaction(skills, destination, True)
            except Exception as recovery_error:
                raise InstallError(
                    f"rollback failed and automatic recovery also failed: {recovery_error}"
                ) from rollback_error
            if (
                destination.exists()
                and backup.exists()
                and _installation_fingerprint(destination) == backup_before
                and _installation_fingerprint(backup) == active_before
            ):
                print("Recovered the requested rollback after an interrupted transaction.")
                print(f"Rolled back {SKILL_NAME} at {destination}")
                return 0
            raise
        print(f"Rolled back {SKILL_NAME} at {destination}")
        return 0


def check_install(skills_dir: Path) -> int:
    _skills, destination = assert_safe_layout(REPO_ROOT, skills_dir)
    try:
        installed_plan = verify_package(destination)
        reviewed_plan = package_plan(REPO_ROOT)
    except (PackageError, InstallError) as exc:
        print(f"Installed package verification failed: {exc}")
        return 1
    if installed_plan != reviewed_plan:
        print("Installed package verification failed: package does not match this checkout's reviewed source lock")
        return 1
    print(f"Verified {SKILL_NAME} at {destination}")
    print(f"Tree SHA-256: {installed_plan['tree_sha256']}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the reviewed Seedance runtime package safely.")
    parser.add_argument(
        "--dest",
        type=Path,
        default=default_skills_dir(),
        help="skills directory; defaults to $CODEX_HOME/skills or ~/.codex/skills",
    )
    parser.add_argument("--force", action="store_true", help="replace an existing install with verified backup")
    parser.add_argument("--dry-run", action="store_true", help="validate and print the exact plan without writes")
    parser.add_argument("--recover", action="store_true", help="recover a stale lock or interrupted transaction")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true", help="verify the installed package and exit")
    action.add_argument("--rollback", action="store_true", help="swap the active package with the last backup")
    action.add_argument("--rollback-legacy", action="store_true", help="swap with the preserved legacy backup")
    args = parser.parse_args()

    if (args.check or args.rollback or args.rollback_legacy) and (args.force or args.dry_run):
        parser.error("--check/--rollback cannot be combined with --force or --dry-run")
    if args.check and args.recover:
        parser.error("--check cannot be combined with --recover; recover first, then check")
    if args.dry_run and args.recover:
        parser.error("--dry-run cannot be combined with --recover")
    try:
        if args.check:
            return check_install(args.dest)
        if args.rollback or args.rollback_legacy:
            return rollback(args.dest, legacy=args.rollback_legacy, recover=args.recover)
        return install(REPO_ROOT, args.dest, force=args.force, dry_run=args.dry_run, recover=args.recover)
    except (InstallError, PackageError, OSError) as exc:
        print(f"Install error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
