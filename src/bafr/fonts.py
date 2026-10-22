# fonts.py
"""
核心业务：BundleFonts 语言映射解析与 legacy Font 资产替换。
"""

import re
from dataclasses import dataclass
from pathlib import Path

from .bundle import Bundle
from .naming import parse_filename
from .searching import find_bundles_by_prefix, find_cab_bundles, get_search_dirs
from .utils import LogFunc, compute_crc32, no_log

# ui-font bundle 的文件名前缀（MX 框架语言字体映射所在包）
UI_FONT_PREFIX = "ui-font-_mxload-"

# externals 路径形如 archive:/CAB-xxx/CAB-xxx，提取中间的 SerializedFile 名
_CAB_PATTERN = re.compile(r"archive:/([^/]+)/")

# 字形缓存字段（不同包版本字段名不同，按存在性清空）
_CHAR_CACHE_FIELDS = ("m_CharacterRects", "m_CharacterInfo")

# sfnt 字体文件魔数（OTTO=otf，0x00010000=ttf）
_SFNT_MAGICS = (b"OTTO", b"\x00\x01\x00\x00")


@dataclass(frozen=True)
class FontPtr:
    """BundleFonts 中单个字重条目的 PPtr 解析结果"""
    weight: str            # "Normal" / "Bold"
    path_id: int           # 目标 Font 对象的 m_PathID
    cab: str | None        # 目标 SerializedFile 名；None 表示同包引用（fileID=0）


@dataclass(frozen=True)
class LangMapping:
    """单个 ui-font bundle 解析出的语言映射"""
    lang: str                     # 语言代码（如 "tw"，取自 GameObject 名 BundleFontTw）
    ui_font_bundle: Path          # 来源 ui-font bundle 路径
    fonts: dict[str, FontPtr]     # {weight: FontPtr}


@dataclass(frozen=True)
class FontRef:
    """已定位到物理 bundle 的 Font 引用"""
    lang: str
    weight: str
    font_name: str        # Font 资产名（如 NotoSansTC-Medium）
    path_id: int
    bundle_path: Path     # 物理 bundle 路径


@dataclass(frozen=True)
class ReplaceTarget:
    """单个 Font 资产的替换内容"""
    font_name: str        # Font 资产名（BundleFonts 引用的名字，如 NotoSansTC-Medium）
    font_data: bytes      # 新字体文件字节
    family_name: str      # 写入 m_FontNames 的家族名（如 "Source Han Sans SC Medium"）


@dataclass
class ReplaceReport:
    """单个 bundle 的替换结果报告（verify_ok 由自检步骤回填，故不可 frozen）"""
    source_path: Path
    output_path: Path
    replaced: tuple[str, ...]        # 实际替换的 Font 资产名
    crc_target: int | None
    crc_actual: int | None
    verify_ok: bool


# -------- BundleFonts 解析 --------

def _find_object(bundle: Bundle, path_id: int, type_name: str):
    """在 bundle 内按 path_id 与类型名查找对象（Bundle 内仅一个 SerializedFile）"""
    for obj in bundle.env.objects:
        if obj.path_id == path_id and obj.type.name == type_name:
            return obj
    return None


def _script_class_name(bundle: Bundle, obj) -> str | None:
    """解析 MonoBehaviour 的 MonoScript 类名（同包 fileID=0 场景）"""
    tree = obj.read_typetree()
    script = tree.get("m_Script") or {}
    if script.get("m_FileID", 0) != 0:
        return None
    script_obj = _find_object(bundle, script.get("m_PathID", 0), "MonoScript")
    if script_obj is None:
        return None
    return script_obj.read_typetree().get("m_ClassName")


def _pptr_to_cab(bundle: Bundle, pptr: dict) -> str | None:
    """把 PPtr 的 externals 引用解析为 CAB 名；同包引用（fileID=0）返回 None"""
    file_id = pptr.get("m_FileID", 0)
    if file_id <= 0:
        return None
    externals = bundle.env.assets[0].externals
    path = externals[file_id - 1].path
    match = _CAB_PATTERN.search(path)
    return match.group(1) if match else path


