# cli.py
"""
BAFR 命令行入口。

用法：
  bafr scan    [--game-path PATH]
  bafr replace --lang tw --normal X.otf --bold Y.otf [--output-dir work]
"""

from argparse import RawTextHelpFormatter
from pathlib import Path

from tap import Tap

from .fonts import (
    FontRef,
    ReplaceReport,
    replace_lang_fonts,
    scan_game_fonts,
)
from .paths import BARegion, DEFAULT_CACHE_PATH, resolve_game_dir


class BaseTap(Tap):
    """基础Tap类，提供共享配置。"""

    def configure(self) -> None:
        self.description = "BAFR - Blue Archive font replacer."
        self.formatter_class = RawTextHelpFormatter
        self._underscores_to_dashes = True


class ScanTap(BaseTap):
    """Scan命令：枚举 BundleFonts 语言映射清单。"""

    game_path: Path | None = None  # Game install path. Auto-detected from the registry if omitted.
    region: BARegion = 'auto'  # Game region used to auto-detect the install path (auto = global first, then japan).
    max_bundle_size_mb: int = 64  # Skip bundles larger than this (MB) when searching for CAB targets.
    no_cache: bool = False  # Disable the CAB-to-bundle mapping cache (rescan every time).

    def configure(self) -> None:
        super().configure()
        self.description = '''Scan game resources and list the BundleFonts language mappings.

Examples:
  # Auto-detect game path from the registry
  bafr scan

  # Explicit game path
  bafr scan --game-path "D:\\SteamLibrary\\steamapps\\common\\BlueArchive"
'''


class ReplaceTap(BaseTap):
    """Replace命令：替换指定语言的 UI 字体并输出产物 bundle。"""

    lang: str  # Language code to replace (e.g. "tw"), as shown by the scan command.
    normal: Path  # Path to the .otf/.ttf font file for the Normal weight.
    bold: Path  # Path to the .otf/.ttf font file for the Bold weight.
    output_dir: Path = Path('./work/')  # Directory to save the modified bundle file(s).
    game_path: Path | None = None  # Game install path. Auto-detected from the registry if omitted.
    region: BARegion = 'auto'  # Game region used to auto-detect the install path (auto = global first, then japan).
    family: str = "Source Han Sans SC"  # Font family name written into the Font assets (weight suffix is appended).
    ui_font: Path | None = None  # Explicit path to the ui-font bundle. Latest version is picked automatically if omitted.
    no_crc: bool = False  # Disable CRC fix function.
    no_cache: bool = False  # Disable the CAB-to-bundle mapping cache (rescan every time).
    max_bundle_size_mb: int = 64  # Skip bundles larger than this (MB) when searching for CAB targets.

    def configure(self) -> None:
        super().configure()
        self.description = '''Replace UI font assets (legacy Font path) for a language and output modified bundles.

Examples:
  # Replace the tw (Traditional Chinese) fonts with Source Han Sans SC
  bafr replace --lang tw \\
      --normal "C:\\Windows\\Fonts\\SourceHanSansSC-Medium.otf" \\
      --bold "C:\\Windows\\Fonts\\SourceHanSansSC-Bold.otf"

  # Custom output directory
  bafr replace --lang tw --normal a.otf --bold b.otf --output-dir "D:\\out"
'''


class MainTap(BaseTap):
    """主Tap类，包含所有子命令。"""

    def configure(self) -> None:
        super().configure()
        self.add_subparsers(dest='command', help='Available commands')
        self.add_subparser('scan', ScanTap, help='Scan game resources and list font language mappings.')
        self.add_subparser('replace', ReplaceTap, help='Replace UI font assets for a language.')


def _resolve_game_dir(game_path: Path | None, region: BARegion) -> Path | None:
    """解析游戏根目录并转换为资源目录（仅当目录本身不含资源后缀时原样返回）。"""
    resolved = resolve_game_dir(game_path, region)
    return resolved


