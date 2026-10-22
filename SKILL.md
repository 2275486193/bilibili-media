---
name: bilibili-media
description: 搜索 B 站视频，按 BV 号、视频链接或内容描述下载视频和音频，支持仅音频、指定分集与质量；默认保留平台原编码，用户要求转换格式时使用固定脚本转码。
---

# B 站音视频下载

脚本在本技能 `scripts/`，命令在技能根目录执行；依赖 Python 3.10+，合并与校验需要 FFmpeg。

```text
python scripts/bilibili_media.py inspect BVxxxxxxxxxx
python scripts/bilibili_media.py download BVxxxxxxxxxx --mode audio --output-dir <out>
python scripts/bilibili_media.py download BVxxxxxxxxxx --page 2 --mode video --height 1080 --output-dir <out>
python scripts/bilibili_media.py search "关键词" --limit 5
python scripts/transcode_media.py src.m4a --format mp3 --audio-bitrate 192k --output dst.mp3
```

## 规则

- 默认下载平台最高可用原编码流，不二次编码；视频用 `-c copy` 无损合并。原流指平台编码，不是上传者母带。
- 下载前确认类型：“下载视频”选 `--mode video`（含音频），“仅音频／伴奏”选 `--mode audio`；仅说“下载这个 BV／链接”等无法明确类型时，先问要完整视频还是仅音频，不猜测。
- 先用 `inspect` 确认分集；已有可靠元信息时可复用。单 P 自动选择唯一分集；多 P 且用户未指定时，返回分集编号、标题、时长并询问，收到答复后才下载，不默认第 1P、不擅自批量。用户已指定的 `--page`、`--cid` 或链接 `p=` 无需重复确认。
- 类型和分集都明确后才调用 `download`，始终显式传入 `--mode`；若两项都缺失，一次询问。按标题、时长核对原唱／伴奏／截取片段。
- `--audio-min-kbps`／`--audio-max-kbps` 按平台带宽筛选，`--height` 限分辨率；无匹配原轨就说明，不升码率冒充提质。
- 仅当用户要求其它格式时转码，保留源文件；`--copy` 只封装。不降噪、不分离人声；转码属二次有损，不承诺音质提升。
- 遇 412／429／验证／权限限制立即停止并说明，不绕过登录、付费或 DRM。搜索受风控时改用网页搜索找链接，再 inspect 核对。
- 交付：文件路径、来源与分集、编码与码率、时长、是否转码；不做试听结论。

排错与接口细节见 `references/api.md`。
