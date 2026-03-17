import os
import re
import shutil
from utils import asyncio, YoutubeDL, db


def _ffmpeg_location():
    """Путь к каталогу с ffmpeg/ffprobe (для yt-dlp postprocessors)."""
    exe = shutil.which("ffmpeg")
    if exe:
        return os.path.dirname(exe)
    return "/usr/bin"


def _match_min_duration(info, *, incomplete=False):
    """Отсекаем короткие превью: только треки от 40 сек или с неизвестной длиной."""
    duration = info.get("duration")
    if duration is not None and duration < 40:
        return "Duration too short"
    return None


class SoundCloudAudioDownloader:
    @staticmethod
    async def download(event, file_info, music_quality, download_directory: str,
                       is_playlist: bool = False, spotify_link_info=None):
        """
        Основной вариант: попытка скачать трек с SoundCloud через yt-dlp
        с использованием поиска scsearch:<artist> - <title>.
        Если event=None (prefetch), скачивание без сообщений в чат.
        """
        user_id = event.sender_id if event else None
        filename = file_info['file_name']
        silent = event is None

        download_message = None
        if not silent and not is_playlist:
            bar = "▱" * 12
            text = f"🎵 Скачивание (SoundCloud)\n{bar}\nФормат: {music_quality['format']} · {music_quality['quality']}"
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
                "match_filter": _match_min_duration,
                "postprocessors": [{'key': 'FFmpegExtractAudio', 'preferredcodec': music_quality['format'],
                                    'preferredquality': music_quality['quality']}]
            }

            with YoutubeDL(ydl_opts) as ydl:
                if not silent and not is_playlist and download_message:
                    await download_message.edit("🎵 Скачивание (SoundCloud)\n▰▰▰▰▰▰▱▱▱▱▱▱\nЗагрузка…")
                await asyncio.to_thread(ydl.extract_info, query, download=True)

        async def download_handler():
            try:
                await download_audio_from_sc(query, filename, music_quality)
                return True, download_message
            except Exception as ERR:
                if not silent and event:
                    await event.respond(
                        "Не удалось скачать трек через SoundCloud.\n"
                        f"Подробнее: {ERR}"
                    )
                if user_id is not None:
                    await db.set_file_processing_flag(user_id, 0)
                return False, download_message

        return await download_handler()

    @staticmethod
    async def search_soundcloud(query: str, limit: int = 10):
        """
        Поиск треков на SoundCloud через yt-dlp (scsearch).
        Возвращает (search_results, link_info_by_id):
        - search_results: список dict с track_name, artist_name, release_year, track_id (sc_xxx)
        - link_info_by_id: dict sc_id -> link_info для кэша (extract_data_from_spotify_link и скачивание).
        """
        if not query or limit < 1:
            return [], {}

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        def _extract():
            with YoutubeDL(ydl_opts) as ydl:
                try:
                    # scsearchN:query — поиск в SoundCloud, N результатов
                    info = ydl.extract_info(f"scsearch{limit}:{query}", download=False)
                except Exception:
                    return None
            if not info or info.get("_type") != "playlist":
                return None
            return info.get("entries") or []

        try:
            entries = await asyncio.to_thread(_extract)
        except Exception:
            return [], {}

        if not entries:
            return [], {}

        search_results = []
        link_info_by_id = {}
        # Плейсхолдер обложки для треков без thumbnail
        default_art = "https://a1.sndcdn.com/images/logo_facebook.png"

        for entry in entries[:limit]:
            if not entry:
                continue
            raw_id = entry.get("id")
            url = entry.get("url") or entry.get("webpage_url") or ""
            if raw_id is not None:
                sc_id = str(raw_id)
            elif url and "soundcloud.com" in url:
                sc_id = (re.search(r"soundcloud\.com/[\w-]+/([\w-]+)", url) or re.search(r"/([^/]+)/?$", url))
                sc_id = (sc_id.group(1) if sc_id else url).replace("/", "_")
            else:
                continue
            track_id = f"sc_{sc_id}"

            title = entry.get("title") or "Unknown"
            uploader = entry.get("uploader") or entry.get("artist") or "Unknown"
            duration = entry.get("duration")
            duration_ms = int(duration * 1000) if duration else 0
            url = entry.get("url") or entry.get("webpage_url") or ""
            thumb = entry.get("thumbnail") or default_art

            release_year = "—"
            if entry.get("timestamp"):
                try:
                    from datetime import datetime
                    release_year = str(datetime.utcfromtimestamp(entry["timestamp"]).year)
                except Exception:
                    pass

            search_results.append({
                "track_name": title,
                "artist_name": uploader,
                "release_year": release_year,
                "track_id": track_id,
            })

            link_info_by_id[track_id] = {
                "type": "track",
                "track_name": title,
                "artist_name": uploader,
                "release_year": release_year,
                "track_id": track_id,
                "track_url": url or "#",
                "artist_url": "#",
                "album_name": "—",
                "album_url": "#",
                "image_url": thumb,
                "duration_ms": duration_ms,
                "youtube_link": None,
            }

        return search_results, link_info_by_id