def parse_bundlefonts(bundle: Bundle) -> list[LangMapping]:
    """
    解析 ui-font bundle 内全部 BundleFonts MonoBehaviour 的语言映射。

    判定依据：m_Script 解析出 MonoScript 类名 "BundleFonts"；
    MonoScript 解析失败时兜底按 typetree 同时含 Normal/Bold 键判定。
    语言代码取 m_GameObject 关联 GameObject 的名字（BundleFontTw → "tw"）。
    """
    mappings: list[LangMapping] = []
    for obj in bundle.env.objects:
        if obj.type.name != "MonoBehaviour":
            continue
        tree = obj.read_typetree()
        if "Normal" not in tree or "Bold" not in tree:
            continue
        class_name = _script_class_name(bundle, obj)
        if class_name is not None and class_name != "BundleFonts":
            continue

        # 语言名来自 m_GameObject 关联的 GameObject
        lang = ""
        go = tree.get("m_GameObject") or {}
        if go.get("m_FileID", 0) == 0:
            go_obj = _find_object(bundle, go.get("m_PathID", 0), "GameObject")
            if go_obj is not None:
                lang = go_obj.read_typetree().get("m_Name", "").removeprefix("BundleFont").lower()

        fonts: dict[str, FontPtr] = {}
        for weight in ("Normal", "Bold"):
            pptr = tree.get(weight) or {}
            fonts[weight] = FontPtr(
                weight=weight,
                path_id=pptr.get("m_PathID", 0),
                cab=_pptr_to_cab(bundle, pptr),
            )

        mappings.append(LangMapping(lang=lang, ui_font_bundle=bundle.path, fonts=fonts))
    return mappings


def find_ui_font_bundles(search_dirs: list[Path], log: LogFunc = no_log) -> list[Path]:
    """按文件名前缀定位全部 ui-font bundle（可能多版本，全列出）。"""
    return find_bundles_by_prefix(UI_FONT_PREFIX, search_dirs, log)


def pick_latest_ui_font_bundle(bundles: list[Path]) -> Path | None:
    """多版本 ui-font bundle 时按文件名日期取最新；均无日期时取最后一个。"""
    if not bundles:
        return None
    return max(bundles, key=lambda p: parse_filename(p.name).date)


def resolve_lang_mapping(
    search_dirs: list[Path],
    lang: str,
    log: LogFunc = no_log,
    ui_font_bundle: Path | None = None,
) -> tuple[LangMapping | None, Path | None]:
    """
    定位指定语言的 BundleFonts 映射。

    Args:
        search_dirs: 资源搜索目录列表
        lang: 语言代码（大小写不敏感，如 "tw"）
        log: 日志记录函数
        ui_font_bundle: 显式指定的 ui-font bundle 路径；为 None 时自动选最新版本

    Returns:
        (语言映射, 所用 ui-font bundle 路径)；未找到时返回 (None, None)
    """
    bundles = [ui_font_bundle] if ui_font_bundle else find_ui_font_bundles(search_dirs, log)
    if not ui_font_bundle:
        chosen = pick_latest_ui_font_bundle(bundles)
        if chosen is None:
            log(f"❌ No ui-font bundle found with prefix '{UI_FONT_PREFIX}'.")
            return None, None
        bundles = [chosen]
        log(f"  > Using ui-font bundle: {chosen.name}")
    else:
        log(f"  > Using ui-font bundle: {ui_font_bundle.name}")

    lang_lower = lang.lower()
    for bundle_path in bundles:
        bundle = Bundle.load(bundle_path, log)
        if bundle is None:
            continue
        for mapping in parse_bundlefonts(bundle):
            if mapping.lang == lang_lower:
                return mapping, bundle_path
    log(f"❌ Language '{lang}' not found in BundleFonts mappings.")
    return None, None


def resolve_font_refs(
    mappings: list[LangMapping],
    search_dirs: list[Path],
    log: LogFunc = no_log,
    max_bundle_size: int = 64 * 1024 * 1024,
    cache_path: Path | None = None,
) -> list[FontRef]:
    """
    把映射中的 PPtr 解析为物理 bundle 内的 Font 资产引用。

    在 Preload/Windows + GameData/Windows 全部 bundle 中按 CAB 名搜索
    （externals 跨目录是常态，轻量头部解析 + 可选缓存），再按 m_PathID
    定位 Font 对象读取资产名。
    """
    # 收集全部跨包 CAB 引用
    target_cabs = {ptr.cab for m in mappings for ptr in m.fonts.values() if ptr.cab}
    cab_map = (find_cab_bundles(target_cabs, search_dirs, log, max_bundle_size, cache_path)
               if target_cabs else {})

    # 同包引用的 Font 与 BundleFonts 同 bundle（ui-font 包内）
    loaded: dict[Path, Bundle] = {}

    def locate(bundle_path: Path, path_id: int) -> str:
        bundle = loaded.get(bundle_path)
        if bundle is None:
            bundle = Bundle.load(bundle_path, log)
            if bundle is None:
                return ""
            loaded[bundle_path] = bundle
        obj = _find_object(bundle, path_id, "Font")
        if obj is None:
            return ""
        return obj.read_typetree().get("m_Name", "")

    refs: list[FontRef] = []
    for mapping in mappings:
        for ptr in mapping.fonts.values():
            bundle_path = cab_map.get(ptr.cab) if ptr.cab else mapping.ui_font_bundle
            if bundle_path is None:
                log(f"  > ⚠️ Unresolved font reference: {mapping.lang}/{ptr.weight} (CAB {ptr.cab})")
                continue
            font_name = locate(bundle_path, ptr.path_id)
            if not font_name:
                log(f"  > ⚠️ Font object not found: {mapping.lang}/{ptr.weight} "
                    f"(path_id={ptr.path_id} in {bundle_path.name})")
                continue
            refs.append(FontRef(
                lang=mapping.lang,
                weight=ptr.weight,
                font_name=font_name,
                path_id=ptr.path_id,
                bundle_path=bundle_path,
            ))
            log(f"  > {mapping.lang:<4} {ptr.weight:<7} {font_name} <- {bundle_path.name}")
    return refs


