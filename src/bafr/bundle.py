# bundle.py
"""
Adapted from [BA-Modding-Toolkit](https://github.com/Agent-0808/BA-Modding-Toolkit)
"""

import struct
import traceback
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Callable, Literal

import UnityPy
from UnityPy.enums import ArchiveFlags, ArchiveFlagsOld
from UnityPy.environment import Environment as Env
from UnityPy.files import SerializedFile
from UnityPy.helpers import CompressionHelper

from .naming import ParsedFilename, parse_filename
from .utils import LogFunc, no_log, apply_crc_fix, compute_crc32

# 压缩类型（"none" 为 UnityPy 默认分支，flags 64/64，与原型产物一致）
CompressionType = Literal["lzma", "lz4", "original", "none"]


@dataclass
class BundleFileInfo:
    """扫描结果中单个 bundle 文件的信息"""
    path: Path
    file_size: int
    modified_time: float = 0.0


class Bundle:
    """
    封装 Bundle 文件的业务类。
    包含了底层的 UnityPy Environment 以及所有业务相关操作（加载、保存）。
    """

    def __init__(self, path: Path, env: Env, log: LogFunc = no_log):
        self.path = path
        self.env = env
        self.log = log

    @property
    def name(self) -> str:
        """快捷获取文件名"""
        return self.path.name

    @cached_property
    def parsed_name(self) -> ParsedFilename:
        """获取解析后的文件名信息（带缓存）"""
        return parse_filename(self.name)

    @property
    def crc(self) -> str:
        """从文件名获取 CRC32 值"""
        return self.parsed_name.crc

    @property
    def core_name(self) -> str:
        """从文件名获取核心名称"""
        return self.parsed_name.core

    def is_empty(self) -> bool:
        """检查 Bundle 是否为空（不包含任何文件）"""
        return len(self.env.files) == 0

    @cached_property
    def sf_name(self) -> str:
        """内部 SerializedFile 名（bundle 内唯一，如 CAB-xxxx）"""
        return next(n for n, f in self.env.file.files.items() if hasattr(f, "objects"))

    @cached_property
    def platform_info(self) -> tuple[str, str]:
        """
        获取 Bundle 文件的平台信息和 Unity 版本。

        Returns:
            tuple[str, str]: (平台名称, Unity版本) 的元组
                             如果找不到则返回 ("UnknownPlatform", "Unknown")
        """
        for file_obj in self.env.files.values():
            for inner_obj in file_obj.files.values():
                if isinstance(inner_obj, SerializedFile) and hasattr(inner_obj, 'target_platform'):
                    return inner_obj.target_platform.name, inner_obj.unity_version

        return "UnknownPlatform", "Unknown"

    def need_crc(self) -> bool:
        """
        判断是否需要执行 CRC 修正。
        当前需要修正的为国际服+Windows平台
        条件：目标平台为 StandaloneWindows64
        """
        platform_name, _ = self.platform_info
        return platform_name == "StandaloneWindows64"

    @staticmethod
    def get_trailing_bytes(bundle_path: Path) -> int | None:
        """
        快速检测 UnityFS bundle 文件尾部添加的额外字节数。

        通过读取文件头中的 size 字段与实际文件大小比较，
        可以在不解压的情况下判断是否需要移除尾部字节。

        Args:
            bundle_path: bundle 文件路径

        Returns:
            int: 需要移除的尾部字节数（0 表示无需移除）
            None: 读取失败
        """
        def read_cstring(f) -> bytes | None:
            """读取以 null 结尾的字符串；EOF 视为无效文件返回 None"""
            out = bytearray()
            while True:
                byte = f.read(1)
                if byte == b'\x00':
                    return bytes(out)
                if not byte:
                    return None
                out.extend(byte)

        try:
            with open(bundle_path, 'rb') as f:
                # 读取签名 (以 null 结尾)
                signature = read_cstring(f)
                if signature is None or signature != b'UnityFS':
                    return None

                # 读取 version (uint32)
                f.read(4)

                # 读取 version_player 与 version_engine (以 null 结尾的字符串)
                if read_cstring(f) is None or read_cstring(f) is None:
                    return None

                # 读取 size (int64, big-endian)
                size_bytes = f.read(8)
                if len(size_bytes) != 8:
                    return None

                recorded_size = int.from_bytes(size_bytes, 'big')

                # 获取实际文件大小
                actual_size = bundle_path.stat().st_size

                # 计算差值
                trailing_bytes = actual_size - recorded_size

                # 如果实际大小小于记录大小，说明文件损坏
                if trailing_bytes < 0:
                    return None

                return trailing_bytes

        except Exception:
            return None

    @classmethod
    def load(cls, bundle_path: Path, log: LogFunc = no_log) -> 'Bundle | None':
        """
        尝试加载一个 Unity bundle 文件。
        使用快速检测尾部字节的方式优化加载流程。

        Returns:
            Bundle 实例，如果加载失败则返回 None
        """
        if not bundle_path.exists():
            log(f'❌ File not exist: {bundle_path}')
            return None

        # 快速检测尾部字节数
        trailing = cls.get_trailing_bytes(bundle_path)

        if trailing is None:
            log(f'❌ Failed to load (not a valid UnityFS file): {bundle_path}')
            return None

        # 尝试加载
        try:
            if trailing == 0:
                env = UnityPy.load(str(bundle_path))
            else:
                data = bundle_path.read_bytes()[:-trailing]
                env = UnityPy.load(data)
            return cls(bundle_path, env, log)
        except Exception:
            pass

        # 如果精确检测后加载失败，尝试 fallback 方式
        try:
            data = bundle_path.read_bytes()
        except Exception as e:
            log(f'  ❌ Failed to read in memory: {bundle_path.name} ({e})')
            return None

        # TODO: 支持用户指定输入
        bytes_to_remove = [4, 8, 12]

        for bytes_num in bytes_to_remove:
            if len(data) > bytes_num:
                try:
                    trimmed_data = data[:-bytes_num]
                    env = UnityPy.load(trimmed_data)
                    return cls(bundle_path, env, log)
                except Exception:
                    pass

        log(f'❌ Failed to load: {bundle_path}')
        return None

    @classmethod
    def check_crc_match(cls, bundle_path: Path) -> bool:
        """
        检查 bundle 实际 CRC 是否已与文件名中的 CRC 一致（一致则无需修正重存）。
        仅需文件名解析与整文件 CRC 计算，无需加载 bundle。
        """
        crc_str = parse_filename(bundle_path.name).crc
        if not crc_str or not crc_str.isdigit():
            return False
        return compute_crc32(bundle_path) == int(crc_str)

    def compress(self, compression: CompressionType = "none") -> bytes:
        """
        从 UnityPy.Environment 对象生成 bundle 文件的字节数据。

        Args:
            compression: 压缩方式
                - "none": 不进行压缩（默认，与原型产物一致）
                - "lzma": 使用 LZMA 压缩
                - "lz4": 使用 LZ4 压缩
                - "original": 保留原始压缩方式
        """
        if not compression or compression == "none":
            packer = ""
        elif compression == "original":
            packer = "original"
        elif compression == "lz4":
            # UnityPy "lz4" uses 0xC2 (BlocksInfoAtTheEnd); use 0x42 so CRC tail is safe.
            packer = (0x42, 2)
        elif compression == "lzma":
            packer = "lzma"
        else:
            raise ValueError(f"Unsupported compression: {compression}")

        return self.env.file.save(packer=packer)

    def save(self, output_path: Path, perform_crc: bool = True, compression: CompressionType = "none") -> tuple[bool, str]:
        """
        生成压缩bundle数据，根据需要执行CRC修正，并最终保存到文件。
        CRC修正使用输出文件名中提取的目标CRC值。

        Returns:
            tuple(bool, str): (是否成功, 状态消息) 的元组。
        """
        try:
            self.log(f"  > Saving bundle [{compression}] [crc: {'on' if perform_crc else 'off'}]")

            compressed_data = self.compress(compression)
            final_data = compressed_data

            if perform_crc:
                crc_str = parse_filename(output_path.name).crc
                if not crc_str or not crc_str.isdigit():
                    return False, f"CRC correction failed: no CRC suffix in filename '{output_path.name}', file not generated."
                target_crc = int(crc_str)

                corrected_data = apply_crc_fix(compressed_data, target_crc)

                if not corrected_data:
                    return False, f"CRC correction failed for '{output_path.name}', file not generated."

                final_data = corrected_data

            with open(output_path, "wb") as f:
                f.write(final_data)

            return True, "Save successful."

        except Exception as e:
            self.log(f'❌ Failed to save: {output_path} ({e})')
            self.log(traceback.format_exc())
            return False, f"Save error: {e}"


