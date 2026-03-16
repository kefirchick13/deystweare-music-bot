# Deystweare Music Bot

Telegram‑бот для скачивания музыки и видео из **Spotify**, **YouTube** и **Instagram**, а также для распознавания треков по голосовым сообщениям (Shazam) и получения текста песен (Genius).

## Возможности

- Скачивание музыки по ссылкам Spotify (треки и плейлисты).
- Поиск треков по названию или части текста через Spotify.
- Выбор **формата и качества аудио** (например `mp3 128/320`, `flac`).
- Отправка красивого превью трека (обложка, артист, альбом, год).
- Рассылки по пользователям и подписчикам (только для админов).
- Управление подпиской на рассылки.
- Распознавание музыки по голосовому сообщению (Shazam).
- Скриншоты твитов и скачивание медиа из Twitter/X.
- Загрузка медиа из Instagram (посты, Reels, IGTV).
- Загрузка видео/аудио с YouTube.

## Как работает бот

### Spotify‑ссылки и текстовый поиск

- Когда вы отправляете ссылку Spotify или команду `/search <запрос>`:
  - бот через Spotify Web API (`spotipy`) получает информацию о треке/плейлисте (название, артист, альбом, год, обложка и т.д.).
- При нажатии на кнопку **Download Track** для трека:
  - бот формирует запрос вида `"Артист - Трек"` и:
    - **сначала пробует найти и скачать аудио через YouTube** с помощью `yt-dlp`;
    - если подходящее видео не найдено или YouTube недоступен (в том числе из‑за возрастных ограничений),  
      бот **автоматически переключается на SoundCloud** и ищет тот же трек там (поиск `scsearch:"Артист - Трек"` в `yt-dlp`);
  - итоговый файл приводится к выбранному формату/качеству и отправляется в Telegram.
- Скачанные файлы кешируются:
  - при повторном запросе того же трека бот использует уже сохранённый файл, а не качает заново.

### Выбор качества

- В настройках (`/settings` → Quality / Качество) пользователь задаёт:
  - формат (`mp3` или `flac`);
  - качество (для `mp3` — 128 или 320 кбит/с; для `flac` — без потерь, но больше размер файла).
- Эти параметры используются при обработке:
  - при загрузке через `yt-dlp` бот выбирает лучшую аудиодорожку и через FFmpeg перегоняет её в нужный формат и битрейт;
  - файл сохраняется с именем вроде  
    `Артист - Трек-128.mp3` или `Артист - Трек.flac`.

### Голосовые сообщения (Shazam)

- Если вы отправляете голосовое с фрагментом песни:
  - бот сохраняет файл во временную папку;
  - отправляет его в `Shazamio` (Shazam API);
  - по результату распознавания строит текстовый запрос (артист + трек + год) и ищет этот трек в Spotify.
- Далее:
  - показываются найденные варианты, как при обычном поиске;
  - через кнопки можно скачать трек, 30‑секундный превью, обложку, текст песни и т.д.

### YouTube‑ссылки

