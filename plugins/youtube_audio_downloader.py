import os
import shutil
from utils import asyncio, YoutubeDL, db


def _ffmpeg_location():
    exe = shutil.which("ffmpeg")
    if exe:
        return os.path.dirname(exe)
    return "/usr/bin"


class YouTubeAudioDownloader:
    @staticmethod
    async def download(event, file_info, music_quality, download_directory: str,
                       max_size_mb: int, is_playlist: bool = False, spotify_link_info=None):
        """
        Скачивание аудио через YouTube (yt-dlp).
        """
        user_id = event.sender_id
        video_url = file_info['video_url']
        filename = file_info['file_name']

        download_message = None
        if not is_playlist:
            text = (
                "Скачиваю аудио через YouTube...\n"
                f"Формат: {music_quality['format']} / Качество: {music_quality['quality']}\n"
                "Это может занять некоторое время, особенно при медленном соединении."
            )
            download_message = await event.respond(text)

        async def get_file_size(video_url):
            ydl_opts = {
                'format': "bestaudio",
                'default_search': 'ytsearch',
                'noplaylist': True,
                "nocheckcertificate": True,
                "quiet": True,
                "geo_bypass": True,
                'get_filesize': True
            }

            with YoutubeDL(ydl_opts) as ydl:
                info_dict = await asyncio.to_thread(ydl.extract_info, video_url, download=False)
                file_size = info_dict.get('filesize', None)
                return file_size

        async def download_audio(video_url, filename, music_quality):
            ydl_opts = {
                'format': "bestaudio",
                'default_search': 'ytsearch',
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
                await download_message.edit("Downloading . . .") if not is_playlist else None
                await asyncio.to_thread(ydl.extract_info, video_url, download=True)

        async def download_handler():
            file_size_task = asyncio.create_task(get_file_size(video_url))
            file_size = await file_size_task

            if file_size and file_size > max_size_mb * 1024 * 1024:
                await event.respond("Ошибка: размер файла больше 50 МБ.\nЗагрузка пропущена.")
                await db.set_file_processing_flag(user_id, 0)
                return False, None

            if not is_playlist:
                await download_message.edit("Downloading . .")

            download_task = asyncio.create_task(download_audio(video_url, filename, music_quality))
            try:
                await download_task
                return True, download_message
            except Exception:
                await event.respond("Something Went Wrong Processing Your Query.")
                await db.set_file_processing_flag(user_id, 0)
                return False, download_message

        return await download_handler()

