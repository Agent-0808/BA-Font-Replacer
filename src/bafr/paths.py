# paths.py
"""
Game installation path locator.
Adapted from [BA-Modding-Toolkit](https://github.com/Agent-0808/BA-Modding-Toolkit)
"""

from pathlib import Path
from typing import Literal


def _get_path_from_registry(key_path: str) -> str | None:
    """从 Windows 注册表获取 Steam 游戏的安装路径。"""

    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        install_path, _ = winreg.QueryValueEx(key, "InstallLocation")
        winreg.CloseKey(key)

        if install_path:
            return install_path

    except Exception as e:
        print(f"读取注册表 {key_path} 时出错: {e}")

    return None


_ba_path_cache: dict[str, str | None] = {}

# 游戏区服，用于定位安装路径；auto = global 优先，japan 兜底
BARegion = Literal["auto", "global", "japan"]

# 国际服 Steam AppID
BA_STEAM_APPID = 3557620

# CAB → 物理 bundle 映射缓存默认位置
DEFAULT_CACHE_PATH = Path.home() / ".bafr" / "cab_cache.json"


def get_BA_path(region: BARegion = "auto") -> str | None:
    """获取游戏安装路径，带缓存机制

    Args:
        region: 区服，"auto"（默认）时优先返回 global 的结果，找不到则回退 japan

    Returns:
        游戏安装路径，如果未找到则返回 None
    """
    if region in _ba_path_cache:
        return _ba_path_cache[region]

    if region == "global":
        result = _get_path_from_registry(fr"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App {BA_STEAM_APPID}")
    elif region == "japan":
        result = _get_path_from_registry(r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\e02a2fab-b426-5ce2-b9de-b9e7506c327e")
    else:  # auto
        result = get_BA_path("global") or get_BA_path("japan")
        return result  # auto 不缓存，保持对注册表变化的响应

    _ba_path_cache[region] = result
    return result


def resolve_game_dir(game_path: Path | str | None, region: BARegion = "auto") -> Path | None:
    """解析游戏根目录：显式路径优先，否则按区服探测注册表。

    Returns:
        游戏根目录 Path；无法确定时返回 None
    """
    if game_path is not None:
        return Path(game_path)
    detected = get_BA_path(region)
    return Path(detected) if detected else None