# -------- 轻量 CAB 名解析（不做全量解压） --------

def _read_cstring(f) -> bytes:
    """读取以 null 结尾的字符串（读到 EOF 返回已读部分）"""
    out = bytearray()
    while True:
        byte = f.read(1)
        if not byte or byte == b'\x00':
            return bytes(out)
        out.extend(byte)


def _parse_engine_version(version_str: bytes) -> tuple[int, ...]:
    """把引擎版本字符串（如 b'2022.3.55f1'）解析为数字元组，失败返回空元组"""
    parts: list[int] = []
    for token in version_str.decode("ascii", "ignore").split("."):
        digits = ""
        for ch in token:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def get_cab_names(bundle_path: Path) -> set[str] | None:
    """
    仅解析 UnityFS 头部与 blockinfo，返回内部文件名集合（如 {"CAB-xxx"}）。

    内部文件名表位于 blockinfo（通常仅几百字节），无需像 Bundle.load 那样
    解压全部数据块——全目录 CAB 扫描因此从分钟级降到秒级。
    含 4 字节 CRC 修正尾的原版/产物文件均可正确解析（定位用头部 size 字段）。

    Returns:
        内部文件名集合；加密包/未知格式/损坏文件返回 None（调用方回退 Bundle.load）
    """
    try:
        with open(bundle_path, 'rb') as f:
            signature = _read_cstring(f)
            if signature != b'UnityFS':
                return None

            version = struct.unpack(">I", f.read(4))[0]
            _version_player = _read_cstring(f)
            version_engine = _read_cstring(f)
            size = struct.unpack(">q", f.read(8))[0]
            compressed_size, uncompressed_size, flags_value = struct.unpack(">III", f.read(12))

            # 与 UnityPy read_fs 一致：按引擎版本区分新旧 flags 语义
            engine_version = _parse_engine_version(version_engine)
            use_old_flags = (
                engine_version < (2020,)
                or (engine_version[0] == 2020 and engine_version < (2020, 3, 34))
                or (engine_version[0] == 2021 and engine_version < (2021, 3, 2))
                or (engine_version[0] == 2022 and engine_version < (2022, 1, 1))
            )
            flags: ArchiveFlagsOld | ArchiveFlags = ArchiveFlagsOld(flags_value) if use_old_flags else ArchiveFlags(flags_value)

            # 加密包无法离线解析 blockinfo
            if flags & flags.UsesAssetBundleEncryption:
                return None

            if flags & ArchiveFlags.BlocksInfoAtTheEnd:
                # 定位以头部 size 字段为准，避开 mod 产物尾部的 CRC 修正字节
                f.seek(size - compressed_size)
            else:
                # 头部版本 7+（及 2019.4.15+）的 blockinfo 起 16 字节对齐
                if version >= 7 or engine_version >= (2019, 4, 15):
                    f.seek((f.tell() + 15) & ~15)
            blocks_info = f.read(compressed_size)

        compression = flags_value & ArchiveFlags.CompressionTypeMask
        if compression == 0:
            data = blocks_info
        elif compression == 1:
            data = CompressionHelper.decompress_lzma(blocks_info, True)
        elif compression in (2, 3):  # lz4 / lz4hc
            data = CompressionHelper.decompress_lz4(blocks_info, uncompressed_size)
        else:
            return None

        # blockinfo 布局：hash(16B) + 块表（每条 u32+u32+u16=10B）+ 节点表（{offset: i64, size: i64, flags: u32, name: cstring}）
        pos = 16
        blocks_count = struct.unpack_from(">i", data, pos)[0]
        pos += 4 + blocks_count * 10
        nodes_count = struct.unpack_from(">i", data, pos)[0]
        pos += 4
        names: set[str] = set()
        for _ in range(nodes_count):
            pos += 20  # offset + size + flags
            end = data.index(b'\x00', pos)
            names.add(data[pos:end].decode("utf-8", "replace"))
            pos = end + 1
        return names

    except Exception:
        return None
