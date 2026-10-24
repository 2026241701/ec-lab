"""Build the Windows portable app with an isolated dependency search path.

Run with the project's virtual-environment Python, from any working directory::

    .venv\\Scripts\\python.exe tools\\build_portable.py --noconfirm

Relative --distpath and --workpath values are resolved against the repository.
The build always uses --clean. A successful PyInstaller run is followed by an
allowlist check of the Analysis TOC; a rejected build must not be distributed.
"""

from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import subprocess
import sys
from typing import Iterable, Iterator


REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "ec_lab.spec"
THREAD_VARIABLES = (
    "OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "BLIS_NUM_THREADS",
)
SOURCE_ENTRY_TYPES = {
    "BINARY", "EXTENSION", "DATA", "PYMODULE", "PYSOURCE", "ZIPFILE",
    "EXECUTABLE", "PKG",
}


def unique_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        path = path.resolve()
        key = os.path.normcase(str(path))
        if key not in seen:
            seen.add(key)
            result.append(path)
    return result


def windows_directory() -> Path:
    return Path(os.environ.get("SystemRoot") or os.environ.get("WINDIR") or r"C:\Windows")


def build_environment() -> dict[str, str]:
    """Only replace the child's environment; never modify the shell's PATH."""
    env = os.environ.copy()
    # Environment keys are case-insensitive on Windows. Remove inherited keys
    # explicitly so this also behaves correctly with ordinary dictionaries.
    for key in list(env):
        if key.upper() in {"PATH", "PYTHONPATH", "PYTHONHOME"}:
            del env[key]
    base = Path(sys.base_prefix)
    windows = windows_directory()
    env["PATH"] = os.pathsep.join(str(path) for path in unique_paths((
        Path(sys.executable).parent, base, base / "DLLs",
        windows / "System32", windows,
    )))
    # User site packages are another possible source of machine-specific imports.
    env["PYTHONNOUSERSITE"] = "1"
    for key in THREAD_VARIABLES:
        env[key] = "1"
    return env


def allowed_source_roots() -> list[Path]:
    """Dependencies must originate in the project, this Python, or Windows."""
    return unique_paths((
        REPO_ROOT, Path(sys.prefix), Path(sys.base_prefix),
        Path(sys.executable).parent, windows_directory(),
    ))


def iter_source_entries(value: object) -> Iterator[tuple[str, str, str]]:
    if not isinstance(value, (list, tuple)):
        return
    if (len(value) == 3 and all(isinstance(item, str) for item in value)
            and value[2] in SOURCE_ENTRY_TYPES):
        yield value[0], value[1], value[2]
        return
    for item in value:
        yield from iter_source_entries(item)


def audit_analysis_toc(toc_path: Path, roots: Iterable[Path]) -> int:
    """Reject dependencies outside allowed roots, without executing TOC code."""
    content = toc_path.read_text(encoding="utf-8")
    # This known collision must also be caught if a runtime is copied inside an
    # otherwise permitted directory. ICU from Poppler cannot replace Windows ICU.
    if "codex-runtimes" in content.casefold():
        raise ValueError(f"Foreign Codex runtime reference in {toc_path}")
    analysis = ast.literal_eval(content)
    allowed = unique_paths(roots)
    entries = list(iter_source_entries(analysis))
    if not entries:
        raise ValueError(f"No dependency source entries found in {toc_path}")
    rejected = []
    for name, source, kind in entries:
        path = Path(source)
        if not path.is_absolute():
            path = REPO_ROOT / path
        path = path.resolve()
        if not source or not any(path.is_relative_to(root) for root in allowed):
            rejected.append(f"  {kind} {name}: {source}")
    if rejected:
        details = "\n".join(rejected[:30])
        if len(rejected) > 30:
            details += f"\n  ... and {len(rejected) - 30} more"
        raise ValueError(
            f"{len(rejected)} dependency sources outside allowed roots in {toc_path}:\n"
            f"{details}"
        )
    return len(entries)


def repository_path(value: str) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else REPO_ROOT / path).resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--distpath", default="dist", help="Output directory (relative to repository)")
    parser.add_argument("--workpath", default="build", help="Build directory (relative to repository)")
    parser.add_argument("--noconfirm", action="store_true", help="Replace existing PyInstaller output")
    parser.add_argument("--clean", action="store_true", default=True,
                        help="Accepted for compatibility; always enabled")
    args = parser.parse_args(argv)
    if os.name != "nt":
        parser.error("This entry point builds the Windows portable app; run it on Windows.")
    if not SPEC_PATH.is_file():
        parser.error(f"Spec file not found: {SPEC_PATH}")
    distpath = repository_path(args.distpath)
    workpath = repository_path(args.workpath)
    command = [sys.executable, "-m", "PyInstaller", str(SPEC_PATH), "--clean",
               "--distpath", str(distpath), "--workpath", str(workpath)]
    if args.noconfirm:
        command.append("--noconfirm")
    env = build_environment()
    print(f"Repository: {REPO_ROOT}", flush=True)
    print(f"Python: {sys.executable}", flush=True)
    print(f"Isolated PATH: {env['PATH']}", flush=True)
    try:
        completed = subprocess.run(command, cwd=REPO_ROOT, env=env, check=False)
        if completed.returncode:
            print(f"PyInstaller failed (exit {completed.returncode}).", file=sys.stderr)
            return completed.returncode
        # PyInstaller places analysis files under workpath/spec-stem, including
        # when workpath was supplied as an absolute path or with Unicode names.
        analysis_dir = workpath / SPEC_PATH.stem
        tocs = sorted(analysis_dir.glob("Analysis-*.toc"))
        if not tocs:
            raise ValueError(f"No Analysis TOC found in {analysis_dir}")
        roots = allowed_source_roots()
        checked = sum(audit_analysis_toc(path, roots) for path in tocs)
    except (OSError, ValueError, SyntaxError) as exc:
        print(f"BUILD REJECTED: {exc}\nDo not distribute this output.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Build interrupted.", file=sys.stderr)
        return 130
    print(f"Dependency audit passed: {checked} entries in {len(tocs)} Analysis TOC(s).", flush=True)
    print(f"Portable app: {distpath / 'ec-lab' / 'ec-lab.exe'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
