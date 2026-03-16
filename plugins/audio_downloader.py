import os

from .soundcloud_audio_downloader import SoundCloudAudioDownloader
from .youtube_audio_downloader import YouTubeAudioDownloader


class AudioDownloader:
    """
    Объединяющий класс: сначала пытается скачать трек через SoundCloud,
    если не удалось — пробует YouTube.
    """

    @staticmethod
    async def download_track(
        event,
        music_quality,
        file_info,
        spotify_link_info,
        download_directory: str,
        max_size_mb: int,
        is_playlist: bool = False,
    ):
        file_path = file_info["file_path"]

        # 1. Пытаемся через SoundCloud
        sc_result, sc_message = await SoundCloudAudioDownloader.download(
            event, file_info, music_quality, download_directory, is_playlist, spotify_link_info
        )

        # Если скачалось и файл есть — возвращаем успех
        if sc_result and os.path.isfile(file_path):
            return True, sc_message

        # 2. Если SoundCloud не сработал — пробуем YouTube
        yt_result, yt_message = await YouTubeAudioDownloader.download(
            event, file_info, music_quality, download_directory, max_size_mb, is_playlist, spotify_link_info
        )

        if yt_result and os.path.isfile(file_path):
            return True, yt_message

        return False, yt_message

    @staticmethod
    async def prefetch_track(spotify_link_info, music_quality, file_info, download_directory: str, max_size_mb: int):
        """Предиктивное скачивание без сообщений в чат (event=None). При показе карточки трека."""
        file_path = file_info["file_path"]
        if os.path.isfile(file_path):
            return True
        sc_result, _ = await SoundCloudAudioDownloader.download(
            None, file_info, music_quality, download_directory, is_playlist=True, spotify_link_info=spotify_link_info
        )
        if sc_result and os.path.isfile(file_path):
            return True
        yt_result, _ = await YouTubeAudioDownloader.download(
            None, file_info, music_quality, download_directory, max_size_mb, is_playlist=True,
            spotify_link_info=spotify_link_info
        )
        return bool(yt_result and os.path.isfile(file_path))

