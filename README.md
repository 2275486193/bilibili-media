# bilibili-media

可复用的 Codex 技能：按 BV 号、B 站链接或搜索描述下载视频和音频，默认保留平台原编码，按需使用固定脚本转码。

## 功能

- 支持关键词搜索、BV 号、视频链接、b23.tv 短链及指定分集。
- 支持完整音视频或仅音频；默认只下载选中分集。
- 默认保留平台可访问的最高质量编码流。视频保留分离源流，并以 `-c copy` 无损封装合并。
- 指定码率范围时选择符合条件的源音轨，没有匹配项时明确提示。
- 固定转码脚本支持 MP3、M4A、AAC、WAV、FLAC、MP4、MKV，以及兼容容器间的仅封装模式。
- 自动记录来源、分集、实际编码、码率、SHA-256、完整解码和样本峰值检查。
- 默认防止覆盖文件，下载中间文件使用 `.partial`。

## 安装与依赖

将仓库放入 `$CODEX_HOME/skills/bilibili-media`，未设置 CODEX_HOME 时使用 `~/.codex/skills/bilibili-media`。

需要 Python 3.10+。网络请求仅依赖标准库；合并、解码检查和转码需要 FFmpeg。按以下顺序定位 FFmpeg：`--ffmpeg` 参数、`BILIBILI_FFMPEG` 环境变量、PATH、已安装的 `imageio-ffmpeg`。可选安装方式：

```sh
python -m pip install imageio-ffmpeg
```

Codex 识别技能后，可显式使用 `$bilibili-media`，也可通过相关自然语言请求触发。

```text
使用 $bilibili-media 下载 BV 号对应视频的第 3P，仅音频，保留原编码。
使用 $bilibili-media 搜索孤独患者纯伴奏，核对分集后下载。
使用 $bilibili-media 下载这个视频，保留源文件，另外生成 192kbps MP3。
```

## 命令行使用

下列命令在仓库根目录执行；`BVxxxxxxxxxx` 替换成实际 BV 号。

```sh
python scripts/bilibili_media.py search "孤独患者 纯器乐伴奏" --limit 5
python scripts/bilibili_media.py inspect "https://www.bilibili.com/video/BVxxxxxxxxxx/?p=3"
python scripts/bilibili_media.py download BVxxxxxxxxxx --page 3 --mode audio --output-dir outputs
python scripts/bilibili_media.py download BVxxxxxxxxxx --mode video --height 1080 --output-dir outputs
```

选择平台已有的 128–192 kbps 音轨：

```sh
python scripts/bilibili_media.py download BVxxxxxxxxxx --mode audio --audio-min-kbps 128 --audio-max-kbps 192 --output-dir outputs
```

范围按 API 声明的 bandwidth 选择；报告中的实际平均码率可能略有不同。没有匹配原轨时停止，不自动升码率转码。`--height` 是视频高度上限；默认只选择当前公开可访问的质量。

无 FFmpeg 时可使用 `--raw-only` 下载分离原流，此时不会合并或进行完整解码检查。下载完成后生成 `.download.json`，不保存含临时签名的 CDN 地址。

## 固定转码脚本

仅在用户明确要求其他格式时使用，输出新文件并保留源文件：

```sh
python scripts/transcode_media.py source.m4a --format mp3 --audio-bitrate 192k --output result.mp3
python scripts/transcode_media.py source.m4a --format wav --output result.wav
python scripts/transcode_media.py source.m4a --format m4a --copy --output compatible.m4a
python scripts/transcode_media.py source.mp4 --format mp4 --crf 20 --output compatible.mp4
```

`--copy` 仅重新封装，不修改编码或音量，目标容器必须兼容原编码。二次编码默认保留采样率；MP3 不支持的高采样率才降至 48 kHz。默认按源样本峰值预留 -2 dBFS 余量，只降不升；可用 `--keep-level` 保持音量，或用 `--peak-ceiling-db` 修改余量。报告记录实际衰减及前后峰值。

转换后生成 `.conversion.json`。AAC 转 MP3 会再次有损压缩；转 WAV 或 FLAC 不能恢复原有损失。脚本不降噪、不分离人声、不添加音效。

## 文件结构

```text
SKILL.md                       技能入口与工作流程
agents/openai.yaml             Codex 展示与调用信息
scripts/bilibili_media.py       搜索、检查、原编码下载
scripts/transcode_media.py      固定格式转换
scripts/media_common.py         哈希、FFmpeg 和解码检查
references/api.md              API 与音视频流说明
```

## 限制与验证

原文件指 B 站提供的编码流，不代表上传者母带或无损素材。样本峰值检查不等于过采样 true-peak 检测，解码正常也不能证明没有可听噪声。

接口可能变化或受风控影响。遇到 412、429、权限限制或验证要求时停止请求；不自动提取浏览器凭据，不绕过登录、付费或 DRM。搜索接口不可用时，Codex 可通过正常网页搜索找到链接后再核对。请在拥有相应权限的范围内使用。

已在 Windows / Python 3.12 / FFmpeg 7.1 下验证 BV 分集识别、原流下载、音画无损合并、7 种格式转换、仅封装音频一致性及防覆盖行为。搜索接口曾返回 412，已验证脚本停止请求；这不代表搜索在所有环境中可用。
