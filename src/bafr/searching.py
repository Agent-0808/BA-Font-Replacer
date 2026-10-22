# searching.py
"""
Bundle locator.
Adapted from [BA-Modding-Toolkit](https://github.com/Agent-0808/BA-Modding-Toolkit)
"""

import json
import os
from pathlib import Path

from .bundle import Bundle, BundleFileInfo, get_cab_names
from .naming import parse_filename
from .utils import LogFunc, no_log

# 相对游戏根目录的资源搜索目录（按实际存在性筛选）
SEARCH_DIR_SUFFIXES = [
    "",
    "BlueArchive_Data/StreamingAssets/PUB/Resource/GameData/Windows",
    "BlueArchive_Data/StreamingAssets/PUB/Resource/Preload/Windows",
    "GameData/Windows",
    "Preload/Windows",
    "GameData/Android",
    "Preload/Android",
]


def get_search_dirs(base_dir: Path) -> list[Path]:
    """获取游戏资源搜索目录列表。"""
    return [
        base_dir / suffix
        for suffix in SEARCH_DIR_SUFFIXES
        if (base_dir / suffix).is_dir()
    ]


def find_bundles_by_prefix(
    prefix: str,
    search_dirs: list[Path],
    log: LogFunc = no_log,
) -> list[Path]:
    """
    按文件名前缀在搜索目录中收集 bundle 文件（scandir 避免海量文件时逐个 stat）。

    Args:
        prefix: 文件名前缀（如 "ui-font-_mxload-"）
        search_dirs: 搜索目录列表
        log: 日志记录函数

    Returns:
        匹配的 bundle 文件路径列表
    """
    candidates: list[Path] = []
    for dir in search_dirs:
        if not dir.is_dir():
            continue
        with os.scandir(dir) as it:
            candidates.extend(
                Path(entry.path)
                for entry in it
                if entry.name.startswith(prefix)
                and entry.name.endswith('.bundle')
                and entry.is_file(follow_symlinks=False)
            )

    log(f"  > Found {len(candidates)} candidate(s) with prefix '{prefix}'.")
    return candidates


def list_bundle_files(base_dir: Path) -> list[BundleFileInfo]:
    """
    快速扫描搜索目录下的所有 bundle 文件，仅收集基础信息（路径、大小、修改时间）。

    Args:
        base_dir: 游戏资源根目录

    Returns:
        BundleFileInfo 列表（仅基础字段已填充）
    """
    results = []
    seen = set()
    for directory in get_search_dirs(base_dir):
        with os.scandir(directory) as it:
            for entry in it:
                if not entry.is_file(follow_symlinks=False):
                    continue
                if not entry.name.endswith('.bundle'):
                    continue

                # 直接使用 entry.stat() 获取大小和修改时间
                st = entry.stat(follow_symlinks=False)

                bundle_path = Path(entry.path)
                if bundle_path in seen:
                    continue
                seen.add(bundle_path)
                results.append(BundleFileInfo(
                    path=bundle_path,
                    file_size=st.st_size,
                    modified_time=st.st_mtime,
                ))

    return results


