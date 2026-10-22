# 接口和原流

- 搜索 `/x/web-interface/search/type?search_type=video&keyword=...`；去除标题 HTML 标记并解码实体。
- 视频信息 `/x/web-interface/view?bvid=...`；`pages[]` 包含 page/cid/part/duration。不能混用合集其他 BV 的 CID。
- 播放 `/x/player/playurl?bvid=...&cid=...&fnval=16&qn=127&fourk=1`；`dash.audio/video` 分离音画。qn 不是音频 kbps。传统 durl 模式脚本明确不支持，不冒充独立音轨。
- bandwidth 单位 bit/s，与实际平均码率有差异；id 不是可靠码率。mp4a.40.2 是 AAC-LC，mp4a.40.5 是 HE-AAC。
- baseUrl/base_url 为短时有效、带签名的 CDN 地址，带视频页面 Referer 下载。链接过期重新取播放信息，不永久保存签名 URL。
- DASH 音轨通常为 fragmented MP4，地址可为 .m4s，精确保存为 .m4a 不意味着转码。视频用 -c copy 合并；MP4 不支持编码时回退 MKV。
- 当前无登录可见的最高轨不一定是平台最高质量。脚本不提取浏览器 Cookie、不隐式使用凭证、不绕过限制。
- 浮点解码可能出现 >0 dBFS 峰值；不能凭 volumedetect 的 0.0 dB 判断无过载。检查全曲浮点峰值和超限样本，但不是过采样 true-peak 检测，也不是可听噪声判定。
