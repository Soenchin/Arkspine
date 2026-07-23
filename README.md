<div align="center">

# Arkspine

### 从角色立绘到可检查的 Spine 2D 骨骼动画原型

[![License: AGPL-3.0-or-later](https://img.shields.io/badge/Arkspine-AGPL--3.0--or--later-8A2BE2?style=flat-square)](LICENSE)
[![Upstream: PolyForm NC](https://img.shields.io/badge/upstream-PolyForm%20Noncommercial%201.0.0-ff8c00?style=flat-square)](spine-animation-ai/LICENSE)
[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![Spine](https://img.shields.io/badge/Spine-4.2-16A6D9?style=flat-square)](https://esotericsoftware.com/spine-in-depth)
[![Krill GPT Image](https://img.shields.io/badge/image%20pipeline-Krill%20GPT%20Image%202-15a56b?style=flat-square)](https://api.cdn-krill-ai.com/v1)
[![Status: Prototype](https://img.shields.io/badge/status-prototype-yellow?style=flat-square)](#当前状态)

**把一张角色图拆成动画部件，自动定位、装配为 Spine JSON / Atlas，并生成浏览器预览。**

</div>

> [!WARNING]
> 这是研究原型，不是“一张立绘无损变工业级 Spine”的魔法机。当前最可靠的输出是 **简单 cutout 骨骼** 与基础动作；复杂 mesh、权重、布料、特效、皮肤切换仍需要人工制作或后续管线支持。

## 它能做什么

```text
角色参考图
  ↓ Krill GPT Image：图像编辑式拆件
拆解 sprite sheet
  ↓ OpenCV：连通域裁切
透明 PNG 部件
  ↓ SIFT + RANSAC：与原图自动对位
初始布局 + 层级顺序
  ↓ 固定模板骨架 + 动作预设
Spine 4.2 JSON + .atlas + PNG + HTML 预览
```

当前已验证的核心链路：

- 使用 **Krill GPT Image 2** 的 OpenAI 兼容 `images.edit` 接口，基于参考图生成拆解部件表；
- 从白底 sprite sheet 裁出单独的角色部件；
- 用 SIFT + RANSAC 将部件回贴至参考图位置，缺少特征时回退模板匹配；
- 生成可读的 Spine 4.2 JSON、贴图 atlas 以及 Web Player 预览页；
- 生成基础 `idle`、`walk`、`run`、`attack`、`jump`、`wave` 动作数据。

## 当前状态

| 模块 | 状态 | 说明 |
| --- | :---: | --- |
| 单图 → 拆件 sprite sheet | ✅ | Krill 图像编辑能产出结构合理的角色部件图；结果需人工检查。 |
| sprite sheet → 独立部件 | ✅ | OpenCV 自动裁切；当前白底/浅色部件的 Alpha 清理仍需加强。 |
| 部件 → 原图定位 | ✅ | SIFT + RANSAC 为主，模板匹配兜底；遮挡、纯色和小配件会有误差。 |
| 自动命名与部件语义识别 | 🟡 | 目前仍会产生 `part_007` 等匿名部件，需要模板或人工复核。 |
| 基础 cutout 骨架与预设动作 | ✅ | 适合原型、简单小人和动作草案。 |
| Mesh / 权重 / 物理 / 特效 | ❌ | 不在当前范围。 |
| 直接复刻任何游戏的正式 Spine | ❌ | 不提供，也不应使用第三方游戏资产。 |

## 快速开始

### 1. 安装依赖

```bash
pip install opencv-python Pillow numpy openai
```

### 2. 配置 Krill GPT Image

`split_character.py` 读取配置的优先顺序：

1. `KRILL_API_KEY` / `KRILL_BASE_URL` 环境变量；
2. `OPENAI_API_KEY` / `OPENAI_BASE_URL` 环境变量；
3. 本机 Pi skill 的 `~/.pi/agent/skills/krill-gpt-image/config.local.json`。

示例（不要把真实 key 提交进 Git）：

```bash
set KRILL_API_KEY=你的密钥
set KRILL_BASE_URL=https://api.cdn-krill-ai.com/v1
```

### 3. 从参考图生成部件

```bash
python spine-animation-ai/scripts/split_character.py character.png \
  --output-dir temp/parts \
  --atlas-out temp/atlas.png \
  --debug-dir temp/split-debug
```

该命令使用图片编辑模式让 Krill 依据参考角色生成拆解图，再用本地 OpenCV 裁出部件。输出部件是带透明 padding 的 RGBA PNG，并额外生成 `temp/parts/parts.json` manifest。背景只会移除**与图像边缘连通**的近似背景色，因此白色衣服、眼睛和高光不会因为简单抠白而消失。

建议检查 `temp/split-debug/foreground_alpha.png`、`background_mask.png` 和 `contours.png`。AI 生成并不保证每个部件都正确：先检查部件、命名、层级和透明边缘，再继续装配。可用 `--bg-tolerance` 调整背景颜色容差，默认是 `30`；如果仍需旧版灰度参数，可使用兼容选项 `--bg-threshold`。

### 4. 自动定位部件

```bash
python spine-animation-ai/scripts/position_parts.py \
  --reference character.png \
  --parts temp/parts \
  --output temp/layout.json \
  --debug temp/debug
```

请检查 `temp/debug/comparison.png`。部件遮挡严重、颜色太平、体积过小时，自动定位结果可能很离谱——别把它当占卜结果，手动调整是正常步骤。

### 5. 生成 Atlas、Spine JSON 和预览

`build_spine_json.py` 需要一个明确的骨骼/slot 配置 JSON。推荐先把自动分出的匿名部件命名为 `head`、`torso`、`left-upper-arm` 等，再映射到固定模板骨架。

```bash
python spine-animation-ai/scripts/make_atlas.py \
  --parts temp/parts \
  --output temp/spine \
  --name character

python spine-animation-ai/scripts/build_spine_json.py \
  --config temp/skeleton-config.json \
  --output temp/spine/character.json

python spine-animation-ai/scripts/generate_spine_player.py \
  --skeleton temp/spine/character.json \
  --atlas temp/spine/character.atlas \
  --atlas-image temp/spine/character.png \
  --output temp/spine/preview.html
```

## 推荐的 L4 工作流

目标不是让模型盲猜每个复杂角色的完整 rig，而是建立一套**固定模板骨架**：

1. 定义小人模板的头身比例、骨骼层级、slot 命名和基础动作；
2. AI 只负责生成/拆出可替换贴图；
3. 自动程序负责初始定位、atlas 与动作草案；
4. 人工检查部件名、穿插层、枢轴和关键帧；
5. 对效果需求高的部位，再在 Spine 编辑器补 mesh、权重、特效和物理。

这条路的好处是：每次都在一个可控的 skeleton 上换皮，而不是让模型从零赌一整套骨架。

## 目录说明

```text
Arkspine/
├── LICENSE                         # Arkspine 自有代码：AGPL-3.0-or-later
├── README.md
├── .gitignore                      # 忽略 temp/、密钥和本地产物
└── spine-animation-ai/             # 上游代码的内置副本（见许可证说明）
    ├── LICENSE                     # PolyForm Noncommercial 1.0.0，必须保留
    ├── scripts/
    │   ├── split_character.py      # 已改：Gemini → Krill GPT Image
    │   ├── position_parts.py
    │   ├── build_spine_json.py
    │   ├── make_atlas.py
    │   └── generate_spine_player.py
    └── ...
```

`temp/` 仅用于参考图、生成图、调试结果、atlas、预览和测试输出，已被 Git 忽略。

拆件输出约定：部件 PNG 必须是 RGBA；`alpha=0` 表示透明 padding，主体通常为 `alpha=255`，轮廓抗锯齿像素可以是中间 alpha。`parts.json` 记录背景估计、画布坐标、部件 bbox 和有效像素数，方便人工复核及后续自动命名。

## 与上游的关系

本仓库内置并修改了 [GenielabsOpenSource/spine-animation-ai](https://github.com/GenielabsOpenSource/spine-animation-ai)：

- 上游项目版权：`Copyright (c) 2025 Spine Animation AI Contributors`；
- 上游目录及其修改版继续受 [`PolyForm Noncommercial License 1.0.0`](spine-animation-ai/LICENSE) 约束；
- 本项目的主要改动是将 `scripts/split_character.py` 的图像生成链路从 Google Gemini 改为 **Krill GPT Image 2 / OpenAI-compatible Images API**；
- 上游的 `reskin-app/` 仍保留 Gemini 相关实现，**本次并未将它改造成 Krill**；
- 本仓库当前不追踪上游 Git 历史，也不以 fork 形式与上游同步。

## 许可证与使用边界

### Arkspine 自有内容：AGPL-3.0-or-later

根目录 [`LICENSE`](LICENSE) 适用于 Arkspine 新增的文档、配置、脚本和未来自有代码。若你修改并向网络用户提供这部分程序，AGPL 通常要求向这些用户提供对应源代码。

### `spine-animation-ai/`：PolyForm Noncommercial 1.0.0

这个目录**不**因为放进 Arkspine 就变成 AGPL，也不因 AGPL 而获得商业授权。其原许可证禁止商业用途；对其进行修改、分发或基于它提供服务时，必须保留该目录的许可证与 Required Notice，并遵守非商业限制。

换句话说：**这是一个混合许可证仓库。** 不要把整个项目宣传为“纯 AGPL、可商用”。若要商业化，需取得上游授权，或以不包含/不依赖上游代码的独立实现替换该部分。

### 第三方资产

请勿上传、分发或用作训练/发布素材：

- 《明日方舟》《杀戮尖塔》或其他游戏的官方图像、Spine 数据、atlas、动画曲线、角色设计；
- 你没有权利再分发的角色立绘；
- API key、访问令牌、个人资料和生成服务的私密配置。

可以研究动作的通用原则（重心、缓入缓出、蓄力—击打—回弹），但不要把第三方游戏资源或导出的骨架数据塞进仓库。

## 致谢

- [Spine Animation AI](https://github.com/GenielabsOpenSource/spine-animation-ai) —— 上游自动装配管线；
- [Spine](https://esotericsoftware.com/) —— 2D 骨骼动画工具与运行时；
- [Krill GPT Image](https://api.cdn-krill-ai.com/v1) —— 图像拆件实验所用的 OpenAI 兼容图像接口；
- OpenCV、Pillow、Spine Web Player。

---

<div align="center">
  <sub>Arkspine 是一个非商业研究原型。先让小人长出骨头，再谈让它跳舞。🐾</sub>
</div>
