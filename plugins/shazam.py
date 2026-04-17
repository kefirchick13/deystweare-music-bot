import asyncio
import os
import shutil
import subprocess
import tempfile

from utils import Shazam


class ShazamHelper:

    @classmethod
    def initialize(cls):
        cls.Shazam = Shazam()

        cls.voice_repository_dir = "repository/Voices"
        if not os.path.isdir(cls.voice_repository_dir):
            os.makedirs(cls.voice_repository_dir, exist_ok=True)

    @staticmethod
    def _ffmpeg_to_wav(input_path: str) -> str:
        """
        Telegram voice = OGG/Opus. ShazamIO внутри опирается на ffmpeg/pydub и часто
        ошибочно трактует поток как MP3 → «invalid mpeg audio header».
        Явно перегоняем в моно WAV 44.1 kHz PCM.
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
    async def recognize(file):
        """
        Распознавание трека по файлу с таймаутом.
        Если Shazam зависает или отвечает слишком долго, возвращаем пустую строку,
        чтобы бот не "висел" бесконечно.
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
                except Exception:
                    return await ShazamHelper.Shazam.recognize_song(path_for_shazam)

            try:
                out = await asyncio.wait_for(_do_recognize(), timeout=20)
            except asyncio.TimeoutError:
                print("Shazam recognize timeout for file:", file)
                return ""
            except Exception as e:
                print("Shazam recognize error:", e)
                return ""

            try:
                status = out.get("status")
                message = out.get("message") or out.get("status", {}).get("msg")
                print("Shazam raw status:", status)
                print("Shazam message:", message)
            except Exception:
                print("Shazam response (raw):", out)

            return ShazamHelper.extract_song_details(out)
        finally:
            if wav_path and os.path.isfile(wav_path):
                try:
                    os.remove(wav_path)
                except OSError:
                    pass

    # Function to extract the Spotify link
    @staticmethod
    def extract_spotify_link(data):
        for provider in data["track"]["hub"]["providers"]:
            if provider["type"] == "SPOTIFY":
                for action in provider["actions"]:
                    if action["type"] == "uri":
                        return action["uri"]
        return None

    @staticmethod
    def extract_song_details(data):

        try:
            music_name = data["track"]["title"]
            artists_name = data["track"]["subtitle"]
        except Exception:
            return ""

        song_details = {
            "music_name": music_name,
            "artists_name": artists_name,
        }
        song_details_string = ", ".join(f"{value}" for value in song_details.values())
        return song_details_string
