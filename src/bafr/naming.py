# naming.py
"""
Parsing BA bundle filenames.
Adapted from [BA-Modding-Toolkit](https://github.com/Agent-0808/BA-Modding-Toolkit)
"""

import re
from typing import NamedTuple

# -------- 文件名解析常量 --------

PRELOAD_PREFIX = [
    "prologgroup-",
    "prologdepengroup-"
]

FIXED_PREFIX = [
    "assets-_mx-",
]

# 日服版额外的资源类型后缀
RESOURCE_TYPES_TEXT = {
    'textures', 'textassets', 'meshes', 'materials',
    'assets', 'animationclips', 'audio', 'prefabs', 'timelines'
}

# -------- 预编译正则（避免 per-call 编译开销）--------
_RE_DATE = re.compile(r'(\d{4}-\d{2}-\d{2})')
_RE_MX = re.compile(r'[-_](?:mxdependency|mxload|mxprolog)')


class ParsedFilename(NamedTuple):
    """
    解析后的文件名结构。

    Attributes:
        category: 资源分类 (如 spinecharacters)，可能为 None
        core:     核心名称 (如 ch0808_spr)，必须有值
        res_type: 资源类型 (如 textassets)，可能为 None
        date:     日期字符串 (YYYY-MM-DD)
        crc:      CRC32 校验码
        prefix:   用于搜索同组文件的前缀
    """
    category: str | None
    core: str
    res_type: str | None
    date: str
    crc: str
    prefix: str


def parse_filename(filename: str) -> ParsedFilename:
    """
    解析文件名，提取各个组成部分。

    Args:
        filename: 文件名字符串

    Returns:
        ParsedFilename: 包含所有解析字段的命名元组
    """
    # 1. 提取 CRC（从右向左切片）
    crc = ""
    stem = filename.rsplit('.', 1)[0]
    crc_idx = stem.rfind('_')
    if crc_idx != -1:
        candidate_crc = stem[crc_idx + 1:]
        if candidate_crc.isdigit():
            crc = candidate_crc

    # 2. 定位 Date 中轴
    match_date = _RE_DATE.search(filename)
    if not match_date:
        # 无日期情况（如 .skel / .png 散件素材）
        core_part = stem
        for p in PRELOAD_PREFIX:
            if core_part.startswith(p):
                core_part = core_part[len(p):]
                break
        for p in FIXED_PREFIX:
            if core_part.startswith(p):
                core_part = core_part[len(p):]
                break
        core = core_part.strip('-_')
        category = None
        if '-' in core:
            category, core = core.split('-', 1)
        return ParsedFilename(category=category, core=core, res_type=None, date="", crc=crc, prefix="")

    date = match_date.group(1)
    date_start = match_date.start()
    date_end = date_start + 10  # YYYY-MM-DD 固定长 10

    before_date = filename[:date_start]
    after_date = filename[date_end:]

    # 3. 基于“中轴两翼”判定 res_type 与 prefix
    res_type = None
    prefix = before_date

    # 3.1 检查左邻居：JP 格式 (res_type 在 date 之前，如 -textures-2024-...)
    left_token = before_date.rstrip('-_').rsplit('-', 1)[-1].lower()
    if left_token in RESOURCE_TYPES_TEXT:
        res_type = left_token
        before_clean = before_date.removesuffix('-')
        prefix = before_clean.removesuffix(f"-{res_type}") + '-'

    # 3.2 检查右邻居：Modern 格式 (res_type 在 date 之后，如 _002_)
    elif len(after_date) >= 5 and after_date[0] == '_' and after_date[4] == '_':
        right_token = after_date[1:4]
        if right_token.isdigit():
            res_type = right_token

    # 4. 提取 Core 与 Category
    # 截掉 mx 依赖标记
    match_mx = _RE_MX.search(prefix)
    if match_mx:
        core_part = prefix[:match_mx.start()]
    else:
        core_part = prefix.rstrip('-_')

    # 双重前缀需分两轮独立剥离
    # 第一轮：剥离 Preload 前缀 (prologdepengroup-)
    for p in PRELOAD_PREFIX:
        if core_part.startswith(p):
            core_part = core_part[len(p):]
            break
    # 第二轮：剥离 Fixed 前缀 (assets-_mx-)
    for p in FIXED_PREFIX:
        if core_part.startswith(p):
            core_part = core_part[len(p):]
            break

    core = core_part.strip('-_')
    category = None
    if '-' in core:
        category, core = core.split('-', 1)

    return ParsedFilename(
        category=category,
        core=core,
        res_type=res_type,
        date=date,
        crc=crc,
        prefix=prefix
    )
