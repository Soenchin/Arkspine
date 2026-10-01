# 上游同步记录

- 上游：https://github.com/GenielabsOpenSource/spine-animation-ai
- 同步日期：2026-10-01
- 对比基线：`faeafe412a544ebeb6495df64a220448c8a625a6`
- 已同步到：`702b71689cac826efee942ee4564fef9560d6ef8`（2026-08-26）
- 方式：同步内置副本中的文件；没有合并上游 Git 历史或添加 remote。

## 本次内容

以下三个文件与该上游提交一致：

- `spine-animation-ai/scripts/build_spine_json.py`：Spine 4.2 旋转字段、按属性存储的贝塞尔曲线、绝对控制点和曲线所属区间修复。
- `spine-animation-ai/references/spine-json-spec.md`：对应格式说明。
- `spine-animation-ai/examples/sombrero/sombrero.json`：修复示例缩放、关节与贴图归属及动画格式。

`spine-animation-ai/SKILL.md` 通过本地 `build_skill.py` 重新生成，保留 Arkspine 模板和拆图脚本的定制，不用上游整份覆盖。重建也补齐了先前未嵌入文档的透明 padding RGB 扩边逻辑；拆图脚本本身未修改。

保留现有根 README 改动、Krill/透明拆图实现，以及未提交的 `layout_to_spine_config.py` 和其测试。

## 验证

新增 `tests/test_spine_42_timelines.py`，覆盖六套预设、旋转字段、双轴曲线、绝对控制点、自定义 stepped 时间线及更新后的示例。

```bash
python -B spine-animation-ai/build_skill.py
python -B -m unittest discover -s tests -v
git diff --check
```

本次做了数据格式和现有单元测试检查，未做浏览器/官方 Spine Runtime 播放验收，不代表完整立绘到动画链路已通过。

上游目录继续遵循其 PolyForm Noncommercial 许可证；本次同步不改变商业使用边界。
