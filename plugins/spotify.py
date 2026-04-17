import time
import tempfile
import shutil
from run import Button, Buttons
from utils import asyncio, re, os, load_dotenv, combinations
from utils import db, SpotifyException, fast_upload, Any, CachePool
from utils import Image, BytesIO, aiohttp, InputMediaUploadedDocument
from telethon.tl.types import InputDocument
from utils import SpotifyClientCredentials, spotipy, ThreadPoolExecutor, DocumentAttributeAudio
from utils import requests
from .audio_downloader import AudioDownloader
from requests.exceptions import HTTPError, ReadTimeout

# TTL кэша link_info по track_id (не вызывать Spotify API и YouTube search повторно при нажатии "Download")
LINK_INFO_CACHE_TTL_SEC = 30 * 60
# Удалять файлы в repository/Musics старше этого возраста (префетч/кэш; отправленные треки — из sent_file_cache)
PREFETCH_FILE_MAX_AGE_SEC = 20 * 60  # 20 минут

# Длина полоски прогресса (символов)
PROGRESS_BAR_LEN = 12


def _format_upload_progress(done: int, total: int) -> str:
    """Строка для отображения прогресса загрузки в Telegram (progress_bar_function для fast_upload)."""
    if total and total > 0:
        pct = min(100, int(100 * done / total))
        filled = min(PROGRESS_BAR_LEN, int(PROGRESS_BAR_LEN * done / total))
        bar = "▰" * filled + "▱" * (PROGRESS_BAR_LEN - filled)
        return f"📤 Загрузка в Telegram\n{bar} {pct}%"
    return "📤 Загрузка в Telegram\n▱▱▱▱▱▱▱▱▱▱▱▱ 0%"


