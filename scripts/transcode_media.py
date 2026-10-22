"""Explicit, verified media conversion for bilibili-media."""
from __future__ import annotations
import argparse
from pathlib import Path
import sys
from media_common import emit, ffmpeg_path, fingerprint, inspect_media, reserve_output, run_ffmpeg, save_json


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("source")
    p.add_argument("--format", choices=["mp3", "m4a", "aac", "wav", "flac", "mp4", "mkv"], required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--audio-bitrate", default="192k")
    p.add_argument("--crf", type=int, default=20)
    p.add_argument("--copy", action="store_true")
    p.add_argument("--keep-level", action="store_true")
    p.add_argument("--peak-ceiling-db", type=float, default=-2.0)
    p.add_argument("--ffmpeg")
    args = p.parse_args()
    if not -20 <= args.peak_ceiling_db <= 0:
        raise ValueError("Peak ceiling must be between -20 and 0 dBFS")
    if not 0 <= args.crf <= 51:
        raise ValueError("CRF must be between 0 and 51")
    source = Path(args.source).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    output, partial = reserve_output(args.output)
    report_path = output.with_name(output.name + ".conversion.json")
    reserve_output(report_path)
    if output == source:
        raise ValueError("Source and output must differ")
    if output.suffix.lower() != "." + args.format:
        raise ValueError("Output extension must match --format")
    ff = ffmpeg_path(args.ffmpeg)
    before = inspect_media(ff, source)
    command = ["-v", "error", "-n", "-i", source]
    gain_db = 0.0
    peak = before.get("sample_peak_dbfs")
    if not args.copy and not args.keep_level and peak is not None:
        gain_db = min(0.0, args.peak_ceiling_db - peak)
    if args.copy:
        command += ["-map", "0:a:0" if args.format in {"mp3", "m4a", "aac", "wav", "flac"} else "0", "-c", "copy"]
    elif args.format in {"mp3", "m4a", "aac", "wav", "flac"}:
        command += ["-map", "0:a:0"]
        if args.format == "mp3":
            command += ["-c:a", "libmp3lame", "-b:a", args.audio_bitrate]
        elif args.format == "m4a":
            command += ["-c:a", "aac", "-b:a", args.audio_bitrate, "-movflags", "+faststart"]
        elif args.format == "aac":
            command += ["-c:a", "aac", "-b:a", args.audio_bitrate]
        elif args.format == "wav":
            command += ["-c:a", "pcm_s24le"]
        else:
            command += ["-c:a", "flac"]
        if args.format == "mp3" and before.get("sample_rate_hz", 0) > 48000:
            command += ["-ar", "48000"]
    else:
        if not before.get("video_stream"):
            raise ValueError("Video conversion requires a source containing video")
        command += ["-map", "0:v:0", "-map", "0:a:0", "-c:v", "libx264", "-crf", str(args.crf), "-c:a", "aac", "-b:a", args.audio_bitrate]
        if args.format == "mp4":
            command += ["-movflags", "+faststart"]
    if gain_db:
        command += ["-af", f"volume={gain_db:.8f}dB"]
    container = {"m4a": "mp4", "aac": "adts", "mkv": "matroska"}.get(args.format, args.format)
    try:
        run_ffmpeg(ff, [*command, "-f", container, partial])
        after = inspect_media(ff, partial, verify_video=bool(before.get("video_stream")) and args.format in {"mp4", "mkv"})
        if not after["decoded_without_error"]:
            raise RuntimeError("Output decoding reported errors")
        partial.rename(output)
    except Exception:
        if partial.exists():
            partial.unlink()
        raise
    report = {"status": "complete", "source": fingerprint(source), "output": fingerprint(output),
              "format": args.format, "reencoded": not args.copy, "copy": args.copy,
              "keep_level": args.keep_level, "requested_peak_ceiling_db": args.peak_ceiling_db,
              "applied_gain_db": round(gain_db, 8),
              "before": before, "after": after}
    save_json(report_path, report)
    emit(report)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit({"status": "error", "message": str(exc)})
        sys.exit(1)
