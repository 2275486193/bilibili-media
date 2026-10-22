---
name: bilibili-media
description: 搜索 B 站视频，按 BV 号、视频链接或内容描述下载视频和音频，支持仅音频、指定分集与质量；默认保留平台原编码，用户要求转换格式时使用固定脚本转码。
---

# B 站音视频下载

## 核心约定

- 接受 BV 号、B 站链接（含 b23.tv）、关键词或自然语言描述。仅要求搜索时只返回候选；要求搜索并下载时核对标题、作者、时长、分集，按用户目标选取匹配项。歧义影响结果时再询问。
- 下载视频默认包含画面和音频；“仅音频／伴奏”选 audio 模式。URL 的 `p=` 指定分集，默认只下载选中分集，不擅自批量下载。区分原唱、和声伴奏、纯器乐及截取片段，不能只看合集标题。
- **默认下载平台提供的最高可用质量原编码流，不二次编码。** “原文件”指平台提供的文件，不是上传者原始母带、无损音源或未压缩素材。音频保存精确下载字节；视频保留分离源流，同时用 `-c copy` 无损封装成可播放文件。
- 用户限定码率时选择满足条件的源音轨；没有符合条件的源轨就解释并使用固定脚本转换，不能把低码率升码率称为提升音质。视频分辨率、音频码率分别处理。
- 遇到 412、429、验证或权限限制就停止该请求并说明，可交付已完成部分；不绕过登录／付费／DRM／验证码／风控，不反复重试。

## 执行

固定脚本位于本技能 `scripts/`，下列路径相对于本技能目录，从任意工作目录执行均可。使用 Python 3.10+。网络部分只依赖标准库。FFmpeg 通过 `--ffmpeg`、`BILIBILI_FFMPEG`、PATH 或已安装的 `imageio_ffmpeg` 查找；桌面环境可用 `load_workspace_dependencies` 定位 Python，必要时在当前工作区 work/ 安装 imageio-ffmpeg，并将其目录加入 PYTHONPATH；不要写死某次对话的运行时路径。

```text
python scripts/bilibili_media.py search "关键词" --limit 5
python scripts/bilibili_media.py inspect BVxxxxxxxxxx
python scripts/bilibili_media.py inspect "https://www.bilibili.com/video/BVxxxxxxxxxx/?p=3"
python scripts/bilibili_media.py download BVxxxxxxxxxx --page 3 --mode audio --output-dir <outputs>
python scripts/bilibili_media.py download BVxxxxxxxxxx --mode video --output-dir <outputs>
```

`inspect` 返回分集和当前可用音轨／视频轨。`download` 可用 `--audio-min-kbps 128 --audio-max-kbps 192` 过滤平台声明带宽（仅是选择依据，实际码率以校验报告为准），用 `--height 1080` 设视频高度上限。精确分集也可传 `--cid`。默认不覆盖。FFmpeg 不可用时 `--raw-only` 可保存精确源流，报告明确未解码校验。

工具输出 JSON 清单和 `.download.json`，包含来源、分集、编码、文件字节数、SHA256、解码和峰值检查；不把带签名的临时 CDN 地址写进永久清单。每个文件先写 `.partial`，成功后才改正式名。

若搜索接口被风控，停止使用该接口；可通过环境中正常可用的网页搜索寻找公开视频链接，再 inspect 核对，不把搜索摘要当作确认过的音轨内容。排错或扩展脚本时读取 [references/api.md](references/api.md)。

## 用户要求转换格式时

**统一调用 `scripts/transcode_media.py`，不要临时拼凑另一套编码逻辑。** 保留源文件，输出新文件名；默认保留采样率和声道，MP3 不支持的高采样率才降至 48 kHz。

```text
python scripts/transcode_media.py source.m4a --format mp3 --audio-bitrate 192k --output result.mp3
python scripts/transcode_media.py source.m4a --format wav --output result.wav
python scripts/transcode_media.py source.m4a --format m4a --copy --output compatible.m4a
python scripts/transcode_media.py source.mp4 --format mp4 --crf 20 --output compatible.mp4
```

- `--copy` 只封装，不编码、不调音量；容器须支持原编码。
- 二次音频编码默认检查源峰值，必要时衰减至 -2 dBFS 留余量，只降不升。用户要求音量原样时用 `--keep-level`，保留峰值风险提示；`--peak-ceiling-db` 可调整余量。编码后再查峰值，余量不能保证无真峰值过载。
- 不降噪、不做人声分离、不添加音效。输出完整解码校验，记录实际编码、采样率、码率、峰值、超满刻度样本和实际衰减。峰值风险不能证明电流音来源；解码通过也不证明无噪声。
- AAC→MP3 属于二次有损编码。转 WAV／FLAC 不恢复已有损失；源 AAC 也不是无损。说明转换及限制，不承诺可听音质提高。

## 交付

提供本地文件和来源链接、正确分集、格式／编码、实际码率、时长、是否转码。视频说明保留的原流及合并文件；仅音频无需下载画面。原音轨不兼容播放器时优先 `--copy` 重封装，确需兼容编码时才转码。不声称试听过；比对噪声先确认相同分集、时间点和音量。
