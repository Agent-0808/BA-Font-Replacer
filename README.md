<div align="center" style="text-align:center">
  <h1>BA-Font-Replacer</h1>
  <p>
    <a href="https://www.gnu.org/licenses/gpl-3.0"><img alt="License: GPLv3" src="https://img.shields.io/badge/License-GPL--3.0-orange.svg"></a>
    <img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-blue.svg">
    <img alt="UnityPy" src="https://img.shields.io/badge/UnityPy-1.23%2B-green.svg">
  </p>
</div>

# BA Font Replacer

[简体中文](README.zh-CN.md) | English

A small UnityPy-based CLI tool for replacing UI fonts (legacy `Font` assets) per language in Blue Archive, producing bundle files that can be copied directly into the game directory.

Supports the Steam Global and JP servers on Windows, auto-detecting the game path from the registry, or you can specify the path manually.

`scan` only reports the current font mappings per language; `replace` performs the actual replacement. No manual bundle handling required.

Supported languages:
- en (English)
- kr (한국어/Korean)
- tw (繁體中文/Traditional Chinese)
- th (ไทย/Thai).

## Requirements

- Windows 10 or later (game path auto-detection relies on the Windows registry)
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) (recommended)

## Installation

```bash
git clone https://github.com/Agent-0808/BA-Font-Replacer.git
cd BA-Font-Replacer

# Install dependencies and create the virtual environment
uv sync
```

After installation, run it via `uv run bafr`, or activate the virtual environment and use `bafr` directly.

## Usage

### `scan`: list font mappings (read-only)

Scans the game resources and lists which font assets each language currently references. **This command only queries; it never modifies any file.**

```bash
# Auto-detect the game path from the registry
uv run bafr scan

# Specify the game directory manually
uv run bafr scan --game-path "D:\SteamLibrary\steamapps\common\BlueArchive"
```