def find_cab_bundles(
    target_cabs: set[str],
    search_dirs: list[Path],
    log: LogFunc = no_log,
    max_bundle_size: int = 64 * 1024 * 1024,
    cache_path: Path | None = None,
) -> dict[str, Path]:
    """
    在搜索目录的全部 bundle 中查找内部 SerializedFile 名（CAB-xxx）匹配的物理 bundle。

    优先用轻量头部解析（get_cab_names，不解压数据块），解析失败时回退 Bundle.load；
    按文件大小升序扫描以尽快命中，超过 max_bundle_size 的文件直接跳过。
    提供 cache_path 时先查缓存（按路径+大小+mtime 校验有效性，不符则重扫），
    扫描结果写回缓存。

    Args:
        target_cabs: 目标 CAB 名集合（如 {"CAB-a657a..."}）
        search_dirs: 搜索目录列表
        log: 日志记录函数
        max_bundle_size: 单个 bundle 的大小上限（字节），超过则跳过
        cache_path: CAB 映射缓存文件路径；None 表示不使用缓存

    Returns:
        {CAB 名: 物理 bundle 路径}；未命中的 CAB 不在结果中
    """
    remaining = set(target_cabs)
    found: dict[str, Path] = {}
    if not remaining:
        return found

    # 1. 缓存命中（路径存在且大小/mtime 与记录一致）
    cache = CabCache.load(cache_path) if cache_path else None
    if cache is not None:
        cached, remaining = cache.lookup(remaining)
        found.update(cached)
        if cached:
            log(f"  > {len(cached)} CAB target(s) resolved from cache.")

    # 2. 扫描未命中的 CAB（小文件优先）
    if remaining:
        # 收集候选并按大小升序
        candidates: list[Path] = []
        for dir in search_dirs:
            if not dir.is_dir():
                continue
            with os.scandir(dir) as it:
                for entry in it:
                    if (entry.name.endswith('.bundle')
                            and entry.is_file(follow_symlinks=False)
                            and entry.stat(follow_symlinks=False).st_size <= max_bundle_size):
                        candidates.append(Path(entry.path))
        candidates.sort(key=lambda p: p.stat().st_size)

        log(f"  > Scanning {len(candidates)} bundle(s) for {len(remaining)} CAB target(s)...")
        total = len(candidates)
        progress_step = max(1, total // 20)  # 每 5% 打印一次
        for idx, bundle_path in enumerate(candidates):
            if not remaining:
                break
            if (idx + 1) % progress_step == 0 or idx + 1 == total:
                log(f"  > Progress: {((idx + 1) * 100) // total}% ({idx + 1}/{total})")
            # 轻量解析仅读头部 blockinfo；失败时回退全量加载
            names = get_cab_names(bundle_path)
            if names is None:
                bundle = Bundle.load(bundle_path, log)
                if bundle is None:
                    continue
                try:
                    names = {getattr(sf, "name", "") for sf in bundle.env.assets}
                except Exception:
                    continue
            hit = names & remaining
            if hit:
                for cab in hit:
                    found[cab] = bundle_path
                    remaining.discard(cab)
                    log(f"  > CAB match: {cab} -> {bundle_path.name}")
                if cache is not None:
                    cache.update({cab: bundle_path for cab in hit})

        if remaining:
            log(f"  > ⚠️ CAB target(s) not found: {', '.join(sorted(remaining))}")

    if cache is not None:
        cache.save()
    return found


class CabCache:
    """CAB → 物理 bundle 映射缓存（JSON 文件，按路径+大小+mtime 校验有效性）。

    游戏更新导致文件变化时校验失败、自动回退重扫并覆写条目，
    因此缓存过期只会带来一次重扫，不会返回错误映射。
    """

    CACHE_VERSION = 1

    def __init__(self, path: Path):
        self.path = path
        # {cab: {"path": str, "size": int, "mtime": float}}
        self.entries: dict[str, dict] = {}

    @classmethod
    def load(cls, path: Path) -> "CabCache":
        cache = cls(path)
        try:
            if path.is_file():
                data = json.loads(path.read_text(encoding="utf-8"))
                if data.get("version") == cls.CACHE_VERSION:
                    cache.entries = data.get("entries", {})
        except Exception:
            cache.entries = {}
        return cache

    def lookup(self, cabs: set[str]) -> tuple[dict[str, Path], set[str]]:
        """查询缓存，返回 (命中 {cab: path}, 未命中集合)。

        命中要求记录的文件仍存在且大小/mtime 与记录一致。
        """
        hits: dict[str, Path] = {}
        for cab in cabs:
            entry = self.entries.get(cab)
            if not entry:
                continue
            path = Path(entry["path"])
            try:
                st = path.stat()
            except OSError:
                continue
            if st.st_size == entry.get("size") and st.st_mtime == entry.get("mtime"):
                hits[cab] = path
        return hits, cabs - set(hits)

    def update(self, found: dict[str, Path]) -> None:
        """把新解析的 CAB 映射写入缓存条目"""
        for cab, path in found.items():
            st = path.stat()
            self.entries[cab] = {
                "path": str(path),
                "size": st.st_size,
                "mtime": st.st_mtime,
            }

    def save(self) -> None:
        """保存缓存文件（失败静默，缓存不可用不影响功能）"""
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(
                json.dumps({"version": self.CACHE_VERSION, "entries": self.entries}, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass
