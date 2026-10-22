"""Shared media verification and file-safe subprocess helpers (stdlib only)."""
from __future__ import annotations
import array
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def emit(value):
    print(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False))


def save_json(path, value):
    path = Path(path)
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2, allow_nan=False)


def ffmpeg_path(explicit=None):
    candidate = explicit or os.environ.get("BILIBILI_FFMPEG") or shutil.which("ffmpeg")
    if candidate:
        resolved = shutil.which(candidate) or candidate
        if Path(resolved).is_file():
            return str(Path(resolved).resolve())
        raise RuntimeError("FFmpeg executable does not exist")
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        raise RuntimeError("FFmpeg not found; supply --ffmpeg or install imageio-ffmpeg") from None


def fingerprint(path):
    path = Path(path)
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path.resolve()), "bytes": path.stat().st_size, "sha256": digest.hexdigest()}


def run_ffmpeg(ffmpeg, arguments):
    r = subprocess.run([ffmpeg, "-hide_banner", "-nostdin", *map(str, arguments)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    if r.returncode:
        raise RuntimeError("FFmpeg failed: " + r.stderr.decode("utf-8", "replace")[-2200:])


def reserve_output(path):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".partial")
    if path.exists() or partial.exists():
        raise FileExistsError("Refusing to overwrite output or partial file: " + str(path))
    return path, partial


def inspect_media(ffmpeg, path, verify_video=False):
    """Decode audio to float PCM: measure sample peaks without int16 clipping."""
    peak = 0.0
    samples = over = nonfinite = 0
    with tempfile.TemporaryFile() as log:
        command = [ffmpeg, "-hide_banner", "-nostdin", "-i", str(path),
                   "-map", "0:a:0", "-vn", "-c:a", "pcm_f32le", "-f", "f32le", "pipe:1"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log)
        pending = b""
        try:
            while True:
                chunk = process.stdout.read(262144)
                if not chunk:
                    break
                pending += chunk
                length = len(pending) // 4 * 4
                values = array.array("f")
                values.frombytes(pending[:length])
                pending = pending[length:]
                if sys.byteorder != "little":
                    values.byteswap()
                samples += len(values)
                for value in values:
                    if not math.isfinite(value):
                        nonfinite += 1
                        continue
                    magnitude = abs(value)
                    peak = max(peak, magnitude)
                    over += magnitude > 1.0
            status = process.wait()
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.kill()
                process.wait()
        log.seek(0)
        diagnostic = log.read().decode("utf-8", "replace")
    if status or not samples or pending or nonfinite:
        raise RuntimeError("Audio verification failed: " + diagnostic[-1800:])
    stream_line = next((line.strip() for line in diagnostic.splitlines() if "Audio:" in line), "")
    video_line = next((line.strip() for line in diagnostic.splitlines() if "Video:" in line), None)
    rate = re.search(r"(\d+) Hz", stream_line)
    bitrate = re.search(r"(\d+) kb/s", stream_line)
    duration = re.search(r"Duration: (\d+):(\d+):([\d.]+)", diagnostic)
    seconds = None
    if duration:
        h, m, s = map(float, duration.groups())
        seconds = round(h * 3600 + m * 60 + s, 5)
    warning = [line.strip() for line in diagnostic.splitlines()
               if re.search(r"error|corrupt|invalid|damaged", line, re.I)]
    if warning:
        raise RuntimeError("Audio decode diagnostics reported errors: " + " | ".join(warning))
    result = {"decoded_without_error": not warning, "audio_stream": stream_line,
              "video_stream": video_line, "duration_seconds": seconds,
              "sample_rate_hz": int(rate[1]) if rate else None,
              "audio_bitrate_kbps": int(bitrate[1]) if bitrate else None,
              "sample_peak_dbfs": round(20 * math.log10(peak), 5) if peak else None,
              "samples_over_0dbfs": over, "decoded_audio_samples": samples,
              "warnings": warning, "peak_measurement": "sample peak; not oversampled true peak"}
    if over:
        result["warnings"].append("Decoded peaks exceed 0 dBFS; some playback paths may clip. This does not diagnose audible noise.")
    if verify_video:
        run_ffmpeg(ffmpeg, ["-v", "error", "-xerror", "-i", path, "-map", "0:v:0", "-an", "-f", "null", "-"])
        result["video_decode_verified"] = True
    return result