class SpotifyDownloader:

    @classmethod
    def _load_dotenv_and_create_folders(cls):
        try:
            load_dotenv('config.env')
            cls.SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
            cls.SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
            cls.GENIUS_ACCESS_TOKEN = os.getenv("GENIUS_ACCESS_TOKEN")
        except FileNotFoundError:
            print("Failed to Load .env variables")

        # Create a directory for the download
        cls.download_directory = "repository/Musics"
        if not os.path.isdir(cls.download_directory):
            os.makedirs(cls.download_directory, exist_ok=True)

        cls.download_icon_directory = "repository/Icons"
        if not os.path.isdir(cls.download_icon_directory):
            os.makedirs(cls.download_icon_directory, exist_ok=True)

    @classmethod
    def initialize(cls):
        cls._load_dotenv_and_create_folders()
        cls.MAXIMUM_DOWNLOAD_SIZE_MB = 50
        cls.spotify_account = spotipy.Spotify(client_credentials_manager=
                                              SpotifyClientCredentials(client_id=cls.SPOTIFY_CLIENT_ID,
                                                                       client_secret=cls.SPOTIFY_CLIENT_SECRET))
        cls.GENIUS_API_BASE = "https://api.genius.com"
        cls._link_info_cache = CachePool(ttl_sec=LINK_INFO_CACHE_TTL_SEC)
        cls._sc_link_info_cache = CachePool(ttl_sec=10 * 60)  # link_info по sc_ id, 10 мин, затем очистка
        cls._prefetch_tasks = {}  # file_path -> asyncio.Task (чтобы при Download дождаться префетча)
        cls._run_cleanups()

    @classmethod
    def _run_cleanups(cls):
        """Очистка файлов префетча, иконок и просроченных записей кэша link_info (SoundCloud)."""
        cls._cleanup_old_prefetch_files()
        cls._cleanup_old_icons()
        cls._sc_link_info_cache.cleanup_expired()

    @classmethod
    def _cleanup_old_prefetch_files(cls):
        """Удаляет в repository/Musics файлы старше PREFETCH_FILE_MAX_AGE_SEC. Освобождает место от префетча и старых кэшей."""
        if not os.path.isdir(cls.download_directory):
            return
        now = time.time()
        for name in os.listdir(cls.download_directory):
            path = os.path.join(cls.download_directory, name)
            if not os.path.isfile(path):
                continue
            try:
                if now - os.path.getmtime(path) > PREFETCH_FILE_MAX_AGE_SEC:
                    os.remove(path)
            except OSError:
                pass

    @classmethod
    def _cleanup_old_icons(cls):
        """Удаляет в repository/Icons обложки старше PREFETCH_FILE_MAX_AGE_SEC."""
        if not os.path.isdir(cls.download_icon_directory):
            return
        now = time.time()
        for name in os.listdir(cls.download_icon_directory):
            path = os.path.join(cls.download_icon_directory, name)
            if not os.path.isfile(path):
                continue
            try:
                if now - os.path.getmtime(path) > PREFETCH_FILE_MAX_AGE_SEC:
                    os.remove(path)
            except OSError:
                pass

    @staticmethod
    def is_spotify_link(url):
        pattern = r'https?://open\.spotify\.com/.*'
        return re.match(pattern, url) is not None

    @staticmethod
    def identify_spotify_link_type(spotify_url) -> str:
        # Define a list of all primary resource types supported by Spotify
        resource_types = ['track', 'playlist', 'album', 'artist', 'show', 'episode']

        for resource_type in resource_types:
            try:
                # Dynamically call the appropriate method on the Spotify API client
                resource = getattr(SpotifyDownloader.spotify_account, resource_type)(spotify_url)
                return resource_type
            except (SpotifyException, Exception) as e:
                # Continue to the next resource type if an exception occurs
                continue

        # Return 'none' if no resource type matches
        return 'none'

    @classmethod
    def _get_cached_link_info(cls, track_id: str):
        if not track_id:
            return None
        return cls._link_info_cache.get(track_id)

    @classmethod
    def _set_cached_link_info(cls, track_id: str, link_info: dict):
        if track_id and link_info and link_info.get('type') == 'track':
            cls._link_info_cache.set(track_id, link_info)

    @staticmethod
    async def extract_data_from_spotify_link(event, spotify_url):
        # Результат поиска SoundCloud: track_id = "sc_xxx" — данные берём из кэша
        if isinstance(spotify_url, str) and spotify_url.startswith("sc_"):
            link_info = SpotifyDownloader._sc_link_info_cache.get(spotify_url)
            if link_info:
                return link_info
            await event.respond("Срок действия результата поиска истёк. Выполните поиск заново.")
            return {}

        # Identify the type of Spotify link to handle the data extraction accordingly
        link_type = SpotifyDownloader.identify_spotify_link_type(spotify_url)

        try:
            if link_type == "track":
                # Extract track information and construct the link_info dictionary
                track_info = SpotifyDownloader.spotify_account.track(spotify_url)
                artists = track_info['artists']
                album = track_info['album']
                link_info = {
                    'type': "track",
                    'track_name': track_info['name'],
                    'artist_name': ', '.join(artist['name'] for artist in artists),
                    'artist_ids': [artist['id'] for artist in artists],
                    'artist_url': artists[0]['external_urls']['spotify'],
                    'album_name': album['name'].translate(str.maketrans('', '', '()[]')),
                    'album_url': album['external_urls']['spotify'],
                    'release_year': album['release_date'].split('-')[0],
                    'image_url': album['images'][0]['url'],
                    'track_id': track_info['id'],
                    'isrc': track_info['external_ids']['isrc'],
                    'track_url': track_info['external_urls']['spotify'],
                    'youtube_link': None,  # Placeholder, will be resolved below
                    'preview_url': track_info.get('preview_url'),
                    'duration_ms': track_info['duration_ms'],
                    'track_number': track_info['track_number'],
                    'is_explicit': track_info['explicit']
                }

                # Attempt to enhance track info with additional external data (e.g., YouTube link)
                link_info['youtube_link'] = await SpotifyDownloader.extract_yt_video_info(link_info)
                SpotifyDownloader._set_cached_link_info(link_info['track_id'], link_info)
                return link_info

            elif link_type == "playlist":
                # Extract playlist information and compile playlist tracks into a dictionary
                playlist_info = SpotifyDownloader.spotify_account.playlist(spotify_url)

                playlist_info_dict = {
                    'type': 'playlist',
                    'playlist_name': playlist_info['name'],
                    'playlist_id': playlist_info['id'],
                    'playlist_url': playlist_info['external_urls']['spotify'],
                    'playlist_owner': playlist_info['owner']['display_name'],
                    'playlist_image_url': playlist_info['images'][0]['url'] if playlist_info['images'] else None,
                    'playlist_followers': playlist_info['followers']['total'],
                    'playlist_public': playlist_info['public'],
                    'playlist_tracks_total': playlist_info['tracks']['total'],
                }
                return playlist_info_dict

            else:
                # Handle unsupported Spotify link types
                link_info = {'type': link_type}
                print(f"Unsupported Spotify link type provided: {spotify_url}")
                return link_info

        except Exception as e:
            # Log and handle any errors encountered during information extraction
            print(f"Error extracting Spotify information: {e}")
            await event.respond("An error occurred while processing the Spotify link. Please try again.")
            return {}

    @staticmethod
    async def extract_yt_video_info(spotify_link_info):
        if spotify_link_info is None:
            return None

        video_url = spotify_link_info.get('youtube_link')
        if video_url:
            return video_url

        artist_name = spotify_link_info["artist_name"]
        track_name = spotify_link_info["track_name"]
        release_year = spotify_link_info["release_year"]
        track_duration = spotify_link_info.get("duration_ms", 0) / 1000
        album_name = spotify_link_info.get("album_name", "")

        queries = [
            f'"{artist_name}" "{track_name}" lyrics {release_year}',
            f'"{track_name}" by "{artist_name}" {release_year}',
            f'"{artist_name}" "{track_name}" "{album_name}" {release_year}',
        ]

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'ignoreerrors': True,
            'ytsearch': 3,  # Limit the number of search results
            'skip_download': True,
            'format': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best',
            'noplaylist': True,  # Disable playlist processing
            'nocheckcertificate': True,  # Disable SSL certificate verification
            'cachedir': False  # Disable caching
        }

        executor = ThreadPoolExecutor(max_workers=16)  # Use 16 workers for the blocking I/O operation
        stop_event = asyncio.Event()

        async def search_query(query):
            def extract_info_blocking():
                with YoutubeDL(ydl_opts) as ydl:
                    try:
                        info = ydl.extract_info(f'ytsearch:{query}', download=False)
                        entries = info.get('entries', [])
                        return entries
                    except Exception:
                        return []

            entries = await asyncio.get_running_loop().run_in_executor(executor, extract_info_blocking)

            if not stop_event.is_set():
                for video_info in entries:
                    video_url = video_info.get('webpage_url')
                    video_duration = video_info.get('duration', 0)

                    # Compare the video duration with the track duration from Spotify
                    duration_diff = abs(video_duration - track_duration)
                    if duration_diff <= 35:
                        stop_event.set()
                        return video_url

            return None

        search_tasks = [asyncio.create_task(search_query(query)) for query in queries]
        search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

        for result in search_results:
            if isinstance(result, Exception):
                continue
            if result is not None:
                return result

        return None

    @staticmethod
    async def download_and_send_spotify_info(event, is_query: bool = True) -> bool:
        user_id = event.sender_id
        waiting_message = None
        if is_query:
            waiting_message = await event.respond('⏳')
            query_data = str(event.data)
            spotify_link = query_data.split("/")[-1][:-1]
        else:
            spotify_link = str(event.message.text)

        # Ensure the user's data is up-to-date
        if not await db.get_user_updated_flag(user_id):
            await event.respond(
                "Our bot has been updated. Please restart the bot with the /start command."
            )
            return True

        link_info = await SpotifyDownloader.extract_data_from_spotify_link(event, spotify_url=spotify_link)
        if link_info["type"] == "track":
            await waiting_message.delete() if is_query else None
            return await SpotifyDownloader.send_track_info(event.client, event, link_info)
        elif link_info["type"] == "playlist":
            return await SpotifyDownloader.send_playlist_info(event.client, event, link_info)
        else:
            await event.respond(
                f"""Unsupported Spotify link type.\n\nThe Bot is currently supports:\n- track \n- playlist\n\nYou 
                requested: {link_info["type"]} """)
            return False

    @staticmethod
    async def fetch_and_save_playlist_image(playlist_id, playlist_image_url):
        icon_name = f"{playlist_id}.jpeg"
        icon_path = os.path.join(SpotifyDownloader.download_icon_directory, icon_name)

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(playlist_image_url) as response:
                    if response.status == 200:
                        image_data = await response.read()
                        img = Image.open(BytesIO(image_data))
                        img.save(icon_path)
                        return icon_path
                    else:
                        print(f"Failed to download playlist image. Status code: {response.status}")
        except Exception as e:
            print(f"Error downloading or saving playlist image: {e}")

        return None

    @staticmethod
    async def send_playlist_info(client, event, link_info):
        playlist_image_url = link_info.get('playlist_image_url')
        playlist_name = link_info.get('playlist_name', 'Unavailable')
        playlist_id = link_info.get('playlist_id', 'Unavailable')
        playlist_url = link_info.get('playlist_url', 'Unavailable')
        playlist_owner = link_info.get('playlist_owner', 'Unavailable')
        total_tracks = link_info.get('playlist_tracks_total', 0)
        collaborative = 'Yes' if link_info.get('collaborative', False) else 'No'
        public = 'Yes' if link_info.get('playlist_public', False) else 'No'
        followers = link_info.get('playlist_followers', 'Unavailable')

        # Construct the playlist information text
        playlist_info = (
            f"🎧 **Playlist: {playlist_name}** 🎶\n\n"
            f"---\n\n"
            f"**Details:**\n\n"

            f"  - 👤 Owner: {playlist_owner}\n"
            f"  - 👥 Followers: {followers}\n"

            f"  - 🎵 Total Tracks: {total_tracks}\n"
            f"  - 🤝 Collaborative: {collaborative}\n"
            f"  - 🌐 Public: {public}\n"

            f"  - 🎧 Playlist URL: [Listen On Spotify]({playlist_url})\n"
            f"---\n\n"
            f"**Enjoy the music!** 🎶"
        )

        # Buttons for interactivity
        buttons = [
            [Button.inline("Download All Tracks Inside [mp3]", data=f"spotify/dl/playlist/{playlist_id}/all")],
            [Button.inline("Download Top 10", data=f"spotify/dl/playlist/{playlist_id}/10")],
            [Button.inline("Search Tracks inside", data=f"spotify/s/playlist/{playlist_id}")],
            [Button.inline("Cancel", data=b"cancel")]
        ]

        # Handle the playlist image if exists
        if playlist_image_url:
            icon_path = await SpotifyDownloader.fetch_and_save_playlist_image(playlist_id, playlist_image_url)
            if icon_path:
                sent_message = await client.send_file(
                    event.chat_id,
                    icon_path,
                    caption=playlist_info,
                    parse_mode='Markdown',
                    buttons=buttons,
                )
            else:
                await event.respond(playlist_info, parse_mode='Markdown', buttons=buttons)
        else:
            await event.respond(playlist_info, parse_mode='Markdown', buttons=buttons)

        return True

    @staticmethod
    async def download_icon(link_info):
        track_name = link_info['track_name']
        artist_name = link_info['artist_name']
        image_url = link_info.get("image_url")

        icon_name = f"{track_name} - {artist_name}.jpeg".replace("/", " ")
        icon_path = os.path.join(SpotifyDownloader.download_icon_directory, icon_name)

        if not image_url:
            # SoundCloud без обложки — используем плейсхолдер
            default_path = os.path.join(SpotifyDownloader.download_icon_directory, "default_soundcloud.jpeg")
            if not os.path.isfile(default_path):
                placeholder_url = "https://a1.sndcdn.com/images/logo_facebook.png"
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(placeholder_url) as response:
                            if response.status == 200:
                                image_data = await response.read()
                                img = Image.open(BytesIO(image_data))
                                img.save(default_path)
                except Exception as e:
                    print(f"Failed to download SoundCloud placeholder: {e}")
            return default_path if os.path.isfile(default_path) else icon_path

        if not os.path.isfile(icon_path):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(image_url) as response:
                        if response.status == 200:
                            image_data = await response.read()
                            img = Image.open(BytesIO(image_data))
                            img.save(icon_path)
                        else:
                            print(
                                f"Failed to download track image for {track_name} - {artist_name}. Status code: {response.status}")
            except Exception as e:
                print(f"Failed to download or save track image for {track_name} - {artist_name}: {e}")
        return icon_path

    @staticmethod
    async def send_track_info(client, event, link_info):
        user_id = event.sender_id
        music_quality = await db.get_user_music_quality(user_id)
        downloading_core = await db.get_user_downloading_core(user_id)

        def build_file_path(artist, track_name, quality_info, format, make_dir=False):
            filename = f"{artist} - {track_name}".replace("/", "")
            filename += f"-{quality_info['quality']}"
            directory = os.path.join(SpotifyDownloader.download_directory, filename)
            if make_dir and not os.path.exists(directory):
                os.makedirs(directory)
            return f"{directory}.{quality_info['format']}"

        def is_track_local(artist_names, track_name):
            for r in range(1, len(artist_names) + 1):
                for combination in combinations(artist_names, r):
                    file_path = build_file_path(", ".join(combination), track_name, music_quality,
                                                music_quality['format'])
                    if os.path.isfile(file_path):
                        return True, file_path
            return False, None

        artist_names = link_info['artist_name'].split(', ')
        is_local, file_path = is_track_local(artist_names, link_info['track_name'])

        # Предиктивно начинаем скачивание в фоне — к моменту нажатия "Download" файл может быть готов
        if not is_local:
            file_path_prefetch, filename_prefetch, _ = SpotifyDownloader._determine_file_path(link_info, music_quality)
            file_info_prefetch = {
                "file_name": filename_prefetch,
                "file_path": file_path_prefetch,
                "icon_path": SpotifyDownloader._get_icon_path(link_info),
                "video_url": link_info.get('youtube_link'),
            }
            task = asyncio.create_task(
                AudioDownloader.prefetch_track(
                    link_info, music_quality, file_info_prefetch,
                    SpotifyDownloader.download_directory,
                    SpotifyDownloader.MAXIMUM_DOWNLOAD_SIZE_MB,
                )
            )
            SpotifyDownloader._prefetch_tasks[file_path_prefetch] = task
            def _remove_prefetch(fp, done_task):
                if SpotifyDownloader._prefetch_tasks.get(fp) is done_task:
                    SpotifyDownloader._prefetch_tasks.pop(fp, None)
            task.add_done_callback(lambda t, fp=file_path_prefetch: _remove_prefetch(fp, t))

        icon_path = await SpotifyDownloader.download_icon(link_info)

        is_soundcloud = (link_info.get("track_id") or "").startswith("sc_")

        if is_soundcloud:
            SpotifyInfoButtons = [
                [Button.inline("Download Track", data=f"spotify/dl/music/{link_info['track_id']}")],
                [Button.url("Listen On SoundCloud", url=link_info.get("track_url") or "#")],
                [Button.inline("Cancel", data=b"cancel")]
            ]
            caption = (
                f"**🎧 Title:** [{link_info['track_name']}]({link_info.get('track_url', '#')})\n"
                f"**🎤 Artist:** {link_info['artist_name']}\n"
                f"**🗓 Release:** {link_info.get('release_year', '—')}\n"
            )
        else:
            SpotifyInfoButtons = [
                [Button.inline("Download Track", data=f"spotify/dl/music/{link_info['track_id']}")],
                [Button.inline("Artist Info", data=f"spotify/artist/{link_info['track_id']}")],
                [Button.inline("Lyrics", data=f"spotify/lyrics/{link_info['track_id']}")],
                [Button.url("Listen On Spotify", url=link_info["track_url"]),
                 Button.url("Listen On Youtube", url=link_info['youtube_link']) if link_info.get(
                     'youtube_link') else Button.inline("Listen On Youtube", data=b"unavailable_feature")],
                [Button.inline("Cancel", data=b"cancel")]
            ]
            caption = (
                f"**🎧 Title:** [{link_info['track_name']}]({link_info['track_url']})\n"
                f"**🎤 Artist:** [{link_info['artist_name']}]({link_info['artist_url']})\n"
                f"**💽 Album:** [{link_info['album_name']}]({link_info['album_url']})\n"
                f"**🗓 Release Year:** {link_info['release_year']}\n"
            )

        try:
            await client.send_file(
                event.chat_id,
                icon_path,
                caption=caption,
                parse_mode='Markdown',
                buttons=SpotifyInfoButtons
            )
            return True
        except Exception as Err:
            print(f"Failed to send track info: {Err}")
            return False

    @staticmethod
    async def send_local_file(event, file_info, spotify_link_info, is_playlist: bool = False) -> bool:
        user_id = event.sender_id
        upload_status_message = None
        if not is_playlist:
            upload_status_message = await event.reply("📤 Загрузка в Telegram\n▱▱▱▱▱▱▱▱▱▱▱▱ 0%")

        try:
            async with event.client.action(event.chat_id, 'document'):
                await SpotifyDownloader._upload_file(
                    event, file_info, spotify_link_info, is_playlist,
                    upload_status_message=upload_status_message,
                )

        except Exception as e:
            # Handle exceptions and provide feedback
            await db.set_file_processing_flag(user_id, 0)  # Reset file processing flag
            await event.respond(f"Unfortunately, uploading failed.\nReason: {e}") if not is_playlist else None
            return False  # Returning False signifies the operation didn't complete successfully

        if not is_playlist:
            await upload_status_message.delete()

            # Reset file processing flag after completion
            await db.set_file_processing_flag(user_id, 0)

        await db.add_or_increment_song(spotify_link_info['track_name'])
        # Indicate successful upload operation
        return True

    @staticmethod
    async def _upload_file(event, file_info, spotify_link_info, playlist: bool = False,
                           upload_status_message=None):

        # У одиночного трека обложка уже загружена при показе карточки; у плейлиста — докачиваем при необходимости
        if playlist and not os.path.exists(file_info['icon_path']):
            await SpotifyDownloader.download_icon(spotify_link_info)

        file_path = file_info['file_path']
        icon_path = file_info['icon_path']
        caption = (
            f"🎵 **{spotify_link_info['track_name']}** — **{spotify_link_info['artist_name']}**\n"
            "@lumen_portal_bot"
        )

        # Для одного трека пробуем отправить из кэша (мгновенно, без повторной загрузки)
        if not playlist:
            cache_key = f"track_{spotify_link_info.get('track_id', '')}_{file_info['file_name']}"
            cached = await db.get_sent_file(cache_key)
            if cached:
                try:
                    doc_id, access_hash, file_ref = cached
                    await event.client.send_file(
                        event.chat_id,
                        InputDocument(id=doc_id, access_hash=access_hash, file_reference=file_ref),
                        caption=caption,
                        supports_streaming=True,
                        force_document=False,
                    )
                    return
                except Exception:
                    await db.delete_sent_file(cache_key)

        # Копируем в временный файл и загружаем его — чтобы содержимое не менялось во время
        # чтения (MD5 check-sums do not match при гонке с префетчем/записью).
        upload_path = file_path
        temp_path = None
        if not playlist and os.path.isfile(file_path):
            # Ждём стабилизации размера (файл мог ещё дописываться после префетча/скачивания)
            for _ in range(3):
                try:
                    size = os.path.getsize(file_path)
                except OSError:
                    break
                await asyncio.sleep(1)
                try:
                    if os.path.getsize(file_path) == size:
                        break
                except OSError:
                    break
            try:
                fd, temp_path = tempfile.mkstemp(suffix=".mp3", prefix="upload_")
                os.close(fd)
                shutil.copy2(file_path, temp_path)
                upload_path = temp_path
            except OSError:
                pass

        try:
            if not playlist:
                uploaded_file = await fast_upload(
                    client=event.client,
                    file_location=upload_path,
                    reply=upload_status_message,
                    name=file_info['file_name'],
                    progress_bar_function=_format_upload_progress,
                )
            else:
                uploaded_file = None

            uploaded_file = await event.client.upload_file(uploaded_file if not playlist else upload_path)
            uploaded_thumbnail = await event.client.upload_file(icon_path)

            duration_sec = int(spotify_link_info.get('duration_ms', 0) / 1000)
            audio_attributes = DocumentAttributeAudio(
                duration=duration_sec,
                title=f"{spotify_link_info['track_name']} - {spotify_link_info['artist_name']}",
                performer="@lumen_portal_bot",
                waveform=None,
                voice=False
            )

            file_name = file_info.get('file_name', '') or ''
            mime_type = 'audio/flac' if file_name.lower().endswith('.flac') else 'audio/mpeg'
            media = InputMediaUploadedDocument(
                file=uploaded_file,
                thumb=uploaded_thumbnail,
                mime_type=mime_type,
                attributes=[audio_attributes],
            )

            sent_msg = await event.client.send_file(
                event.chat_id,
                media,
                caption=caption,
                supports_streaming=True,
                force_document=False,
                thumb=icon_path
            )

            # Сохраняем document в кэш — при следующем запросе того же трека отправим без загрузки
            if not playlist and sent_msg and sent_msg.media and getattr(sent_msg.media, 'document', None):
                doc = sent_msg.media.document
                await db.set_sent_file(
                    cache_key,
                    doc.id,
                    doc.access_hash,
                    getattr(doc, 'file_reference', None) or b''
                )
        finally:
            if temp_path and os.path.isfile(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    @staticmethod
    # youtube / soundcloud логика вынесена в отдельные классы
    @staticmethod
    async def download_spotify_file_and_send(event) -> bool:

        user_id = event.sender_id

        query_data = str(event.data)
        is_playlist = True if query_data.split("/")[-3] == "playlist" else False

        if is_playlist:
            spotify_link = query_data.split("/")[-2]
        else:
            spotify_link = query_data.split("/")[-1][:-1]


        fetch_message = await event.respond("Fetching information... Please wait.")
        # Для трека сначала проверяем кэш (если пользователь только что смотрел карточку и нажал Download)
        if not is_playlist:
            track_id = spotify_link.split("/")[-1].split("?")[0] if "/" in spotify_link else spotify_link
            spotify_link_info = SpotifyDownloader._get_cached_link_info(track_id)
        else:
            spotify_link_info = None
        if not spotify_link_info:
            spotify_link_info = await SpotifyDownloader.extract_data_from_spotify_link(event, spotify_link)

        await db.set_file_processing_flag(user_id, 1)
        await fetch_message.delete()

        if spotify_link_info and spotify_link_info.get('type') == "track":
            return await SpotifyDownloader.download_track(event, spotify_link_info)
        elif spotify_link_info['type'] == "playlist":
            return await SpotifyDownloader.download_playlist(event, spotify_link_info,
                                                             number_of_downloads=query_data.split("/")[-1][:-1])

    @staticmethod
    async def download_track(event, spotify_link_info, is_playlist: bool = False):

        user_id = event.sender_id

        music_quality = await db.get_user_music_quality(user_id)
        # Для стабильности скачивания треков Spotify здесь используем путь через yt-dlp,
        # а в качестве резервного варианта позже пробуем SoundCloud.
        spotdl = False

        file_path, filename, is_local = SpotifyDownloader._determine_file_path(spotify_link_info, music_quality)

        file_info = {
            "file_name": filename,
            "file_path": file_path,
            "icon_path": SpotifyDownloader._get_icon_path(spotify_link_info),
            "is_local": is_local,
            "video_url": spotify_link_info.get('youtube_link')
        }

        if is_local:
            return await SpotifyDownloader.send_local_file(event, file_info, spotify_link_info, is_playlist)
        else:
            return await SpotifyDownloader._handle_download(event, spotify_link_info, music_quality, file_info,
                                                            spotdl, is_playlist)

    @staticmethod
    async def _handle_download(event, spotify_link_info, music_quality, file_info, spotdl, is_playlist):
        file_path = file_info["file_path"]
        # Файл мог появиться от префетча — тогда сразу отправляем без повторного скачивания
        if os.path.isfile(file_path):
            return await SpotifyDownloader.send_local_file(event, file_info, spotify_link_info, is_playlist)
        # Префетч уже запущен — ждём его и берём файл оттуда (таймаут 2 мин)
        prefetch_task = SpotifyDownloader._prefetch_tasks.get(file_path)
        if prefetch_task is not None:
            try:
                await asyncio.wait_for(prefetch_task, timeout=120)
            except (asyncio.TimeoutError, Exception):
                pass
            if os.path.isfile(file_path):
                return await SpotifyDownloader.send_local_file(event, file_info, spotify_link_info, is_playlist)
        if not spotdl:
            # Основная логика скачивания вынесена в AudioDownloader:
            # сначала SoundCloud, если не получилось — YouTube.
            result, download_message = await AudioDownloader.download_track(
                event,
                music_quality,
                file_info,
                spotify_link_info,
                SpotifyDownloader.download_directory,
                SpotifyDownloader.MAXIMUM_DOWNLOAD_SIZE_MB,
                is_playlist,
            )

            if os.path.isfile(file_path) and result:
                if not is_playlist and download_message:
                    await download_message.edit("🎵 Скачано\n▰▰▰▰▰▰▰▰▰▰▰▰\nОтправка…")
                    await download_message.delete()

                send_file_result = await SpotifyDownloader.send_local_file(
                    event, file_info, spotify_link_info, is_playlist
                )
                return send_file_result

            return False

        # spotdl‑ветка пока не используется, но оставлена для возможного расширения
        result, message = await SpotifyDownloader.download_spotdl(event, music_quality, spotify_link_info)
        if not result:
            result, message = await SpotifyDownloader.download_spotdl(
                event, music_quality, spotify_link_info, is_playlist, message, audio_option="soundcloud"
            )
            if not result:
                result, _ = await SpotifyDownloader.download_spotdl(
                    event, music_quality, spotify_link_info, is_playlist, message, audio_option="youtube"
                )
        if result and message:
            return await SpotifyDownloader.send_local_file(event, file_info, spotify_link_info, is_playlist)
        return False

    @staticmethod
    def _get_icon_path(spotify_link_info):
        icon_name = f"{spotify_link_info['track_name']} - {spotify_link_info['artist_name']}.jpeg".replace("/", " ")
        return os.path.join(SpotifyDownloader.download_icon_directory, icon_name)

    @staticmethod
    def _determine_file_path(spotify_link_info, music_quality):
        artist_names = spotify_link_info['artist_name'].split(', ')
        for r in range(1, len(artist_names) + 1):
            for combination in combinations(artist_names, r):
                filename = f"{', '.join(combination)} - {spotify_link_info['track_name']}".replace("/", "")
                filename += f"-{music_quality['quality']}"
                file_path = os.path.join(SpotifyDownloader.download_directory, f"{filename}.{music_quality['format']}")
                if os.path.isfile(file_path):
                    return file_path, filename, True
        filename = f"{spotify_link_info['artist_name']} - {spotify_link_info['track_name']}".replace("/", "")
        filename += f"-{music_quality['quality']}"
        return os.path.join(SpotifyDownloader.download_directory,
                            f"{filename}.{music_quality['format']}"), filename, False

    @staticmethod
    async def download_playlist(event, spotify_link_info, number_of_downloads: str):
        playlist_id = spotify_link_info["playlist_id"]
        music_quality = None

        await db.set_file_processing_flag(event.sender_id, 1)

        if number_of_downloads == "10":
            tracks_info = await SpotifyDownloader.get_playlist_tracks(playlist_id, as_link_info=True)
        elif number_of_downloads == "all":
            music_quality = await db.get_user_music_quality(event.sender_id)
            new_music_quality = {'format': "mp3", 'quality': 320}
            await db.set_user_music_quality(event.sender_id, new_music_quality)
            tracks_info = await SpotifyDownloader.get_playlist_tracks(playlist_id, get_all=True, as_link_info=True)
        else:
            await db.set_file_processing_flag(event.sender_id, 0)
            return await event.respond("Sorry, Something went wrong.\ntry again later.")

        start_message = await event.respond("Checking the playlist ....")

        batch_size = 10
        track_batches = [tracks_info[i:i + batch_size] for i in range(0, len(tracks_info), batch_size)]
        download_tasks = []

        await start_message.edit("Sending musics.... Please Hold on.")

        for batch in track_batches:
            download_tasks.extend([
                SpotifyDownloader.download_track(event, link_info, is_playlist=True)
                for link_info in batch
            ])

            # Wait for all downloads in the batch to complete before proceeding to the next batch
            await asyncio.gather(*download_tasks)
            download_tasks.clear()  # Clear completed tasks

        await start_message.delete()
        if music_quality is not None:
            await db.set_user_music_quality(event.sender_id, music_quality)
        await db.set_file_processing_flag(event.sender_id, 0)
        return await event.respond("Enjoy!\n\nOur bot is OpenSource.", buttons=Buttons.source_code_button)

    @staticmethod
    async def search_spotify_based_on_user_input(query, limit=10):
        results = SpotifyDownloader.spotify_account.search(q=query, limit=limit)

        extracted_details = []

        for result in results['tracks']['items']:
            # Extracting track name, artist's name, release year, and track ID
            track_name = result['name']
            artist_name = result['artists'][0]['name']  # Assuming the first artist is the primary one
            release_year = result['album']['release_date']
            track_id = result['id']

            # Append the extracted details to the list
            extracted_details.append({
                "track_name": track_name,
                "artist_name": artist_name,
                "release_year": release_year.split("-")[0],
                "track_id": track_id
            })

        return extracted_details

    @staticmethod
    async def search_soundcloud_fallback(query: str, limit: int = 10):
        """
        Поиск через SoundCloud (yt-dlp). Результаты кладутся в _sc_link_info_cache (TTL как у файлов/обложек).
        Возвращает список того же формата, что и search_spotify_based_on_user_input,
        или пустой список при ошибке/пустом результате.
        """
        from .soundcloud_audio_downloader import SoundCloudAudioDownloader
        SpotifyDownloader._sc_link_info_cache.cleanup_expired()
        try:
            results, link_info_by_id = await SoundCloudAudioDownloader.search_soundcloud(query, limit=limit)
        except Exception:
            return []
        for track_id, link_info in (link_info_by_id or {}).items():
            SpotifyDownloader._sc_link_info_cache.set(track_id, link_info)
        return results

    @staticmethod
    async def send_30s_preview(event):
        try:
            query_data = str(event.data)
            preview_url = "https://p.scdn.co/mp3-preview/" + query_data.split("/")[-1][:-1]
            await event.respond(file=preview_url)
        except Exception as Err:
            await event.respond(f"Sorry, Something went wrong:\nError\n{str(Err)}")

    @staticmethod
    async def send_artists_info(event):
        query_data = str(event.data)
        track_id = query_data.split("/")[-1][:-1]
        if (track_id or "").startswith("sc_"):
            await event.respond("Доступно только для треков из Spotify.")
            return
        track_info = SpotifyDownloader.spotify_account.track(track_id=track_id)
        artist_ids = [artist["id"] for artist in track_info['artists']]
        artist_details = []

        def format_number(number):
            if number >= 1000000000:
                return f"{number // 1000000000}.{(number % 1000000000) // 100000000}B"
            elif number >= 1000000:
                return f"{number // 1000000}.{(number % 1000000) // 100000}M"
            elif number >= 1000:
                return f"{number // 1000}.{(number % 1000) // 100}K"
            else:
                return str(number)

        for artist_id in artist_ids:
            artist = SpotifyDownloader.spotify_account.artist(artist_id.replace("'", ""))
            followers_total = artist.get('followers', {}).get('total', 0)

            artist_details.append({
                'name': artist.get('name', 'Unknown'),
                'followers': followers_total,
                'genres': artist.get('genres', []),
                'external_url': artist.get('external_urls', {}).get('spotify', '')
            })

        # Create a professional artist info message with more details and formatting
        message = "🎤 <b>Artists Information</b> :\n\n"
        for artist in artist_details:
            message += f"🌟 <b>Artist Name:</b> {artist['name']}\n"

            # Followers: если 0 или None, показываем 'Unknown'
            followers_value = artist.get('followers') or 0
            followers_text = format_number(followers_value) if followers_value > 0 else "Unknown"
            message += f"👥 <b>Followers:</b> {followers_text}\n"

            # Genres: если список пустой, не выводим строку
            if artist['genres']:
                message += f"🎵 <b>Genres:</b> {', '.join(artist['genres'])}\n"

            message += f"🔗 <b>Spotify URL:</b> <a href='{artist['external_url']}'>Spotify Link</a>\n\n"
            message += "───────────\n\n"

        # Create buttons with URLs
        artist_buttons = [
            [Button.url(f"🎧 {artist['name']}", artist['external_url'])]
            for artist in artist_details
        ]
        artist_buttons.append([Button.inline("Remove", data='cancel')])

        await event.respond(message, parse_mode='html', buttons=artist_buttons)

    @staticmethod
    async def send_music_lyrics(event):
        MAX_MESSAGE_LENGTH = 4096  # Telegram's maximum message length
        SECTION_HEADER_PATTERN = r'\[.+?\]'  # Pattern to match section headers

        query_data = str(event.data)
        track_id = query_data.split("/")[-1][:-1]
        if (track_id or "").startswith("sc_"):
            await event.respond("Доступно только для треков из Spotify.")
            return

        waiting_message = await event.respond("Searching For Lyrics in Genius ....")

        try:
            track_info = SpotifyDownloader.spotify_account.track(track_id=track_id)
        except ReadTimeout:
            await waiting_message.delete()
            return await event.respond(
                "Не удалось получить информацию о треке от Spotify (таймаут).\n"
                "Пожалуйста, попробуйте ещё раз чуть позже."
            )
        except Exception as Err:
            await waiting_message.delete()
            return await event.respond(
                f"Произошла ошибка при обращении к Spotify API.\nПодробнее: {Err}"
            )

        artist_names = ",".join(artist['name'] for artist in track_info['artists'])

        # Запрос к Genius API через GET /search, затем при желании /songs/:id
        headers = {"Authorization": f"Bearer {SpotifyDownloader.GENIUS_ACCESS_TOKEN}"}
        search_params = {
            "q": f'{track_info["name"]} {artist_names}'
        }

        try:
            search_resp = requests.get(
                f"{SpotifyDownloader.GENIUS_API_BASE}/search",
                headers=headers,
                params=search_params,
                timeout=10,
            )
            search_resp.raise_for_status()
            search_data = search_resp.json()
        except HTTPError:
            await waiting_message.delete()
            return await event.respond(
                "К сожалению, сейчас не удалось получить текст этой песни (ошибка Genius API)."
            )
        except Exception as Err:
            await waiting_message.delete()
            return await event.respond(
                f"Произошла ошибка при обращении к Genius API.\nПодробнее: {Err}"
            )

        hits = search_data.get("response", {}).get("hits", [])
        if not hits:
            await waiting_message.delete()
            return await event.respond("Sorry, I couldn't find the lyrics for this track.")

        song_info = hits[0].get("result", {})
        # Попробуем забрать страницу с текстом (Genius API не отдаёт голый текст); здесь предполагается,
        # что где‑то ещё у тебя реализован парсинг страницы или внешний сервис.
        # Пока оставляем как заглушку и возвращаем ссылку на текст.

        song_url = song_info.get("url")
        if song_url:
            await waiting_message.delete()
            return await event.respond(
                f"Текст песни доступен по ссылке:\n{song_url}",
                buttons=[Button.inline("Remove", data='cancel')],
            )

        # Старый путь с разбивкой на части больше не используется, т.к. API не отдаёт готовый текст.
        # Оставляем на всякий случай как fallback, но фактически сюда не попадём.
        song = None
        if song:
            await waiting_message.delete()
            lyrics = song.lyrics

            if not lyrics:
                error_message = "Sorry, I couldn't find the lyrics for this track."
                return await event.respond(error_message)

            # Remove 'Embed' and the first line of the lyrics
            lyrics = song.lyrics.strip().split('\n', 1)[-1]
            lyrics = lyrics.replace('Embed', '').strip()

            metadata = f"**Song:** {track_info['name']}\n**Artist:** {artist_names}\n\n"

            # Split the lyrics into multiple messages if necessary
            lyrics_chunks = []
            current_chunk = ""
            section_lines = []
            for line in lyrics.split('\n'):
                if re.match(SECTION_HEADER_PATTERN, line) or not section_lines:
                    if section_lines:
                        section_text = '\n'.join(section_lines)
                        if len(current_chunk) + len(section_text) + 2 <= MAX_MESSAGE_LENGTH:
                            current_chunk += section_text + "\n"
                        else:
                            lyrics_chunks.append(f"```{current_chunk.strip()}```")
                            current_chunk = section_text + "\n"
                    section_lines = [line]
                else:
                    section_lines.append(line)

            # Add the last section to the chunks
            if section_lines:
                section_text = '\n'.join(section_lines)
                if len(current_chunk) + len(section_text) + 2 <= MAX_MESSAGE_LENGTH:
                    current_chunk += section_text + "\n"
                else:
                    lyrics_chunks.append(f"```{current_chunk.strip()}```")
                    current_chunk = section_text + "\n"
            if current_chunk:
                lyrics_chunks.append(f"```{current_chunk.strip()}```")

            for i, chunk in enumerate(lyrics_chunks, start=1):
                page_header = f"Page {i}/{len(lyrics_chunks)}\n"
                if chunk == "``````":
                    await waiting_message.delete() if waiting_message is not None else None
                    error_message = "Sorry, I couldn't find the lyrics for this track."
                    return await event.respond(error_message)
                message = metadata + chunk + page_header
                await event.respond(message, buttons=[Button.inline("Remove", data='cancel')])
        else:
            await waiting_message.delete()
            error_message = "Sorry, I couldn't find the lyrics for this track."
            return await event.respond(error_message)

    @staticmethod
    async def send_music_icon(event):
        try:
            query_data = str(event.data)
            image_url = "https://i.scdn.co/image/" + query_data.split("/")[-1][:-1]
            await event.respond(file=image_url)
        except Exception:
            await event.reply("An error occurred while processing your request. Please try again later.")

    @staticmethod
    def _link_info_from_playlist_track(track) -> dict:
        """Собирает link_info для трека из элемента плейлиста (playlist_items), без отдельного вызова track() и YouTube search."""
        if not track or not track.get('id'):
            return None
        artists = track.get('artists') or []
        album = track.get('album') or {}
        images = album.get('images') or []
        return {
            'type': 'track',
            'track_name': track.get('name', ''),
            'artist_name': ', '.join(a.get('name', '') for a in artists),
            'artist_ids': [a.get('id') for a in artists if a.get('id')],
            'artist_url': artists[0].get('external_urls', {}).get('spotify', '') if artists else '',
            'album_name': (album.get('name') or '').translate(str.maketrans('', '', '()[]')),
            'album_url': album.get('external_urls', {}).get('spotify', ''),
            'release_year': (album.get('release_date') or '')[:4],
            'image_url': images[0]['url'] if images else '',
            'track_id': track.get('id'),
            'isrc': (track.get('external_ids') or {}).get('isrc'),
            'track_url': track.get('external_urls', {}).get('spotify', ''),
            'youtube_link': None,
            'preview_url': track.get('preview_url'),
            'duration_ms': track.get('duration_ms', 0),
            'track_number': track.get('track_number', 0),
            'is_explicit': track.get('explicit', False),
        }

    @staticmethod
    async def get_playlist_tracks(playlist_id, limit: int = 10, get_all: bool = False, as_link_info: bool = False):
        if get_all:
            results = SpotifyDownloader.spotify_account.playlist_items(playlist_id)
        else:
            results = SpotifyDownloader.spotify_account.playlist_items(playlist_id, limit=limit)

        extracted_details = []
        for item in results['items']:
            track = item.get('track')
            if not track:
                continue
            if as_link_info:
                link_info = SpotifyDownloader._link_info_from_playlist_track(track)
                if link_info:
                    extracted_details.append(link_info)
            else:
                track_name = track['name']
                artist_name = track['artists'][0]['name']
                release_year = track['album']['release_date'].split("-")[0]
                track_id = track['id']
                extracted_details.append({
                    "track_name": track_name,
                    "artist_name": artist_name,
                    "release_year": release_year,
                    "track_id": track_id
                })
        return extracted_details
