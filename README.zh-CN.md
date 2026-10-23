<div align="center" style="text-align:center">
  <h1>BA-Font-Replacer</h1>
  <p>
    <a href="https://www.gnu.org/licenses/gpl-3.0"><img alt="License: GPLv3" src="https://img.shields.io/badge/License-GPL--3.0-orange.svg"></a>
    <img alt="Python" src="https://img.shields.io/badge/Python-3.11%2B-blue.svg">
    <img alt="UnityPy" src="https://img.shields.io/badge/UnityPy-1.23%2B-green.svg">
  </p>
</div>

# BA Font Replacer

简体中文 | [English](README.md)

一个基于 UnityPy 的命令行小工具，用于替换 Blue Archive（碧蓝档案 / 蔚蓝档案）各语言的 UI 字体（legacy `Font` 资产），输出可直接覆盖进游戏目录的 bundle 文件。

支持 Windows 下的 Steam 国际服或日服，可自动从注册表探测游戏路径，也支持手动指定路径。

`scan` 仅查询当前各语言的字体映射，`replace` 执行实际替换，无需手动操作 bundle。

支持语言：
- en（English）
- kr（한국어/Korean）
- tw（繁體中文/Traditional Chinese）
- th（ไทย/Thai）。

## 环境要求

- Windows 10 及以上（游戏路径自动探测依赖 Windows 注册表）
- Python 3.11+
- [uv](https://github.com/astral-sh/uv)（推荐）

## 安装

```bash
git clone https://github.com/Agent-0808/BA-Font-Replacer.git
cd BA-Font-Replacer

# 安装依赖并创建虚拟环境
uv sync
```

安装后即可通过 `uv run bafr` 调用，或激活虚拟环境后直接使用 `bafr`。

## 功能说明

### `scan`：查询字体映射（只读）

扫描游戏资源，列出当前版本各语言的字体资产引用关系。**该命令只做查询，不会修改任何文件。**

```bash
# 自动从注册表探测游戏路径
uv run bafr scan

# 手动指定游戏目录
uv run bafr scan --game-path "D:\SteamLibrary\steamapps\common\BlueArchive"
```

输出示例（bundle 名已缩写，完整列表见[当前字体映射](#当前字体映射steam-国际服)）：

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

### `replace`：替换指定语言的字体

```bash
# 繁中：思源黑体 TC → 思源黑体 SC
uv run bafr replace tw "C:\Windows\Fonts\SourceHanSansSC-Medium.otf" "C:\Windows\Fonts\SourceHanSansSC-Bold.otf"

# 英文：换成 Windows 自带的 Segoe UI
uv run bafr replace en "C:\Windows\Fonts\segoeui.ttf" "C:\Windows\Fonts\segoeuib.ttf"

# 两个字重使用同一个字体文件
uv run bafr replace th myfont.otf

# 指定输出目录
uv run bafr replace kr a.otf b.otf --output-dir "D:\out"
```

参数说明：

| 参数 | 说明 |
| --- | --- |
| `lang` | 语言代码（`tw` / `en` / `kr` / `th` 等），以 `scan` 的输出为准，大小写不敏感 |
| `normal` | Normal 字重的 `.otf` / `.ttf` 字体文件 |
| `bold` | Bold 字重的字体文件，省略时使用 `normal` |
| `--output-dir` | 产物输出目录，默认 `./output/` |
| `--family` | 写入 `m_FontNames` 的字体家族名，默认 `Source Han Sans SC`（自动追加字重后缀） |
| `--game-path` | 游戏安装目录，省略时从注册表自动探测 |
| `--region` | 区服 `auto` / `global` / `japan`，默认 `auto`（先国际服，后日服） |
| `--ui-font` | 显式指定 `ui-font` bundle，省略时自动选择最新版本 |
| `--no-crc` | 跳过 CRC 修正（默认开启） |
| `--no-cache` | 不使用 CAB 映射缓存，每次都全量扫描 |
| `--max-bundle-size-mb` | CAB 搜索时跳过的单文件大小上限，默认 64 MB |

替换成功后，工具会输出产物路径、实际替换的 Font 资产名、CRC 目标值 / 实际值以及自检结果：

```
Bundle: prologdepengroup-assets-_mx-uis-_mxcommon-_mxprolog-2026-03-13_assets_all_842690403.bundle
  Replaced fonts: NotoSansTC-Medium, NotoSansTC-Bold
  Output: D:\...\output\prologdepengroup-..._842690403.bundle
  CRC: actual=0x323c5563 target=0x323c5563
  Verify: OK
```

## 使用流程

1. 运行 `bafr scan` 确认目标语言的字体映射与对应的 bundle 文件名。
2. 运行 `bafr replace <lang> <normal.otf> [bold.otf]`，产物保存在 `--output-dir`。
3. **备份**游戏目录中原版的同名 bundle 文件。
4. 用产物覆盖游戏目录中同名的原版文件（默认位于 `BlueArchive_Data/StreamingAssets/PUB/Resource/Preload/Windows/`）。
5. 启动游戏验证效果；如需回滚，还原第 3 步的备份即可。

> [!WARNING]
> 请务必先备份原版文件。工具只负责生成产物，不会自动替换游戏目录中的文件。

## 当前字体映射（Steam 国际服）

> [!NOTE]
> 以下为 Steam 国际服实测结果，游戏更新后可能变化，请以 `bafr scan` 的实际输出为准。

| 语言 | Normal | Bold | 所在 bundle |
| --- | --- | --- | --- |
| th | `RSU_BOLD` | `RSU_BOLD` | `...-2025-03-11_assets_all_3487395783.bundle` |
| en | `NotoSans-Regular` | `NotoSans-Bold` | `...-2025-03-11_assets_all_3487395783.bundle` |
| kr | `MainFont` | `MainFont_Bold` | `...-2024-11-18_assets_all_2386780975.bundle` |
| tw | `NotoSansTC-Medium` | `NotoSansTC-Bold` | `...-2026-03-13_assets_all_842690403.bundle` |

表中的 bundle 名省略了公共前缀 `prologdepengroup-assets-_mx-uis-_mxcommon-_mxprolog`，这些文件均位于 `Preload/Windows`。

## 工作原理

替换流程与逆向结论的完整说明见 [字体渲染链逆向报告](docs/2026-10-22_BA%E5%9B%BD%E9%99%85%E6%9C%8DUI%E5%AD%97%E4%BD%93%E6%B8%B2%E6%9F%93%E9%93%BE%E9%80%86%E5%90%91%E6%8A%A5%E5%91%8A.md)，核心步骤：

1. **定位语言映射**：在 `Preload/Windows/ui-font-_mxload-*.bundle` 中找到 MX 框架的 `BundleFonts` MonoBehaviour，由关联的 GameObject 名（`BundleFontTw`）解析语言代码，读取 `Normal` / `Bold` 两个 PPtr。语言列表是动态枚举的，不硬编码。
2. **定位物理 bundle**：PPtr 的外部引用按 SerializedFile 名（`CAB-xxx`）索引，需在 `GameData/Windows` 与 `Preload/Windows` 全部 bundle 中搜索。搜索使用轻量 UnityFS 头部解析，只读 blockinfo 不解压数据块，并优先扫描 prolog 前缀包；结果按“路径 + 大小 + mtime”缓存，游戏更新后缓存自动失效重扫。
3. **替换字体资产**：在 UnityPy typetree 中替换 `m_FontData` 与 `m_FontNames`，清空字形缓存字段（`m_CharacterRects` / `m_CharacterInfo`，按实际存在性自适应），其余字体度量字段保持不变。
4. **CRC 修正**：客户端按文件名尾的 CRC32 自校验，保存后追加 4 字节修正尾，使整文件 CRC 等于文件名中的数值。
5. **产物自检**：重新加载产物，校验字体数据、家族名与 CRC，全部通过才算成功。

## 代码复用与致谢

本项目在定位、Bundle 处理与 CRC 修正等部分**复用并改编了 [BA-Modding-Toolkit](https://github.com/Agent-0808/BA-Modding-Toolkit) 的部分源代码**。
BAMT 以 GPL-3.0 授权，本项目复用其代码，整体同样遵循 GPL-3.0。

其他依赖：

- [UnityPy](https://github.com/K0lb3/UnityPy)（MIT License）：Unity bundle 解析与操作
- [Tap](https://github.com/swansonk14/typed-argument-parser)（MIT License）：命令行参数解析
- [pytest](https://pytest.org/)（MIT License）：测试框架

## 开发

```bash
# 运行测试
uv run pytest

# 查看帮助
uv run bafr --help
uv run bafr scan --help
uv run bafr replace --help
```

### 文件结构

```
BA-Font-Replacer/
├── src/bafr/
│ ├── __init__.py
│ ├── cli.py         # 命令行入口（scan / replace）
│ ├── fonts.py       # 核心业务：BundleFonts 解析、Font 替换、自检
│ ├── bundle.py      # Bundle 封装、轻量 CAB 名解析
│ ├── naming.py      # 文件名解析
│ ├── searching.py   # 资源目录搜索与 CAB 定位、缓存
│ ├── paths.py       # 游戏路径探测
│ └── utils/
│   ├── common.py    # 日志类型
│   └── crc.py       # CRC32 计算与 CRC 修正
├── tests/           # pytest 测试（含原版 / 改后 bundle 对照资产）
├── docs/            # 逆向报告等文档
├── pyproject.toml
├── LICENSE
├── README.zh-CN.md  # 项目说明文档（中文，本文件）
└── README.md        # 项目说明文档
```

## 免责声明 / Disclaimer

<sub>
BA-Font-Replacer is a personal project and is not affiliated with, endorsed by, or connected to NEXON Games Co., Ltd., NEXON Korea Corp., Yostar, Inc., or any of their subsidiaries. All game assets, characters, music, and related intellectual property are the trademarks or registered trademarks of their respective owners. They are used in this tool for educational and interoperability purposes only (fair use). Please respect the Terms of Service of the official game. Do not use this tool for cheating or malicious activities.
</sub>