def _cache_path(args: ScanTap | ReplaceTap) -> Path | None:
    """按 --no-cache 开关解析缓存文件路径"""
    return None if args.no_cache else DEFAULT_CACHE_PATH


def _print_ref(ref: FontRef) -> None:
    print(f"{ref.lang:<6} {ref.weight:<8} {ref.font_name:<28} <- {ref.bundle_path.name}")


def handle_scan(args: ScanTap) -> None:
    """处理 'scan' 命令的逻辑。"""
    print("--- BAFR Font Scan ---")
    game_dir = _resolve_game_dir(args.game_path, args.region)
    if game_dir is None or not game_dir.is_dir():
        print(f"❌ Game directory not found: {game_dir or '(auto-detect failed)'}")
        print("   Provide --game-path explicitly.")
        return

    print(f"Game directory: {game_dir}")
    refs = scan_game_fonts(game_dir, log=print, max_bundle_size=args.max_bundle_size_mb * 1024 * 1024,
                           cache_path=_cache_path(args))

    print("\n" + "=" * 50)
    if refs:
        print(f"Font mappings ({len(refs)}):")
        print(f"{'lang':<6} {'weight':<8} {'font_name':<28} bundle")
        for ref in refs:
            _print_ref(ref)
        print("\nUse `bafr replace --lang <lang> --normal <otf> --bold <otf>` to replace.")
    else:
        print("❌ No font mappings found.")
    print("=" * 50)


def handle_replace(args: ReplaceTap) -> None:
    """处理 'replace' 命令的逻辑。"""
    print("--- BAFR Font Replace ---")
    game_dir = _resolve_game_dir(args.game_path, args.region)
    if game_dir is None or not game_dir.is_dir():
        print(f"❌ Game directory not found: {game_dir or '(auto-detect failed)'}")
        print("   Provide --game-path explicitly.")
        return

    print(f"Game directory: {game_dir}")
    print(f"Language: {args.lang}")
    print(f"Normal font: {args.normal}")
    print(f"Bold font: {args.bold}")
    print(f"Output directory: {args.output_dir.resolve()}")

    reports: list[ReplaceReport] = replace_lang_fonts(
        game_dir=game_dir,
        lang=args.lang,
        normal_path=args.normal,
        bold_path=args.bold,
        output_dir=args.output_dir,
        log=print,
        family=args.family,
        perform_crc=not args.no_crc,
        max_bundle_size=args.max_bundle_size_mb * 1024 * 1024,
        ui_font_bundle=args.ui_font,
        cache_path=_cache_path(args),
    )

    print("\n" + "=" * 50)
    if not reports:
        print("❌ Replace failed: nothing processed.")
        return

    success = True
    for report in reports:
        print(f"Bundle: {report.output_path.name}")
        print(f"  Replaced fonts: {', '.join(report.replaced) or '(none)'}")
        print(f"  Output: {report.output_path}")
        if report.crc_target is not None:
            print(f"  CRC: actual={report.crc_actual:#010x} target={report.crc_target:#010x}")
        print(f"  Verify: {'OK' if report.verify_ok else 'FAILED'}")
        success = success and report.verify_ok and bool(report.replaced)

    if success:
        print(f"\n✅ Replace successful. Replace the file(s) in the game directory with the output in {args.output_dir.resolve()}")
    else:
        print("\n❌ Replace failed or verification did not pass. Check the log above.")
    print("=" * 50)


COMMAND_HANDLERS = {
    'scan': handle_scan,
    'replace': handle_replace,
}


def main() -> None:
    """主函数，用于解析命令行参数并分派任务。"""
    args = MainTap().parse_args()

    # Tap使用 dest 参数指定的属性名存储子命令名称
    command = getattr(args, 'command', None)
    if command in COMMAND_HANDLERS:
        COMMAND_HANDLERS[command](args)
    else:
        # 如果没有提供子命令，显示帮助信息
        MainTap().print_help()


if __name__ == "__main__":
    main()
