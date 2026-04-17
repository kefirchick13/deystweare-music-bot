import asyncio
import json
import os
import shutil
import subprocess
import tempfile

from utils import Shazam


class ShazamHelper:

    @classmethod
    def initialize(cls):
        # Регион влияет на endpoint Shazam; для RU/СНГ удобнее ru-RU + RU
        lang = os.getenv("SHAZAM_LANGUAGE", "ru-RU")
        country = os.getenv("SHAZAM_ENDPOINT_COUNTRY", "RU")
        cls.Shazam = Shazam(language=lang, endpoint_country=country)

        cls.voice_repository_dir = "repository/Voices"
        if not os.path.isdir(cls.voice_repository_dir):
            os.makedirs(cls.voice_repository_dir, exist_ok=True)

    @staticmethod
    def _ffmpeg_to_wav(input_path: str) -> str:
        """
        Telegram voice = OGG/Opus. Перегоняем в моно WAV 44.1 kHz PCM для стабильного чтения.
        """
        ffmpeg = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
        fd, out_path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        result = subprocess.run(
            [
                ffmpeg,
                "-y",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                input_path,
                "-ac",
                "1",
                "-ar",
                "44100",
                "-c:a",
                "pcm_s16le",
                out_path,
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
        if result.returncode != 0:
            try:
                os.remove(out_path)
            except OSError:
                pass
            err = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(err or f"ffmpeg exited {result.returncode}")

        return out_path

    @staticmethod
    def _pick_track_dict(data: dict):
        """Ответ Shazam v2 часто кладёт трек в matches[0].track, а не в корень."""
        if not isinstance(data, dict):
            return None
        track = data.get("track")
        if isinstance(track, dict) and track.get("title"):
            return track
        matches = data.get("matches")
        if isinstance(matches, list) and matches:
            first = matches[0]
            if isinstance(first, dict):
                t = first.get("track")
                if isinstance(t, dict) and t.get("title"):
                    return t
        return None

    @staticmethod
    async def recognize(file):
        """
        Распознавание трека по файлу с таймаутом.
        """
        wav_path = None
        path_for_shazam = file

        try:
            try:
                wav_path = ShazamHelper._ffmpeg_to_wav(file)
                path_for_shazam = wav_path
            except Exception as conv_err:
                print("Shazam: не удалось нормализовать аудио в WAV, пробуем исходный файл:", conv_err)
                path_for_shazam = file

            async def _do_recognize():
                try:
                    return await ShazamHelper.Shazam.recognize(path_for_shazam)
                except Exception as e1:
                    print("Shazam.recognize (rust) failed:", e1)
                    try:
                        return await ShazamHelper.Shazam.recognize_song(path_for_shazam)
                    except Exception as e2:
                        print("Shazam.recognize_song (legacy) failed:", e2)
                        raise

            try:
                out = await asyncio.wait_for(_do_recognize(), timeout=45)
            except asyncio.TimeoutError:
                print("Shazam recognize timeout for file:", file)
                return ""
            except Exception as e:
                print("Shazam recognize error:", e)
                return ""

            if isinstance(out, dict):
                status = out.get("status")
                msg = out.get("message") or (out.get("status") or {}).get("msg")
                print("Shazam raw status:", status, "message:", msg)
                if not ShazamHelper.extract_song_details(out):
                    # Короткий лог для отладки «нашёлся ответ, но не распарсили»
                    try:
                        preview = json.dumps(out, ensure_ascii=False)[:800]
                        print("Shazam response preview:", preview)
                    except Exception:
                        print("Shazam response (non-json-serializable keys):", list(out.keys()))

            return ShazamHelper.extract_song_details(out)
        finally:
            if wav_path and os.path.isfile(wav_path):
                try:
                    os.remove(wav_path)
                except OSError:
                    pass

    @staticmethod
    def extract_spotify_link(data):
        track = ShazamHelper._pick_track_dict(data)
        hub = track.get("hub") if track else None
        providers = hub.get("providers") if isinstance(hub, dict) else None
        if not providers:
            return None
        for provider in providers:
            if provider["type"] == "SPOTIFY":
                for action in provider["actions"]:
                    if action["type"] == "uri":
                        return action["uri"]
        return None

    @staticmethod
    def extract_song_details(data):
        track = ShazamHelper._pick_track_dict(data)
        if not track:
            return ""

        title = track.get("title")
        subtitle = (track.get("subtitle") or "").strip()
        if not title:
            return ""

        if subtitle:
            return f"{title}, {subtitle}"
        return str(title)
