# installer.py
"""
产物安装：把 output 目录中的 bundle 产物备份并覆盖到游戏目录，支持从备份回滚。

原版文件判定：Bundle.get_trailing_bytes 返回 0 表示文件未被修改过（原版）；
产物文件因追加了 CRC 修正尾，该值不为 0。备份目录只保存原版文件，
因此已有备份时不会用可能被修改过的游戏文件覆盖它。
"""

import shutil
from dataclasses import dataclass
from pathlib import Path

from .bundle import Bundle
from .searching import get_search_dirs
from .utils import LogFunc, no_log


@dataclass
class InstallReport:
    """单个 bundle 的安装/回滚结果"""
    name: str
    game_path: Path | None    # 游戏内目标文件；None 表示未找到同名文件
    backup_path: Path | None  # 涉及的备份文件路径
    ok: bool
    message: str              # 结果说明（供 CLI 汇总展示）


def _find_game_bundle(name: str, search_dirs: list[Path]) -> Path | None:
    """按文件名在游戏资源目录中定位 bundle（文件名含版本哈希，全局唯一）"""
    for dir in search_dirs:
        candidate = dir / name
        if candidate.is_file():
            return candidate
    return None


def _apply_one(
    output: Path,
    search_dirs: list[Path],
    backup_dir: Path,
    force: bool,
    log: LogFunc,
) -> InstallReport:
    """备份并覆盖单个产物 bundle"""
    name = output.name

    # 产物自检：CRC 与文件名不一致说明产物损坏，要求重新生成
    if not Bundle.check_crc_match(output):
        log(f"❌ {name}: output bundle CRC mismatch (regenerate it with `replace`), skipped.")
        return InstallReport(name, None, None, False, "invalid output bundle")

    game_file = _find_game_bundle(name, search_dirs)
    if game_file is None:
        log(f"⚠️ {name}: no bundle with the same name in the game directory "
            f"(the game may have been updated), skipped.")
        return InstallReport(name, None, None, False, "target not found in game")

    # 原版判定：trailing 为 None 表示损坏/非 UnityFS；不为 0 表示已被修改过
    trailing = Bundle.get_trailing_bytes(game_file)
    backup_path = backup_dir / name
    if trailing == 0:
        if backup_path.is_file():
            log(f"  > Backup already exists, keeping the original: {backup_path.name}")
        else:
            shutil.copy2(game_file, backup_path)
            log(f"  > Backup saved: {backup_path.name}")
    elif not backup_path.is_file() and not force:
        # 已被修改过且没有备份：为避免丢失当前文件，拒绝覆盖
        log(f"⚠️ {name}: target is already modified and no backup exists, "
            f"skipped to protect the current file (use --force to override).")
        return InstallReport(name, game_file, None, False, "modified without backup")

    # 覆盖游戏目录中的文件
    try:
        shutil.copy2(output, game_file)
    except PermissionError as e:
        log(f"❌ {name}: failed to write game file (is the game running?): {e}")
        return InstallReport(name, game_file, backup_path, False, "permission denied")

    # 覆盖后自检：整文件 CRC 应等于文件名中的目标值
    if not Bundle.check_crc_match(game_file):
        log(f"❌ {name}: applied but CRC check failed after writing.")
        return InstallReport(name, game_file, backup_path, False, "crc mismatch after write")

    log(f"  ✅ Applied: {name} -> {game_file}")
    return InstallReport(name, game_file, backup_path, True, "applied")


def apply_bundles(
    game_dir: Path,
    output_dir: Path,
    backup_dir: Path,
    force: bool = False,
    log: LogFunc = no_log,
) -> list[InstallReport]:
    """
    把 output_dir 中的全部产物 bundle 备份并覆盖到游戏目录。

    Args:
        game_dir: 游戏资源根目录
        output_dir: 产物目录（replace 的输出）
        backup_dir: 原版备份目录（只保存 trailing == 0 的原版文件）
        force: 允许覆盖损坏/已修改且无备份的目标文件
        log: 日志记录函数

    Returns:
        每个产物的 InstallReport 列表；output_dir 为空时返回 []
    """
    outputs = sorted(p for p in output_dir.glob("*.bundle") if p.is_file())
    if not outputs:
        log(f"❌ No output bundles found in '{output_dir}'. Run `replace` first.")
        return []

    search_dirs = get_search_dirs(game_dir)
    if not search_dirs:
        log(f"❌ No resource directories found under '{game_dir}'.")
        return []

    backup_dir.mkdir(parents=True, exist_ok=True)
    return [_apply_one(output, search_dirs, backup_dir, force, log) for output in outputs]


def _restore_one(backup: Path, search_dirs: list[Path], log: LogFunc) -> InstallReport:
    """把单个备份文件还原到游戏目录"""
    name = backup.name

    # 备份自检：损坏的备份不允许写回游戏目录
    if not Bundle.check_crc_match(backup):
        log(f"❌ {name}: backup file CRC mismatch, skipped.")
        return InstallReport(name, None, backup, False, "invalid backup file")

    game_file = _find_game_bundle(name, search_dirs)
    if game_file is None:
        log(f"⚠️ {name}: no bundle with the same name in the game directory "
            f"(the game may have been updated), skipped.")
        return InstallReport(name, None, backup, False, "target not found in game")

    try:
        shutil.copy2(backup, game_file)
    except PermissionError as e:
        log(f"❌ {name}: failed to write game file (is the game running?): {e}")
        return InstallReport(name, game_file, backup, False, "permission denied")

    if not Bundle.check_crc_match(game_file):
        log(f"❌ {name}: restored but CRC check failed after writing.")
        return InstallReport(name, game_file, backup, False, "crc mismatch after write")

    log(f"  ✅ Restored: {name} -> {game_file}")
    return InstallReport(name, game_file, backup, True, "restored")


def restore_bundles(
    game_dir: Path,
    backup_dir: Path,
    log: LogFunc = no_log,
) -> list[InstallReport]:
    """
    把 backup_dir 中的全部备份还原到游戏目录（回滚 apply 的修改）。

    Returns:
        每个备份的 InstallReport 列表；backup_dir 为空时返回 []
    """
    backups = sorted(p for p in backup_dir.glob("*.bundle") if p.is_file())
    if not backups:
        log(f"❌ No backup bundles found in '{backup_dir}'.")
        return []

    search_dirs = get_search_dirs(game_dir)
    if not search_dirs:
        log(f"❌ No resource directories found under '{game_dir}'.")
        return []

    return [_restore_one(backup, search_dirs, log) for backup in backups]
