#!/usr/bin/env python3
"""
render_batch.py - run many Phase-4 renders in parallel.

Manim's Cairo renderer is single-threaded, so the only way to use more than one
core is to run more than one render. This launches N `main.py --job ...`
subprocesses at a time and reports what happened.

Runs unchanged on Windows (laptop, --workers 2) and Linux (cloud pod,
--workers 14). Worker count is capped by free RAM, not just core count: each
Manim process holds ~2-2.5 GB at 1080x1920, so an unbounded pool will swap the
machine to death instead of going faster.

    python render_batch.py --all
    python render_batch.py --jobs jobs/auto/auto_12 jobs/sort_job --workers 2
    python render_batch.py --all --dry-run
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

REPO_ROOT = Path(__file__).resolve().parent
RAM_GB_PER_WORKER = 2.5


# ----------------------------------------------------------------------------
# Machine probing
# ----------------------------------------------------------------------------
def _free_ram_gb() -> Optional[float]:
    """Available RAM in GB, or None if we can't tell. No hard dependencies."""
    try:
        import psutil  # type: ignore
        return psutil.virtual_memory().available / (1024 ** 3)
    except Exception:
        pass

    if sys.platform == "win32":
        try:
            import ctypes

            class _MemStatus(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            st = _MemStatus()
            st.dwLength = ctypes.sizeof(_MemStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st)):
                return st.ullAvailPhys / (1024 ** 3)
        except Exception:
            return None
        return None

    try:  # Linux
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / (1024 ** 2)
    except Exception:
        return None
    return None