# -------- Font 替换 --------

def validate_font_file(data: bytes) -> str | None:
    """校验字体文件字节头为 sfnt（otf/ttf），返回错误消息；合法返回 None。"""
    if len(data) < 4:
        return "Font file is too small."
    if not any(data.startswith(magic) for magic in _SFNT_MAGICS):
        return "Not a valid sfnt font file (expected OTTO otf or 0x00010000 ttf head)."
    return None


def replace_fonts_in_bundle(
    bundle_path: Path,
    targets: dict[str, ReplaceTarget],
    output_path: Path,
    perform_crc: bool = True,
    log: LogFunc = no_log,
) -> ReplaceReport:
    """
    替换 bundle 内指定名字的 legacy Font 资产并保存输出。

    typetree 改法：换 m_FontData、m_FontNames，清字形缓存字段
    （m_CharacterRects / m_CharacterInfo 按字段存在性自适应），
    其余度量字段不动（原字体与替换字体度量一致时零布局风险）。
    """
    bundle = Bundle.load(bundle_path, log)
    if bundle is None:
        return ReplaceReport(bundle_path, output_path, (), None, None, False)

    replaced: list[str] = []
    for obj in bundle.env.objects:
        if obj.type.name != "Font":
            continue
        tree = obj.read_typetree()
        name = tree.get("m_Name")
        if name not in targets:
            continue
        target = targets[name]
        tree["m_FontData"] = target.font_data
        tree["m_FontNames"] = [target.family_name]
        for field in _CHAR_CACHE_FIELDS:
            if field in tree:
                tree[field] = []
        obj.save_typetree(tree)
        replaced.append(name)
        log(f"  ✅ Replaced Font '{name}' <- {len(target.font_data)} bytes "
            f"(family: {target.family_name})")

    missing = set(targets) - set(replaced)
    if missing:
        log(f"  > ⚠️ Font asset(s) not found in bundle: {', '.join(sorted(missing))}")

    ok, message = bundle.save(output_path, perform_crc=perform_crc)
    if not ok:
        log(f"  ❌ {message}")
        return ReplaceReport(bundle_path, output_path, tuple(replaced), None, None, False)

    crc_target = int(parse_filename(output_path.name).crc) if parse_filename(output_path.name).crc else None
    crc_actual = compute_crc32(output_path)
    return ReplaceReport(
        source_path=bundle_path,
        output_path=output_path,
        replaced=tuple(replaced),
        crc_target=crc_target,
        crc_actual=crc_actual,
        verify_ok=False,  # 由 verify_replaced_bundle 填充
    )


def verify_replaced_bundle(report: ReplaceReport, targets: dict[str, ReplaceTarget], log: LogFunc = no_log) -> bool:
    """
    重载产物自检：Font 数据头部/长度一致、CRC 等于文件名值。
    自检通过时原地更新 report.verify_ok 并返回 True。
    """
    ok = True
    bundle = Bundle.load(report.output_path, log)
    if bundle is None:
        return False
    for obj in bundle.env.objects:
        if obj.type.name != "Font":
            continue
        tree = obj.read_typetree()
        name = tree.get("m_Name")
        target = targets.get(name)
        if target is None:
            continue
        data = tree.get("m_FontData", b"")
        data_ok = bytes(data) == target.font_data
        names_ok = tree.get("m_FontNames") == [target.family_name]
        log(f"  > verify Font '{name}': data={len(data)}B "
            f"head={bytes(data[:4])!r} data_ok={data_ok} names_ok={names_ok}")
        ok = ok and data_ok and names_ok
    crc_ok = report.crc_target is None or report.crc_actual == report.crc_target
    log(f"  > verify CRC: actual={report.crc_actual:#010x} target={report.crc_target:#010x} ok={crc_ok}")
    ok = ok and crc_ok
    report.verify_ok = ok
    return ok


# -------- 高层编排（供 CLI 调用） --------