Example output (bundle names abbreviated; see [Current Font Mappings](#current-font-mappings-steam-global) for the full list):

```
Font mappings (8):
lang   weight   font_name                    bundle
th     Normal   RSU_BOLD                     <- ...-2025-03-11_assets_all_3487395783.bundle
th     Bold     RSU_BOLD                     <- ...-2025-03-11_assets_all_3487395783.bundle
en     Normal   NotoSans-Regular             <- ...-2025-03-11_assets_all_3487395783.bundle
en     Bold     NotoSans-Bold                <- ...-2025-03-11_assets_all_3487395783.bundle
kr     Normal   MainFont                     <- ...-2024-11-18_assets_all_2386780975.bundle
kr     Bold     MainFont_Bold                <- ...-2024-11-18_assets_all_2386780975.bundle
tw     Normal   NotoSansTC-Medium            <- ...-2026-03-13_assets_all_842690403.bundle
tw     Bold     NotoSansTC-Bold              <- ...-2026-03-13_assets_all_842690403.bundle
```

### `replace`: replace fonts for a language

```bash
# Traditional Chinese: Source Han Sans TC -> Source Han Sans SC
uv run bafr replace tw "C:\Windows\Fonts\SourceHanSansSC-Medium.otf" "C:\Windows\Fonts\SourceHanSansSC-Bold.otf"

# English: switch to Segoe UI (preinstalled on Windows)
uv run bafr replace en "C:\Windows\Fonts\segoeui.ttf" "C:\Windows\Fonts\segoeuib.ttf"

# Use a single font file for both weights
uv run bafr replace th myfont.otf

# Custom output directory
uv run bafr replace kr a.otf b.otf --output-dir "D:\out"
```

Arguments:

| Argument | Description |
| --- | --- |
| `lang` | Language code (`tw` / `en` / `kr` / `th`, etc.), as shown by `scan`; case-insensitive |
| `normal` | `.otf` / `.ttf` font file for the Normal weight |
| `bold` | Font file for the Bold weight; falls back to `normal` if omitted |
| `--output-dir` | Output directory, defaults to `./output/` |
| `--family` | Font family name written into `m_FontNames`, defaults to `Source Han Sans SC` (weight suffix is appended) |
| `--game-path` | Game install directory; auto-detected from the registry if omitted |
| `--region` | Server: `auto` / `global` / `japan`, defaults to `auto` (Global first, then JP) |
| `--ui-font` | Explicit path to the `ui-font` bundle; the latest version is picked automatically if omitted |
| `--no-crc` | Skip the CRC fix (enabled by default) |
| `--no-cache` | Ignore the CAB mapping cache and rescan everything each time |
| `--max-bundle-size-mb` | Size limit for bundles skipped during the CAB search, defaults to 64 MB |

On success, the tool prints the output paths, the replaced Font asset names, the target / actual CRC values, and the self-check result:

```
Bundle: prologdepengroup-assets-_mx-uis-_mxcommon-_mxprolog-2026-03-13_assets_all_842690403.bundle
  Replaced fonts: NotoSansTC-Medium, NotoSansTC-Bold
  Output: D:\...\output\prologdepengroup-..._842690403.bundle
  CRC: actual=0x323c5563 target=0x323c5563
  Verify: OK
```

## Workflow

1. Run `bafr scan` to confirm the font mapping and bundle filename for your target language.
2. Run `bafr replace <lang> <normal.otf> [bold.otf]`; the output is written to `--output-dir`.
3. **Back up** the original bundle file(s) with the same name in the game directory.
4. Overwrite the original file(s) with the generated ones (usually under `BlueArchive_Data/StreamingAssets/PUB/Resource/Preload/Windows/`).
5. Launch the game to verify; to roll back, restore the backups from step 3.

> [!WARNING]
> Always back up the original files first. The tool only generates output files; it never modifies the game directory on its own.

## Current Font Mappings (Steam Global)

> [!NOTE]
> The following reflects the Steam Global build at the time of testing. Mappings may change after game updates; always trust the actual output of `bafr scan`.

| Language | Normal | Bold | Bundle |
| --- | --- | --- | --- |
| th | `RSU_BOLD` | `RSU_BOLD` | `...-2025-03-11_assets_all_3487395783.bundle` |
| en | `NotoSans-Regular` | `NotoSans-Bold` | `...-2025-03-11_assets_all_3487395783.bundle` |
| kr | `MainFont` | `MainFont_Bold` | `...-2024-11-18_assets_all_2386780975.bundle` |
| tw | `NotoSansTC-Medium` | `NotoSansTC-Bold` | `...-2026-03-13_assets_all_842690403.bundle` |

Bundle names in the table omit the common prefix `prologdepengroup-assets-_mx-uis-_mxcommon-_mxprolog`; all of these files live under `Preload/Windows`.

## How It Works

See the [reverse-engineering report](docs/2026-10-22_BA%E5%9B%BD%E9%99%85%E6%9C%8DUI%E5%AD%97%E4%BD%93%E6%B8%B2%E6%9F%93%E9%93%BE%E9%80%86%E5%90%91%E6%8A%A5%E5%91%8A.md) (Chinese) for the full analysis. Core steps:

1. **Locate the language mapping**: find the MX framework's `BundleFonts` MonoBehaviour inside `Preload/Windows/ui-font-_mxload-*.bundle`, derive the language code from the linked GameObject name (`BundleFontTw`), and read its `Normal` / `Bold` PPtrs. Languages are enumerated dynamically, not hard-coded.
2. **Locate the physical bundle**: PPtr external references are indexed by SerializedFile name (`CAB-xxx`), so all bundles under `GameData/Windows` and `Preload/Windows` must be searched. The search uses a lightweight UnityFS header parser that reads only the blockinfo without decompressing data blocks, scanning prolog-prefixed bundles first; results are cached by path + size + mtime, and the cache invalidates and rescans automatically after a game update.
3. **Replace the Font assets**: swap `m_FontData` and `m_FontNames` in the UnityPy typetree, clear the glyph cache fields (`m_CharacterRects` / `m_CharacterInfo`, whichever exists), and leave all other font metrics untouched.
4. **Fix the CRC**: the client self-verifies against the CRC32 suffix in the filename, so a 4-byte correction tail is appended after saving to make the whole-file CRC equal the value in the filename.
5. **Verify the output**: reload the generated bundle and check the font data, family name, and CRC; all must pass for success.

## Code Reuse & Credits

This project **reuses and adapts parts of the source code of [BA-Modding-Toolkit](https://github.com/Agent-0808/BA-Modding-Toolkit)** for locating bundles, bundle handling, and CRC fixing.
BAMT is licensed under GPL-3.0; since this project reuses its code, it is distributed under GPL-3.0 as well.

Other dependencies:

- [UnityPy](https://github.com/K0lb3/UnityPy) (MIT License): Unity bundle parsing and manipulation
- [Tap](https://github.com/swansonk14/typed-argument-parser) (MIT License): CLI argument parsing
- [pytest](https://pytest.org/) (MIT License): testing framework

## Development

```bash
# Run tests
uv run pytest

# Show help
uv run bafr --help
uv run bafr scan --help
uv run bafr replace --help
```

### Project Structure

```
BA-Font-Replacer/
├── src/bafr/
│ ├── __init__.py
│ ├── cli.py         # CLI entry point (scan / replace)
│ ├── fonts.py       # Core logic: BundleFonts parsing, Font replacement, verification
│ ├── bundle.py      # Bundle wrapper, lightweight CAB name parsing
│ ├── naming.py      # Bundle filename parsing
│ ├── searching.py   # Resource directory search, CAB lookup, cache
│ ├── paths.py       # Game path detection
│ └── utils/
│   ├── common.py    # Logging types
│   └── crc.py       # CRC32 calculation and CRC fix
├── tests/           # pytest tests (with original / modified bundle fixtures)
├── docs/            # Reverse-engineering report and other docs
├── pyproject.toml
├── LICENSE
├── README.zh-CN.md  # Chinese README
└── README.md        # English README (this file)
```

## Disclaimer

<sub>
BA-Font-Replacer is a personal project and is not affiliated with, endorsed by, or connected to NEXON Games Co., Ltd., NEXON Korea Corp., Yostar, Inc., or any of their subsidiaries. All game assets, characters, music, and related intellectual property are the trademarks or registered trademarks of their respective owners. They are used in this tool for educational and interoperability purposes only (fair use). Please respect the Terms of Service of the official game. Do not use this tool for cheating or malicious activities.
</sub>
