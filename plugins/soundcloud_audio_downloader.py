import os
import shutil
from utils import asyncio, YoutubeDL, db


def _ffmpeg_location():
    """Путь к каталогу с ffmpeg/ffprobe (для yt-dlp postprocessors)."""
    exe = shutil.which("ffmpeg")
    if exe:
        return os.path.dirname(exe)
    return "/usr/bin"


class SoundCloudAudioDownloader:
    @staticmethod
    async def download(event, file_info, music_quality, download_directory: str,
                       is_playlist: bool = False, spotify_link_info=None):
        """
        Основной вариант: попытка скачать трек с SoundCloud через yt-dlp
        с использованием поиска scsearch:<artist> - <title>.
        """
        user_id = event.sender_id
        filename = file_info['file_name']

        download_message = None
        if not is_playlist:
            text = (
                "Скачиваю аудио через SoundCloud...\n"
                f"Формат: {music_quality['format']} / Качество: {music_quality['quality']}\n"
                "Это может занять некоторое время, особенно при медленном соединении."
            )
            download_message = await event.respond(text)

        query = f"{spotify_link_info['artist_name']} - {spotify_link_info['track_name']}"

        async def download_audio_from_sc(query, filename, music_quality):
            ydl_opts = {
                'format': "bestaudio",
                'default_search': 'scsearch',
                'noplaylist': True,
                "nocheckcertificate": True,
                "outtmpl": f"{download_directory}/{filename}",
                "quiet": True,
                "addmetadata": True,
                "prefer_ffmpeg": True,
                "ffmpeg_location": _ffmpeg_location(),
                "geo_bypass": True,
                "postprocessors": [{'key': 'FFmpegExtractAudio', 'preferredcodec': music_quality['format'],
                                    'preferredquality': music_quality['quality']}]
            }

            with YoutubeDL(ydl_opts) as ydl:
                await download_message.edit("Downloading from SoundCloud . . .") if not is_playlist else None
                await asyncio.to_thread(ydl.extract_info, query, download=True)

        async def download_handler():
            try:
                await download_audio_from_sc(query, filename, music_quality)
                return True, download_message
            except Exception as ERR:
                await event.respond(
                    "Не удалось скачать трек через SoundCloud.\n"
                    f"Подробнее: {ERR}"
                )
                await db.set_file_processing_flag(user_id, 0)
                return False, download_message

        return await download_handler()