def _cgroup_cpu_limit():
    """CPUs this container may actually use, or None if unrestricted.

    A RunPod CPU pod reports the HOST's core count through os.cpu_count() - an
    8-vCPU pod says 192 - so trusting it would launch ~24x too many renders and
    thrash the box. The cgroup quota is the real allocation.
    """
    try:  # cgroup v2
        raw = Path("/sys/fs/cgroup/cpu.max").read_text().split()
        if raw[0] != "max":
            return int(raw[0]) / int(raw[1])
    except Exception:
        pass
    try:  # cgroup v1
        q = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us").read_text())
        per = int(Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us").read_text())
        if q > 0 and per > 0:
            return q / per
    except Exception:
        pass
    return None


def _cgroup_mem_limit_gb():
    """RAM ceiling for this container, or None. Same host-vs-container trap:
    /proc/meminfo on a pod shows the host's total, not the pod's share."""
    for path in ("/sys/fs/cgroup/memory.max",
                 "/sys/fs/cgroup/memory/memory.limit_in_bytes"):
        try:
            raw = Path(path).read_text().strip()
            if raw == "max":
                continue
            val = int(raw)
            if 0 < val < (1 << 62):  # unset limits show up as absurd numbers
                return val / (1024 ** 3)
        except Exception:
            continue
    return None


def default_workers() -> int:
    cpu = os.cpu_count() or 2
    quota = _cgroup_cpu_limit()
    if quota:
        cpu = max(1, int(quota))
    by_cpu = max(1, cpu - 1)
    free = _free_ram_gb()
    cap = _cgroup_mem_limit_gb()
    if cap is not None:
        free = cap if free is None else min(free, cap)
    if free is None:
        return max(1, min(by_cpu, 2))  # unknown RAM: stay conservative
    by_ram = max(1, int(free // RAM_GB_PER_WORKER))
    return max(1, min(by_cpu, by_ram))


# ----------------------------------------------------------------------------
# Job discovery
# ----------------------------------------------------------------------------
def discover_jobs(jobs_root: Path) -> List[Path]:
    """Every directory under jobs/ holding a job.json, in stable order."""
    if not jobs_root.is_dir():
        return []
    return sorted({p.parent for p in jobs_root.rglob("job.json")})


def is_done(job_dir: Path) -> bool:
    return (job_dir / "output" / "final.mp4").is_file()


def label(job_dir: Path) -> str:
    try:
        return job_dir.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return job_dir.as_posix()


# ----------------------------------------------------------------------------
# Execution
# ----------------------------------------------------------------------------
@dataclass
class Task:
    job_dir: Path
    proc: Optional[subprocess.Popen] = None
    log_handle: Optional[object] = None
    log_path: Optional[Path] = None
    started: float = 0.0
    elapsed: float = 0.0
    status: str = "pending"
    returncode: Optional[int] = None


def build_cmd(job_dir: Path, quality: str) -> List[str]:
    return [
        sys.executable,
        "main.py",
        "--job", label(job_dir),
        "-q", quality,
    ]


def start(task: Task, quality: str) -> None:
    log_dir = task.job_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    task.log_path = log_dir / "render_batch.log"
    task.log_handle = open(task.log_path, "w", encoding="utf-8", errors="replace")
    task.started = time.time()
    task.status = "running"
    task.proc = subprocess.Popen(
        build_cmd(task.job_dir, quality),
        cwd=str(REPO_ROOT),
        stdout=task.log_handle,
        stderr=subprocess.STDOUT,
    )


def finish(task: Task) -> None:
    task.elapsed = time.time() - task.started
    task.returncode = task.proc.returncode if task.proc else -1
    task.status = "ok" if task.returncode == 0 else "FAILED"
    try:
        task.log_handle.close()  # type: ignore[union-attr]
    except Exception:
        pass


def tail(path: Optional[Path], n: int = 12) -> List[str]:
    if not path or not path.is_file():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()[-n:]
    except Exception:
        return []


def fmt(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return "{:d}m{:02d}s".format(m, s)


def run_pool(tasks: List[Task], workers: int, quality: str) -> None:
    queue = list(tasks)
    active: List[Task] = []
    done = 0
    total = len(tasks)
    t0 = time.time()

    try:
        while queue or active:
            while queue and len(active) < workers:
                task = queue.pop(0)
                start(task, quality)
                active.append(task)
                print("[start ] {}  ({}/{} workers busy)".format(
                    label(task.job_dir), len(active), workers), flush=True)

            time.sleep(1.0)

            for task in list(active):
                if task.proc and task.proc.poll() is not None:
                    finish(task)
                    active.remove(task)
                    done += 1
                    mark = "ok    " if task.status == "ok" else "FAIL  "
                    print("[{}] {}  {}  ({}/{} done, {} elapsed)".format(
                        mark, label(task.job_dir), fmt(task.elapsed),
                        done, total, fmt(time.time() - t0)), flush=True)
    except KeyboardInterrupt:
        print("\n[abort ] terminating running renders...", flush=True)
        for task in active:
            try:
                task.proc.terminate()  # type: ignore[union-attr]
            except Exception:
                pass
        for task in active:
            try:
                task.proc.wait(timeout=20)  # type: ignore[union-attr]
            except Exception:
                try:
                    task.proc.kill()  # type: ignore[union-attr]
                except Exception:
                    pass
            finish(task)
            task.status = "aborted"
        raise


# ----------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Render many jobs in parallel.")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--jobs", nargs="+", help="job directories, e.g. jobs/auto/auto_12")
    src.add_argument("--all", action="store_true",
                     help="every job under jobs/ that has no final.mp4")
    ap.add_argument("--workers", type=int, default=None,
                    help="parallel renders (default: min(cores-1, free_ram/2.5GB))")
    ap.add_argument("-q", "--quality", default="h",
                    help="manim quality passed to main.py (default: h)")
    ap.add_argument("--force", action="store_true",
                    help="re-render jobs that already have output/final.mp4")
    ap.add_argument("--dry-run", action="store_true", help="print the plan and exit")
    args = ap.parse_args()

    if args.all:
        candidates = discover_jobs(REPO_ROOT / "jobs")
    else:
        candidates = []
        for raw in args.jobs:
            p = Path(raw)
            p = p if p.is_absolute() else (REPO_ROOT / p)
            candidates.append(p.resolve())

    selected: List[Path] = []
    skipped: List[Path] = []
    missing: List[Path] = []
    for job_dir in candidates:
        if not (job_dir / "job.json").is_file():
            missing.append(job_dir)
        elif is_done(job_dir) and not args.force:
            skipped.append(job_dir)
        else:
            selected.append(job_dir)

    for job_dir in missing:
        print("[skip  ] {} - no job.json".format(label(job_dir)))
    for job_dir in skipped:
        print("[skip  ] {} - output/final.mp4 exists (use --force)".format(label(job_dir)))

    if not selected:
        print("\nNothing to render.")
        return 0

    workers = args.workers if args.workers else default_workers()
    workers = max(1, min(workers, len(selected)))

    free = _free_ram_gb()
    cap = _cgroup_mem_limit_gb()
    if cap is not None:
        free = cap if free is None else min(free, cap)
    free_txt = "{:.1f} GB usable".format(free) if free is not None else "RAM unknown"
    quota = _cgroup_cpu_limit()
    cores_txt = "{:g} cores".format(quota) if quota else "{} cores".format(os.cpu_count())
    print()
    print("{} job(s) to render - {} worker(s) [{}, {}], quality=-q{}".format(
        len(selected), workers, cores_txt, free_txt, args.quality))
    for job_dir in selected:
        print("  - " + label(job_dir))

    if args.dry_run:
        print("\n[dry-run] nothing executed.")
        return 0

    tasks = [Task(job_dir=d) for d in selected]
    t0 = time.time()
    print()
    run_pool(tasks, workers, args.quality)
    wall = time.time() - t0

    # ---- summary ----
    width = max([len(label(t.job_dir)) for t in tasks] + [10])
    print("\n" + "=" * (width + 26))
    print("{}  {:<8}  TIME".format("JOB".ljust(width), "STATUS"))
    print("-" * (width + 26))
    for t in tasks:
        print("{}  {:<8}  {}".format(label(t.job_dir).ljust(width), t.status, fmt(t.elapsed)))
    print("=" * (width + 26))

    failed = [t for t in tasks if t.status != "ok"]
    ok = len(tasks) - len(failed)
    cpu_min = sum(t.elapsed for t in tasks) / 60.0
    print("{}/{} rendered in {} wall ({:.1f} core-minutes of work)".format(
        ok, len(tasks), fmt(wall), cpu_min))

    for t in failed:
        print("\n--- {} (exit {}) - last lines of {} ---".format(
            label(t.job_dir), t.returncode, t.log_path))
        for line in tail(t.log_path):
            print("    " + line)

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
