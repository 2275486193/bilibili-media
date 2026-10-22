"""Search, inspect and download public Bilibili DASH streams without encoding."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from media_common import emit, ffmpeg_path, fingerprint, inspect_media, reserve_output, run_ffmpeg, save_json

API = "https://api.bilibili.com"
UA = "Mozilla/5.0 BilibiliMediaSkill/1.0"


class PageSelectionRequired(ValueError):
    def __init__(self, pages):
        self.pages = pages
        choices = "; ".join(f"P{p['page']}: {p['part']} ({p['duration']}s)" for p in pages)
        super().__init__(f"Multiple pages require selection: {choices}. Ask which page to download, "
                         "then specify --page, --cid or URL p=.")


def request(url, referer="https://www.bilibili.com/"):
    try:
        return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Referer": referer}), timeout=45)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code}; stopped without retry or access-control bypass.") from None


def api(endpoint, **params):
    with request(API + endpoint + "?" + urllib.parse.urlencode(params)) as response:
        try:
            data = json.load(response)
        except (ValueError, UnicodeError):
            raise RuntimeError("Non-JSON API response; stop and inspect in normal browser.") from None
    if data.get("code") != 0:
        raise RuntimeError(f"API code {data.get('code')}: {data.get('message', data.get('msg', 'rejected'))}; stopped.")
    return data.get("data") or {}


def parse_target(target):
    parsed = urllib.parse.urlparse(target)
    if parsed.hostname in {"b23.tv", "www.b23.tv"}:
        with request(target) as response:
            target = response.url
        parsed = urllib.parse.urlparse(target)
    match = re.search(r"BV[0-9A-Za-z]{10}(?![0-9A-Za-z])", target)
    if not match:
        raise ValueError("Supply a BV id or video URL; use search for keywords.")
    query = urllib.parse.parse_qs(parsed.query)
    return match[0], int(query["p"][0]) if "p" in query else None


def get_info(target, page=None, cid=None):
    bvid, url_page = parse_target(target)
    data = api("/x/web-interface/view", bvid=bvid)
    pages = data.get("pages") or []
    if not pages:
        raise ValueError("No accessible pages in video metadata.")
    selected_page = page if page is not None else url_page
    if cid is not None:
        chosen = next((p for p in pages if p["cid"] == cid), None)
    elif selected_page is not None:
        chosen = next((p for p in pages if p["page"] == selected_page), None)
    else:
        chosen = pages[0] if len(pages) == 1 else None
    if chosen is None and (cid is not None or selected_page is not None):
        raise ValueError("Requested page/cid does not belong to this video.")
    info = {"bvid": bvid, "title": data.get("title"), "author": data.get("owner", {}).get("name"),
            "description": data.get("desc"), "pages": [
                {k: p.get(k) for k in ("page", "cid", "part", "duration")} for p in pages],
            "selected_page": {k: chosen.get(k) for k in ("page", "cid", "part", "duration")} if chosen else None}
    info["source_url"] = f"https://www.bilibili.com/video/{bvid}/"
    if chosen:
        info["source_url"] += f"?p={chosen['page']}"
    return info


def get_tracks(info):
    data = api("/x/player/playurl", bvid=info["bvid"], cid=info["selected_page"]["cid"], fnval=16, qn=127, fourk=1)
    dash = data.get("dash")
    if not dash or not dash.get("audio"):
        raise RuntimeError("No accessible DASH audio; legacy durl, paid and restricted playback are not handled.")
    return dash


def public_track(track):
    return {k: track.get(k) for k in ("id", "bandwidth", "codecs", "mimeType", "width", "height", "frameRate")}


def choose_audio(tracks, minimum=None, maximum=None):
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ValueError("Audio minimum exceeds maximum.")
    candidates = [t for t in tracks if (minimum is None or t.get("bandwidth", 0) >= minimum * 1000)
                  and (maximum is None or t.get("bandwidth", 0) <= maximum * 1000)]
    if not candidates:
        raise ValueError("No original audio matches bandwidth range; inspect alternatives or explicitly transcode.")
    return max(candidates, key=lambda t: t.get("bandwidth", 0))


def choose_video(tracks, height=None):
    candidates = [t for t in tracks if height is None or t.get("height", 0) <= height]
    if not candidates:
        raise ValueError("No video matches height limit.")
    return max(candidates, key=lambda t: (t.get("height", 0), t.get("bandwidth", 0)))


def safe_name(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value).strip(" .")[:90]
    if re.fullmatch(r"CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9]", value, re.I):
        value = "_" + value
    return value or "bilibili"


def download_track(track, path, referer):
    url = track.get("baseUrl") or track.get("base_url")
    if not url or urllib.parse.urlparse(url).scheme not in {"http", "https"}:
        raise ValueError("Missing HTTP(S) media URL")
    path, partial = reserve_output(path)
    with request(url, referer) as response:
        expected = response.headers.get("Content-Length")
        with partial.open("xb") as output:
            first = response.read(1024 * 1024)
            if b"ftyp" not in first[:128] and b"styp" not in first[:128]:
                raise RuntimeError("Unexpected media signature; retained .partial.")
            output.write(first)
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                output.write(chunk)
    if not partial.stat().st_size or (expected and partial.stat().st_size != int(expected)):
        raise RuntimeError("Incomplete media; retained .partial")
    partial.rename(path)
    return fingerprint(path)


def download(args):
    info = get_info(args.target, args.page, args.cid)
    if info["selected_page"] is None:
        raise PageSelectionRequired(info["pages"])
    dash = get_tracks(info)
    audio = choose_audio(dash["audio"], args.audio_min_kbps, args.audio_max_kbps)
    video = choose_video(dash.get("video", []), args.height) if args.mode == "video" else None
    ff = None if args.raw_only else ffmpeg_path(args.ffmpeg)
    folder = Path(args.output_dir).resolve()
    folder.mkdir(parents=True, exist_ok=True)
    stem = safe_name(args.name or info["title"]) + f"_{info['bvid']}_P{info['selected_page']['page']}"
    audio_path = folder / (stem + ".source.m4a")
    video_path = folder / (stem + ".source.video.mp4")
    manifest = folder / (stem + ".download.json")
    for target in [audio_path, manifest] + ([video_path, folder / (stem + ".mp4"), folder / (stem + ".mkv")] if video else []):
        reserve_output(target)
    report = {"created_utc": datetime.now(timezone.utc).isoformat(), "source": info, "mode": args.mode,
              "reencoded": False, "selected_audio": public_track(audio), "files": [],
              "source_meaning": "Exact platform stream; not uploader master or lossless original."}
    try:
        audio_record = download_track(audio, audio_path, info["source_url"])
        report["files"].append(audio_record)
        audio_record["verification"] = inspect_media(ff, audio_path) if ff else {"status": "not decoded (--raw-only)"}
        if video:
            report["selected_video"] = public_track(video)
            report["files"].append(download_track(video, video_path, info["source_url"]))
            if ff:
                final, partial = reserve_output(folder / (stem + ".mp4"))
                command = ["-v", "error", "-n", "-i", video_path, "-i", audio_path,
                           "-map", "0:v:0", "-map", "1:a:0", "-c", "copy"]
                try:
                    run_ffmpeg(ff, [*command, "-movflags", "+faststart", "-f", "mp4", partial])
                except RuntimeError as error:
                    if partial.exists():
                        partial.unlink()
                    report["mp4_mux_error"] = str(error)
                    final, partial = reserve_output(folder / (stem + ".mkv"))
                    run_ffmpeg(ff, [*command, "-f", "matroska", partial])
                verification = inspect_media(ff, partial, verify_video=True)
                partial.rename(final)
                report["files"].append({**fingerprint(final), "verification": verification, "operation": "stream-copy mux"})
        report["status"] = "complete"
    except Exception as exc:
        report["status"] = "incomplete"
        report["error"] = str(exc)
        save_json(manifest, report)
        emit(report)
        raise
    save_json(manifest, report)
    emit(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    search = sub.add_parser("search")
    search.add_argument("keywords")
    search.add_argument("--limit", type=int, default=5)
    for name in ("inspect", "download"):
        p = sub.add_parser(name)
        p.add_argument("target")
        p.add_argument("--page", type=int)
        p.add_argument("--cid", type=int)
        if name == "download":
            p.add_argument("--mode", choices=["audio", "video"], required=True,
                           help="Required: video includes audio; ask the user if the intended mode is unclear.")
            p.add_argument("--output-dir", required=True)
            p.add_argument("--name")
            p.add_argument("--height", type=int)
            p.add_argument("--audio-min-kbps", type=float)
            p.add_argument("--audio-max-kbps", type=float)
            p.add_argument("--raw-only", action="store_true")
            p.add_argument("--ffmpeg")
    args = parser.parse_args()
    if args.command == "search":
        if not 1 <= args.limit <= 20:
            raise ValueError("limit must be 1..20")
        data = api("/x/web-interface/search/type", search_type="video", keyword=args.keywords)
        emit([{"bvid": t.get("bvid"), "title": html.unescape(re.sub(r"<[^>]+>", "", t.get("title", ""))),
               "author": t.get("author"), "duration": t.get("duration"),
               "description": html.unescape(t.get("description", "")),
               "url": f"https://www.bilibili.com/video/{t.get('bvid')}/"} for t in (data.get("result") or [])[:args.limit]])
    elif args.command == "inspect":
        info = get_info(args.target, args.page, args.cid)
        if info["selected_page"] is None:
            emit({**info, "status": "needs_selection",
                  "message": "Ask which page to download, then specify --page, --cid or URL p=."})
            return
        dash = get_tracks(info)
        emit({**info, "audio": [public_track(t) for t in dash.get("audio", [])],
              "video": [public_track(t) for t in dash.get("video", [])]})
    else:
        try:
            download(args)
        except PageSelectionRequired as exc:
            emit({"status": "needs_selection", "pages": exc.pages, "message": str(exc)})


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        emit({"status": "error", "message": str(exc)})
        sys.exit(1)