- **Сейчас поддержка YouTube отключена:** при отправке ссылки на YouTube бот отвечает сообщением «Неверная ссылка. Поддержка YouTube временно отключена.»  
  Как включить обратно — см. раздел ниже **[YouTube: как включить обратно](#youtube-как-включить-обратно)**.
- Если YouTube включён:
  - бот с помощью `yt-dlp` получает список доступных форматов;
  - показывает кнопки с указанием контейнера, разрешения и примерного размера файла;
  - после выбора формата скачивает видео/аудио и отправляет файл в Telegram (со стримингом).

### Instagram

- **Instagram**:
  - по ссылке на пост / Reels / IGTV бот скачивает исходный медиа‑файл и отправляет его в чат.

### Кеширование

Всё, что возможно, бот сохраняет локально. Если тот же трек или видео запрашиваются снова, бот переиспользует локальный файл — за счёт этого повторные ответы намного быстрее.

### Почему трек может долго загружаться и как это улучшено

- **Скачивание** (SoundCloud/YouTube): поиск, загрузка и конвертация через ffmpeg зависят от источника и канала. Ускорить можно только сменой источника или качества.
- **Отправка в Telegram**: чем больше файл (например, 320 kbps или flac), тем дольше загрузка на серверы Telegram; задержка также зависит от региона сервера бота.
- **Улучшение**: для треков Spotify включён **кэш отправленных файлов**: при первом запросе трек скачивается и загружается в Telegram; при повторном запросе того же трека бот отправляет его по сохранённому `file_id` **без повторной загрузки** — ответ приходит почти мгновенно. В настройках можно выбрать меньшее качество (например, 128 kbps), чтобы первый запрос выполнялся быстрее.

### Деплой на Railway

При размещении на **Railway** на скорость влияют регион и ресурсы:

- **Регион**: в настройках сервиса выберите регион ближе к аудитории (например **EU West** для Европы/РФ) — меньше задержка до CDN и до пользователей.
- **Память**: рекомендуется **не менее 512 MB–1 GB RAM**; при активной нагрузке — 1 GB. yt-dlp и ffmpeg при конвертации нагружают процессор и память.
- Переменные окружения (Spotify, Telegram, при необходимости `YTDL_COOKIES`) задайте в **Variables**. Билд по Dockerfile уже включает ffmpeg.

## YouTube: как включить обратно

Поддержка YouTube в боте сейчас **выключена**: по ссылкам на YouTube пользователь получает сообщение «Неверная ссылка. Поддержка YouTube временно отключена.»

Чтобы снова включить загрузку видео/аудио с YouTube:

1. **Включить инициализацию YouTube**  
   В файле `run/bot.py` в методе `initialize()` раскомментируйте строку:
   ```python
   Bot.initialize_youtube()
   ```
   (удалите `#` в начале строки).

2. **Включить обработку ссылок**  
   В том же файле в методе `handle_message()` найдите блок с YouTube и замените:
   ```python
   elif YoutubeDownloader.is_youtube_link(event.message.text or ""):
       await event.respond("Неверная ссылка. Поддержка YouTube временно отключена.")
       # await Bot.process_youtube_link(event)
   ```
   на:
   ```python
   elif YoutubeDownloader.is_youtube_link(event.message.text or ""):
       await Bot.process_youtube_link(event)
   ```
   (удалите строку с `respond` и раскомментируйте `await Bot.process_youtube_link(event)`).

3. **Включить обработку кнопок выбора формата**  
   В методе `callback_query_handler()` найдите блок `elif event.data.startswith(b"yt"):` и замените ответ «YouTube временно отключён» на вызов обработчика:
   ```python
   elif event.data.startswith(b"yt"):
       await Bot.handle_youtube_callback(Bot.Client, event)
   ```
   (удалите `try/except` с `event.answer("YouTube временно отключён.")` и раскомментируйте вызов `handle_youtube_callback`).

4. **Раскомментировать сами обработчики**  
   В `run/bot.py` найдите комментарии:
   - `# --- YouTube: закомментировано ... ---` и блок с `process_youtube_link`;
   - второй такой же блок с `handle_youtube_callback`.  
   Раскомментируйте код этих двух методов (уберите `#` в начале каждой строки блока), чтобы снова работали `process_youtube_link` и `handle_youtube_callback`.

5. **Перезапустить бота**  
   После изменений перезапустите процесс бота (`python3 main.py` или через ваш способ запуска).

Для работы YouTube нужны: `yt-dlp`, `ffmpeg` и при необходимости переменная окружения `YTDL_COOKIES` (cookies в формате Netscape), если YouTube блокирует запросы.

---

## Установка

Ниже — оригинальные шаги установки (на английском) из исходного проекта.

### Step 1: Install FFmpeg

FFmpeg is required for audio processing. Here's how to install it on different operating systems:

#### Ubuntu/Debian
```zsh
sudo apt install ffmpeg
```

#### macOS (using Homebrew)
```zsh
brew install ffmpeg
```

#### Windows

Download the FFmpeg build from [Here](https://ffmpeg.org/download.html).
Extract the downloaded file and add the bin folder to your system's PATH.

To verify the installation, run:
```zsh
ffmpeg -version
```

If you see version information, FFmpeg is installed correctly.


### Step 2: Clone the Repository

Open a terminal and clone the `MusicDownloader-Telegram-Bot` repository from GitHub:

```zsh
git clone https://github.com/AdibNikjou/MusicDownloader-Telegram-Bot.git
```

### Step 3: Install Python Dependencies

Navigate to the cloned repository's directory and install the required Python dependencies using `pip`:

```zsh
cd MusicDownloader-Telegram-Bot
pip install -r requirements.txt
```


### Step 4: Set Up Your Environment Variables

Create a `config.env` file in the root directory of the project and add the following environment variables:

- `SPOTIFY_CLIENT_ID=your_spotify_client_id`
- `SPOTIFY_CLIENT_SECRET=your_spotify_client_secret`
- `BOT_TOKEN=your_telegram_bot_token`
- `API_ID=your_telegram_api_id`
- `API_HASH=your_telegram_api_hash`
- `GENIUS_ACCESS_TOKEN=your_genius_access_token`
- `ADMIN_USER_IDS=123456789,987654321` — список админов (через запятую, без пробелов)
- `REQUIRED_CHANNELS=@your_channel1,@your_channel2` — (опционально) список каналов, на которые пользователь обязан быть подписан; если пусто или переменной нет — подписка не обязательна

### Step 5: Run the Bot

With all dependencies installed and environment variables set, you can now run the bot:

```zsh
python3 main.py
```

## Использование

1. Отправьте боту `/start`, чтобы начать диалог.
2. Отправьте ссылку Spotify или используйте `/search`, чтобы найти и скачать трек.
3. Используйте `/settings`, чтобы настроить:
   - формат и качество аудио,
   - язык интерфейса (RU/EN),
   - подписку на рассылки.
4. Подпишитесь на рассылки через `/subscribe` и отписывайтесь через `/unsubscribe`.
5. Команда `/admin` доступна только админам и открывает панель управления.

## Команды для пользователей

- `/start` — запустить бота и получить приветственное сообщение.
- `/search <query>` — поиск треков по.
- `/settings` — открыть меню настроек (качество, язык, подписка).
- `/quality` — сразу перейти к выбору качества и формата.
- `/subscribe` — подписаться на рассылку.
- `/unsubscribe` — отписаться от рассылки.
- `/help` — получить справку по использованию бота.
- `/ping` — проверить время отклика бота.

## Команды для админов

Доступны только пользователям, чьи ID указаны в `ADMIN_USER_IDS`:

- `/admin` — открыть панель администратора (кнопки рассылки и статистики).
- `/stats` — показать количество пользователей и подписчиков.
- `/broadcast` — запустить рассылку:
  - `/broadcast` — рассылка по подписчикам;
  - `/broadcast (id1,id2,...)` — рассылка по указанным ID;
  - `/broadcast_to_all` — рассылка по всем пользователям.

### Список команд для BotFather

Скопируй блок ниже и вставь в `BotFather` в разделе `/setcommands`:

```text
start - Запустить бота
search - Поиск трека на Spotify
settings - Открыть меню настроек
quality - Изменить формат и качество аудио
subscribe - Подписаться на обновления бота
unsubscribe - Отписаться от обновлений
help - Показать справку
ping - Проверить отклик бота
admin - Открыть панель администратора
stats - Показать статистику бота
broadcast - Рассылка по подписчикам
broadcast_to_all - Рассылка по всем пользователям
```

## Dependencies

- Python 3.10+
- Telethon
- Spotipy
- Yt-dlp
- Shazamio
- Pillow
- dotenv
- aiosqlite
- FastTelethonhelper

## Contributing

Contributions are welcome! Please feel free to submit a pull request or open an issue if you find any bugs or have suggestions for improvements.

## License

This project is licensed under the MIT License. See the `LICENSE` file for details.

## Contact

For any inquiries or feedback, please contact the creator:
- Telegram: @AdibNikjou
- Email: adib.n7789@gmail.com

## Acknowledgments

- Spotify API for providing access to music metadata.
- Telegram API for the bot framework.
- Shazam API for voice recognition.
- YoutubeDL for downloading music from YouTube.
