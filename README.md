# bilibili-media

一个可加载到 Agent 中的技能：按 BV 号、B 站链接或关键词下载视频和音频，默认保留平台原编码。

## 功能

- 关键词搜索、BV 号、视频链接、b23.tv 短链，支持指定分集。
- 完整音视频或仅音频；类型不明确时先询问，多分集未选集时列出候选并询问。
- 默认保存平台最高可用质量的原始编码流，视频用 `-c copy` 无损合并，不做二次编码。
- 可按码率范围、分辨率上限筛选源轨道。
- 明确要求转换格式时，使用固定脚本输出 MP3、M4A、AAC、WAV、FLAC、MP4、MKV 或仅封装文件。
- 自动记录来源、分集、编码、码率、SHA-256 与解码检查结果。

## 加载到 Agent

本技能不绑定特定产品，任何能读取 `SKILL.md` 并执行终端命令的 Agent 都可使用。把本仓库整体放入该 Agent 的技能目录：

技能目录由所用 Agent 决定，也可放入项目的技能／规则目录；目录名使用 `bilibili-media/`。

目录内需包含 `SKILL.md`（入口文件）和 `scripts/`。不要只复制 `SKILL.md`。

没有技能加载机制时，直接在对话中说明：读取本目录的 `SKILL.md`，按其中命令通过终端执行脚本。

依赖：Python 3.10+；合并与转码需要 FFmpeg（按 `--ffmpeg`、`BILIBILI_FFMPEG`、PATH、`imageio-ffmpeg` 的顺序查找）。

## 调用示例

Agent 下载前会确认类型和分集：明确要求“下载视频”则包含画面和音频，要求“仅音频／伴奏”则只下载音频；仅给出“下载这个 BV／链接”时先询问类型。单 P 自动选中；多 P 未指定时列出编号、标题和时长，询问后再下载，不默认第 1P。若两项都不明确，一次询问。

命令行必须显式传入 `--mode audio` 或 `--mode video`；多 P 必须通过 `--page`、`--cid` 或链接的 `p=` 选集。`inspect` 遇到未选集的多 P 时返回 `needs_selection` 和分集列表，不查询任意一集的音视频轨。

自然语言：

```text
下载这个 B 站视频，仅保留音频，使用原编码。
搜索 Python 入门教程，列出候选视频。
下载 BVxxxxxxxxxx 第 3 集的音频，保留源文件，另转成 192 kbps MP3。
```

命令行（在仓库根目录执行）：

```sh
python scripts/bilibili_media.py search "Python 入门教程" --limit 5
python scripts/bilibili_media.py inspect "https://www.bilibili.com/video/BVxxxxxxxxxx/?p=3"
python scripts/bilibili_media.py download BVxxxxxxxxxx --page 3 --mode audio --output-dir outputs
python scripts/bilibili_media.py download BVxxxxxxxxxx --page 1 --mode video --height 1080 --output-dir outputs
python scripts/transcode_media.py source.m4a --format mp3 --audio-bitrate 192k --output result.mp3
```

遇到 412、429 或权限验证时停止请求，不绕过登录、付费或 DRM。请在拥有相应权限的范围内使用。
