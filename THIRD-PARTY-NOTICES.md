# 第三方组件与授权声明

U Draw 本体以 [MIT](LICENSE) 协议发布。仓库中使用的第三方组件如下。

## 运行依赖

| 组件 | 授权 | 说明 |
|---|---|---|
| [PySide6](https://pypi.org/project/PySide6/)（Qt for Python） | LGPL-3.0 | 以独立 Python 包形式安装、动态链接，未修改 Qt 源码。商用闭源分发时需遵守 LGPLv3 的动态链接与替换条款 |
| [NumPy](https://numpy.org/) | BSD-3-Clause | 仅用于像素缓冲的数值运算 |

## 内置字体（`assets/fonts/`）

| 字体 | 授权 |
|---|---|
| BIZ UDMincho | SIL Open Font License 1.1 |
| BIZ UDPGothic / BIZ UDPGothic Bold | SIL Open Font License 1.1 |
| Shippori Mincho | SIL Open Font License 1.1 |

授权原文随字体一起提供：`assets/fonts/OFL-biz-ud-mincho.txt`、`OFL-biz-ud-pgothic.txt`、`OFL-shippori-mincho.txt`。

## 血缘声明

U Draw 衍生于 **PhotoCraft 0.12.0** —— ArtCraft 开源发布的 Photoshop 复刻
（MIT / Apache-2.0 双许可，100% Rust 编写，https://getartcraft.com/apps/photocraft ）。

本项目以 PhotoCraft 的界面语言与 Pro (Dark) 配色为参照，用 Python + PySide6
**重新实现**，仓库中不包含 PhotoCraft 的任何源代码。

原项目名称与商标归 ArtCraft 所有，本软件与其无隶属关系，也不代表其立场。