def scan_game_fonts(
    game_dir: Path,
    log: LogFunc = no_log,
    max_bundle_size: int = 64 * 1024 * 1024,
    cache_path: Path | None = None,
) -> list[FontRef]:
    """扫描游戏资源目录，输出全部语言的字体映射清单。"""
    search_dirs = get_search_dirs(game_dir)
    if not search_dirs:
        log(f"❌ No resource directories found under '{game_dir}'.")
        return []

    bundles = find_ui_font_bundles(search_dirs, log)
    if not bundles:
        return []

    mappings: list[LangMapping] = []
    for bundle_path in bundles:
        bundle = Bundle.load(bundle_path, log)
        if bundle is None:
            continue
        mappings.extend(parse_bundlefonts(bundle))

    return resolve_font_refs(mappings, search_dirs, log, max_bundle_size, cache_path)


def replace_lang_fonts(
    game_dir: Path,
    lang: str,
    normal_path: Path,
    bold_path: Path,
    output_dir: Path,
    log: LogFunc = no_log,
    family: str = "Source Han Sans SC",
    perform_crc: bool = True,
    max_bundle_size: int = 64 * 1024 * 1024,
    ui_font_bundle: Path | None = None,
    cache_path: Path | None = None,
) -> list[ReplaceReport]:
    """
    替换指定语言的 UI 字体并输出产物 bundle。

    流程：定位 ui-font bundle → 解析语言映射 → CAB 定位物理 bundle →
    按资产名分组替换 → 保存 + CRC 修正 → 重载自检。

    Args:
        game_dir: 游戏资源根目录
        lang: 语言代码（如 "tw"）
        normal_path: Normal 字重的新字体文件（otf/ttf）
        bold_path: Bold 字重的新字体文件（otf/ttf）
        output_dir: 产物输出目录
        log: 日志记录函数
        family: 字体家族名基础（写入 m_FontNames，权重后缀自动追加）
        perform_crc: 是否执行 CRC 修正
        max_bundle_size: CAB 搜索时单个 bundle 的大小上限
        ui_font_bundle: 显式指定 ui-font bundle（缺省自动选最新版本）
        cache_path: CAB 映射缓存文件路径；None 表示不使用缓存

    Returns:
        每个 involved bundle 的 ReplaceReport 列表
    """
    search_dirs = get_search_dirs(game_dir)
    if not search_dirs:
        log(f"❌ No resource directories found under '{game_dir}'.")
        return []

    mapping, _ = resolve_lang_mapping(search_dirs, lang, log, ui_font_bundle)
    if mapping is None:
        return []

    # 读入并校验用户字体
    font_files: dict[str, Path] = {}
    for weight, path in (("Normal", normal_path), ("Bold", bold_path)):
        if not path.is_file():
            log(f"❌ Font file not found: {path}")
            return []
        font_files[weight] = path

    refs = resolve_font_refs([mapping], search_dirs, log, max_bundle_size, cache_path)
    if not refs:
        return []

    # 按 (bundle, font_name) 聚合替换目标
    targets_by_bundle: dict[Path, dict[str, ReplaceTarget]] = {}
    for ref in refs:
        weight = ref.weight
        if weight not in font_files:
            log(f"  > ⚠️ No input font for weight '{weight}', skipping {ref.font_name}.")
            continue
        data = font_files[weight].read_bytes()
        error = validate_font_file(data)
        if error:
            log(f"❌ Invalid font file '{font_files[weight].name}': {error}")
            return []
        # 家族名：基础名 + 资产名字重后缀（如 NotoSansTC-Medium → "Source Han Sans SC Medium"）
        weight_suffix = ref.font_name.rsplit("-", 1)[-1].title() if "-" in ref.font_name else weight
        target = ReplaceTarget(
            font_name=ref.font_name,
            font_data=data,
            family_name=f"{family} {weight_suffix}",
        )
        bundle_targets = targets_by_bundle.setdefault(ref.bundle_path, {})
        existing = bundle_targets.get(ref.font_name)
        if existing is not None and existing.font_data != target.font_data:
            # 多字重共用一个 Font 资产但输入不同（如 th 的 Normal/Bold 同指 RSU_BOLD）
            log(f"  > ⚠️ Font '{ref.font_name}' is referenced by multiple weights with different "
                f"input fonts; using the '{weight}' input.")
        bundle_targets[ref.font_name] = target

    output_dir.mkdir(parents=True, exist_ok=True)
    reports: list[ReplaceReport] = []
    for bundle_path, targets in targets_by_bundle.items():
        log(f"Processing bundle: {bundle_path.name}")
        output_path = output_dir / bundle_path.name
        report = replace_fonts_in_bundle(bundle_path, targets, output_path, perform_crc, log)
        if report.replaced:
            report.verify_ok = verify_replaced_bundle(report, targets, log)
        reports.append(report)
    return reports
