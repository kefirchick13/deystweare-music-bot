import tempfile
import shutil
from utils import YoutubeDL, re, lru_cache, hashlib, InputMediaPhotoExternal, db
from utils import os, InputMediaUploadedDocument, DocumentAttributeVideo, fast_upload
from utils import DocumentAttributeAudio, DownloadError, WebpageMediaEmptyError
from run import Button, Buttons


def _ffmpeg_location():
    """Путь к каталогу с ffmpeg/ffprobe для yt-dlp (merge/postprocess)."""
    exe = shutil.which("ffmpeg")
    if exe:
        return os.path.dirname(exe)
    return "/usr/bin"


def _ydl_cookies_opts():
    """Куки только из env YTDL_COOKIES (Netscape-текст), пишем во временный файл при старте."""
    path = getattr(YoutubeDownloader, '_cookies_file_path', None)
    if path and os.path.isfile(path):
        return {'cookiefile': path}
    return {}


class YoutubeDownloader:

    @classmethod
    def initialize(cls):
        cls.DOWNLOAD_DIR = 'repository/Youtube'
        cls._cookies_file_path = None

        if not os.path.isdir(cls.DOWNLOAD_DIR):
            os.mkdir(cls.DOWNLOAD_DIR)

        # Куки только из env YTDL_COOKIES — весь текст в формате Netscape, вставляешь как есть
        raw = os.environ.get('YTDL_COOKIES', '').strip()
        if raw:
            raw = raw.replace('\\n', '\n')
            try:
                tmp = tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8')
                tmp.write(raw)
                tmp.close()
                cls._cookies_file_path = tmp.name
            except Exception:
                cls._cookies_file_path = None

    @lru_cache(maxsize=128)  # Cache the last 128 screenshots
    def get_file_path(url, format_id, extension):
        url = url + format_id + extension
        url_hash = hashlib.blake2b(url.encode()).hexdigest()
        filename = f"{url_hash}.{extension}"
        return os.path.join(YoutubeDownloader.DOWNLOAD_DIR, filename)

    @staticmethod
    def is_youtube_link(url):
        youtube_patterns = [
            r'(https?\:\/\/)?youtube\.com\/shorts\/([a-zA-Z0-9_-]{11}).*',
            r'(https?\:\/\/)?www\.youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})(?!.*list=)',
            r'(https?\:\/\/)?youtu\.be\/([a-zA-Z0-9_-]{11})(?!.*list=)',
            r'(https?\:\/\/)?www\.youtube\.com\/embed\/([a-zA-Z0-9_-]{11})(?!.*list=)',
            r'(https?\:\/\/)?www\.youtube\.com\/v\/([a-zA-Z0-9_-]{11})(?!.*list=)',
            r'(https?\:\/\/)?www\.youtube\.com\/[^\/]+\?v=([a-zA-Z0-9_-]{11})(?!.*list=)',
        ]
        for pattern in youtube_patterns:
            match = re.match(pattern, url)
            if match:
                return True
        return False

    @staticmethod
    def extract_youtube_url(text):
        # Regular expression patterns to match different types of YouTube URLs
        youtube_patterns = [
            r'(https?\:\/\/)?youtube\.com\/shorts\/([a-zA-Z0-9_-]{11}).*',
            r'(https?\:\/\/)?www\.youtube\.com\/watch\?v=([a-zA-Z0-9_-]{11})(?!.*list=)',
            r'(https?\:\/\/)?youtu\.be\/([a-zA-Z0-9_-]{11})(?!.*list=)',
            r'(https?\:\/\/)?www\.youtube\.com\/embed\/([a-zA-Z0-9_-]{11})(?!.*list=)',
            r'(https?\:\/\/)?www\.youtube\.com\/v\/([a-zA-Z0-9_-]{11})(?!.*list=)',
            r'(https?\:\/\/)?www\.youtube\.com\/[^\/]+\?v=([a-zA-Z0-9_-]{11})(?!.*list=)',
        ]

        for pattern in youtube_patterns:
            match = re.search(pattern, text)
            if match:
                video_id = match.group(2)
                if 'youtube.com/shorts/' in match.group(0):
                    return f'https://www.youtube.com/shorts/{video_id}'
                else:
                    return f'https://www.youtube.com/watch?v={video_id}'

        return None

    @staticmethod
    def _get_formats(url):
        ydl_opts = {
            'listformats': True,
            'no_warnings': True,
            'quiet': True,
            **_ydl_cookies_opts(),
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = info['formats']
        return formats

    @staticmethod
    async def send_youtube_info(client, event, youtube_link):
        url = youtube_link
        video_id = (youtube_link.split("?si=")[0]
                    .replace("https://www.youtube.com/watch?v=", "")
                    .replace("https://www.youtube.com/shorts/", ""))
        formats = YoutubeDownloader._get_formats(url)

        # Download the video thumbnail
        with YoutubeDL({'quiet': True, **_ydl_cookies_opts()}) as ydl:
            info = ydl.extract_info(url, download=False)
            thumbnail_url = info['thumbnail']   

        audio_formats = [f for f in formats if f.get('acodec') != 'none' and f.get('vcodec') == 'none']

        def _filesize_mb(fmt):
            size = fmt.get('filesize') or fmt.get('filesize_approx')
            if not size:
                return None
            return size / 1024 / 1024

        # Видео: одна кнопка — bestvideo+bestaudio/best
        video_buttons = [[Button.inline("Видео — лучшее качество", data=f"yt/dl/{video_id}/mp4/best/?")]]

        # Pick 2 best audio-only formats by abr
        audio_buttons = []
        audio_sorted = sorted(
            audio_formats,
            key=lambda f: (f.get('abr') or 0, _filesize_mb(f) or 0),
            reverse=True,
        )
        for fmt in audio_sorted:
            if len(audio_buttons) >= 2:
                break
            extension = fmt.get('ext')
            abr = fmt.get('abr')
            size_mb = _filesize_mb(fmt)
            if not extension or not fmt.get('format_id') or size_mb is None:
                continue
            abr_text = f"{int(abr)}kbps" if abr else "audio"
            filesize = f"{size_mb:.2f} MB"
            button_data = f"yt/dl/{video_id}/{extension}/{fmt['format_id']}/{filesize}"
            button = [Button.inline(f"{extension} - {abr_text} - {filesize}", data=button_data)]
            if button not in audio_buttons:
                audio_buttons.append(button)

        buttons = video_buttons + audio_buttons
        buttons.append(Buttons.cancel_button)

        # Set thumbnail attributes
        thumbnail = InputMediaPhotoExternal(thumbnail_url)
        thumbnail.ttl_seconds = 0

        # Send the thumbnail as a picture with format buttons
        try:
            await client.send_file(
                event.chat_id,
               file=thumbnail,
               caption="Select a format to download:",
               buttons=buttons
               )
        except WebpageMediaEmptyError:
            await event.respond(
               "Select a format to download:",
               buttons=buttons
               )


    @staticmethod
    async def download_and_send_yt_file(client, event):
        user_id = event.sender_id

        if await db.get_file_processing_flag(user_id):
            return await event.respond("Sorry, There is already a file being processed for you.")

        data = event.data.decode('utf-8')
        parts = data.split('/')
        if len(parts) == 6:
            extension = parts[3]
            format_id = parts[-2]
            filesize_str = parts[-1].replace("MB", "").strip()
            video_id = parts[2]

            await db.set_file_processing_flag(user_id, is_processing=True)

            local_availability_message = None
            url = "https://www.youtube.com/watch?v=" + video_id

            is_merge = format_id.startswith("merge_") or format_id == "best"
            if format_id == "best":
                format_spec = "bestvideo+bestaudio/best"
                path = YoutubeDownloader.get_file_path(url, "best", "mp4")
            elif format_id.startswith("merge_"):
                try:
                    height = int(format_id.replace("merge_", ""))
                    format_spec = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]"
                except ValueError:
                    format_spec = "bestvideo+bestaudio/best"
                path = YoutubeDownloader.get_file_path(url, format_id, "mp4")
            else:
                format_spec = format_id
                path = YoutubeDownloader.get_file_path(url, format_id, extension)

            if not os.path.isfile(path):
                size_label = f"{filesize_str} MB" if filesize_str != "?" else ""
                downloading_message = await event.respond(
                    f"Скачиваю файл с YouTube ({size_label})... Это может занять некоторое время.".strip())
                ydl_opts_base = {
                    'outtmpl': path,
                    'quiet': True,
                    'ffmpeg_location': _ffmpeg_location(),
                    **_ydl_cookies_opts(),
                }
                if is_merge:
                    ydl_opts_base['merge_output_format'] = 'mp4'

                info = None
                try:
                    ydl_opts = {**ydl_opts_base, 'format': format_spec}
                    with YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                except DownloadError as e:
                    if 'not available' in str(e).lower() or 'requested format' in str(e).lower():
                        # Формат недоступен — пробуем лучшее качество (video+audio)
                        fallback_path = YoutubeDownloader.get_file_path(url, "best", extension if extension == "mp4" else "mp4")
                        try:
                            ydl_opts = {
                                **ydl_opts_base,
                                'format': 'bestvideo+bestaudio/best',
                                'outtmpl': fallback_path,
                                'merge_output_format': 'mp4',
                            }
                            with YoutubeDL(ydl_opts) as ydl:
                                info = ydl.extract_info(url, download=True)
                            path = fallback_path
                            extension = "mp4"
                        except DownloadError:
                            await db.set_file_processing_flag(user_id, is_processing=False)
                            return await downloading_message.edit(f"Ошибка: запрошенный формат недоступен.\n{str(e)[:300]}")
                    else:
                        await db.set_file_processing_flag(user_id, is_processing=False)
                        return await downloading_message.edit(f"Sorry Something went wrong:\nError: {str(e).split('Error')[-1]}")
                if info is None:
                    await db.set_file_processing_flag(user_id, is_processing=False)
                    return await downloading_message.edit("Ошибка при скачивании.")
                duration = info.get('duration', 0)
                width = info.get('width', 0)
                height = info.get('height', 0)
                await downloading_message.delete()
            else:
                local_availability_message = await event.respond(
                    "Этот файл уже есть у бота. Готовлю его к отправке...")

                ydl_opts = {
                    'format': format_spec,
                    'outtmpl': path,
                    'quiet': True,
                    'ffmpeg_location': _ffmpeg_location(),
                    **_ydl_cookies_opts(),
                }
                if is_merge:
                    ydl_opts['merge_output_format'] = 'mp4'
                try:
                    with YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                except DownloadError:
                    ydl_opts['format'] = 'bestvideo+bestaudio/best'
                    with YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=False)
                duration = info.get('duration', 0)
                width = info.get('width', 0)
                height = info.get('height', 0)

            upload_message = await event.respond("Uploading ... Please hold on.")

            try:
                # Indicate ongoing file upload to enhance user experience
                async with client.action(event.chat_id, 'document'):

                    media = await fast_upload(
                        client=client,
                        file_location=path,
                        reply=None,  # No need for a progress bar in this case
                        name=path,
                        progress_bar_function=None
                    )

                    if extension == "mp4":

                        uploaded_file = await client.upload_file(media)

                        # Prepare the video attributes
                        video_attributes = DocumentAttributeVideo(
                            duration=int(duration),
                            w=int(width),
                            h=int(height),
                            supports_streaming=True,
                            # Add other attributes as needed
                        )

                        media = InputMediaUploadedDocument(
                            file=uploaded_file,
                            thumb=None,
                            mime_type='video/mp4',
                            attributes=[video_attributes],
                        )

                    elif extension == "m4a" or extension == "webm":

                        uploaded_file = await client.upload_file(media)

                        # Prepare the audio attributes
                        audio_attributes = DocumentAttributeAudio(
                            duration=int(duration),
                            title="Downloaded Audio",  # Replace with actual title
                            performer="@deystweare_music_bot",  # Replace with actual performer
                            # Add other attributes as needed
                        )

                        media = InputMediaUploadedDocument(
                            file=uploaded_file,
                            thumb=None,  # Assuming you have a thumbnail or will set it later
                            mime_type='audio/m4a' if extension == "m4a" else 'audio/webm',
                            attributes=[audio_attributes],
                        )

                    # Send the downloaded file
                    await client.send_file(event.chat_id, file=media,
                                           caption=f"Enjoy!\n@deystweare_music_bot",
                                           force_document=False,
                                           # This ensures the file is sent as a video/voice if possible
                                           supports_streaming=True  # This enables video streaming
                                           )

                await upload_message.delete()
                await local_availability_message.delete() if local_availability_message else None
                await db.set_file_processing_flag(user_id, is_processing=False)

            except Exception as Err:
                await db.set_file_processing_flag(user_id, is_processing=False)
                return await event.respond(f"Sorry There was a problem with your request.\nReason:{str(Err)}")
        else:
            await event.answer("Invalid button data.")
