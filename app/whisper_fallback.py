import tempfile
import subprocess
import os
import shutil
import os

try:
    import whisper
except Exception:
    whisper = None


def _truncate_bytes(data: bytes, max_len: int = 400) -> str:
    if not data:
        return ""
    text = data.decode(errors="ignore")
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."


_model = None
_availability_checked = False
_is_available = False


def whisper_available() -> bool:
    global _availability_checked, _is_available
    if _availability_checked:
        return _is_available

    _availability_checked = True
    _is_available = (
        whisper is not None
        and bool(shutil.which("yt-dlp"))
        and bool(shutil.which("ffmpeg"))
    )
    return _is_available


def _get_model():
    global _model
    if _model is None:
        if whisper is None:
            raise RuntimeError("Whisper is not available in this environment.")
        _model = whisper.load_model("base")
    return _model


def _safe_log(on_log, message: str):
    if on_log:
        try:
            on_log(message)
        except Exception:
            pass


def transcribe_video(video_id: str, on_log=None):
    """
    Best-effort Whisper transcription.
    NEVER throws.
    Returns transcript-like list or None.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"

    try:
        if not whisper_available():
            return None

        with tempfile.TemporaryDirectory() as tmpdir:
            audio_path = os.path.join(tmpdir, "audio.mp3")

            # 🔑 yt-dlp may fail for many valid reasons; try multiple clients
            clients_raw = os.getenv("YTDLP_PLAYER_CLIENTS", "tv,web_embedded,web")
            player_clients = [c.strip() for c in clients_raw.split(",") if c.strip()]
            if not player_clients:
                player_clients = ["tv", "web_embedded", "web"]

            cookies_file = os.getenv("YTDLP_COOKIES_FILE")
            cookies_from_browser = os.getenv("YTDLP_COOKIES_FROM_BROWSER")

            last_error = None
            player_js_variant = os.getenv("YTDLP_PLAYER_JS_VARIANT", "tv")
            for player_client in player_clients:
                extractor_args = f"youtube:player_client={player_client}"
                if player_js_variant:
                    extractor_args += f";player_js_variant={player_js_variant}"
                cmd = [
                    "yt-dlp",
                    "-f", "bestaudio/best",
                    "-x",
                    "--audio-format", "mp3",
                    "--no-playlist",
                    "--geo-bypass",
                    "--force-ipv4",
                    "--js-runtimes", "node",
                    "--extractor-args", extractor_args,
                    "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
                    "-o", audio_path,
                    url,
                ]
                _safe_log(on_log, f"[whisper] using player client {player_client}")
                if player_js_variant:
                    _safe_log(on_log, f"[whisper] using player js variant {player_js_variant}")

                remote_components = os.getenv("YTDLP_REMOTE_COMPONENTS", "ejs:github")
                if remote_components:
                    cmd.extend(["--remote-components", remote_components])
                    _safe_log(on_log, f"[whisper] using remote components {remote_components}")

                if cookies_file and os.path.exists(cookies_file):
                    cmd.extend(["--cookies", cookies_file])
                    _safe_log(on_log, f"[whisper] using cookies file {cookies_file}")
                elif cookies_from_browser:
                    cmd.extend(["--cookies-from-browser", cookies_from_browser])
                    _safe_log(on_log, f"[whisper] using cookies from {cookies_from_browser}")

                result = subprocess.run(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                if result.returncode != 0:
                    last_error = _truncate_bytes(result.stderr)
                    _safe_log(on_log, f"[whisper] yt-dlp failed: {last_error}")
                    if "cookies are no longer valid" in last_error.lower():
                        cmd_no_cookies = [
                            arg for arg in cmd
                            if arg not in ("--cookies", cookies_file, "--cookies-from-browser", cookies_from_browser)
                        ]
                        result = subprocess.run(
                            cmd_no_cookies,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            check=False,
                        )
                        if result.returncode == 0:
                            if result.stderr:
                                _safe_log(on_log, f"[whisper] yt-dlp stderr: {_truncate_bytes(result.stderr)}")
                            break
                    continue
                if result.stderr:
                    _safe_log(on_log, f"[whisper] yt-dlp stderr: {_truncate_bytes(result.stderr)}")
                break
            else:
                if last_error:
                    _safe_log(on_log, f"[whisper] yt-dlp failed after clients: {last_error}")
                return None

            if not os.path.exists(audio_path) or os.path.getsize(audio_path) == 0:
                _safe_log(on_log, "[whisper] audio file missing or empty")
                return None

            result = _get_model().transcribe(audio_path)

        transcript = []
        for seg in result.get("segments", []):
            text = seg.get("text", "").strip()
            if not text:
                continue

            transcript.append({
                "text": text,
                "start": seg.get("start", 0),
                "duration": seg.get("end", 0) - seg.get("start", 0),
            })

        return transcript if transcript else None

    except Exception as e:
        _safe_log(on_log, f"[whisper] error: {e}")
        # 🔥 swallow ALL yt-dlp / ffmpeg / whisper errors
        return None
