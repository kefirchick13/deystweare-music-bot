from .glob_variables import BotState
from .buttons import Buttons
from utils import db
from telethon.errors.rpcerrorlist import MessageNotModifiedError


class BotMessageHandler:
    @staticmethod
    def get_start_message(language: str) -> str:
        # YouTube отключён — приветствие без YouTube. Чтобы вернуть с YouTube: раскомментировать блок ниже и закомментировать текущий return.
        # if language == "en":
        #     return (
        #         "Welcome to **Lumen Music Bot** 🎧\n\n"
        #         "I can:\n"
        #         "- Search by text or Spotify link\n"
        #         "- Search by voice message (Shazam)\n"
        #         "- Download from YouTube\n\n"
        #         "Send me a song name, artist, link or a voice message — I will find the track and help you download music or video. 🎶\n\n"
        #         "To see what I can do, type: /help\n"
        #         'Or simply tap the "Instructions" button below. 👇'
        #     )
        # else:
        #     return (
        #         "Добро пожаловать в **Lumen Music Bot** 🎧\n\n"
        #         "Я умею:\n"
        #         "- Искать треки по тексту или ссылке Spotify\n"
        #         "- Искать музыку по голосовому сообщению (Shazam)\n"
        #         "- Скачивать видео/аудио с YouTube\n\n"
        #         "Отправь мне название песни, исполнителя, ссылку или голосовое сообщение — я найду трек и помогу скачать музыку или видео. 🎶\n\n"
        #         "Чтобы узнать подробнее, введи команду: /help\n"
        #         "Или просто нажми кнопку «Инструкция» ниже. 👇"
        #     )
        if language == "en":
            return (
                "Welcome to **Lumen Music Bot** 🎧\n\n"
                "I can:\n"
                "- Search by text or Spotify link\n"
                "- Search by voice message (Shazam)\n"
                "- Download from YouTube — coming soon 🎬\n\n"
                "Send me a song name, artist, link or a voice message — I will find the track and help you download music. 🎶\n\n"
                "To see what I can do, type: /help\n"
                'Or simply tap the "Instructions" button below. 👇'
            )
        else:
            return (
                "Добро пожаловать в **Lumen Music Bot** 🎧\n\n"
                "Я умею:\n"
                "- Искать треки по тексту или ссылке Spotify\n"
                "- Искать музыку по голосовому сообщению (Shazam)\n"
                "- Скачивание с YouTube — скоро появится 🎬\n\n"
                "Отправь мне название песни, исполнителя, ссылку или голосовое сообщение — я найду трек и помогу скачать музыку. 🎶\n\n"
                "Чтобы узнать подробнее, введи команду: /help\n"
                "Или просто нажми кнопку «Инструкция» ниже. 👇"
            )

    @staticmethod
    def get_instruction_message(language: str) -> str:
        if language == "en":
            return (
                "🎧 Lumen Music Bot — what it can do 🎧\n\n"
                "🎵 Music / Spotify / voice:\n"
                "1. Send a Spotify track/album/playlist link 🔗\n"
                "2. Wait for processing ⏳\n"
                "3. Get a file or download options 💾\n"
                "4. Or send a voice message with a song sample —\n"
                "   the bot will try to recognize it via Shazam and suggest tracks 🎤🔍📩\n"
                "5. You can request lyrics, artist info and more 📜👨‍🎤\n\n"
                "💡 Tip: you can search by title, part of lyrics or artist name.\n\n"
                "If you have any questions about the bot, contact your admin/owner."
            )
        else:
            return (
                "🎧 Lumen Music Bot — что он умеет 🎧\n\n"
                "🎵 Музыка / Spotify / голос:\n"
                "1. Отправь ссылку на трек / альбом / плейлист Spotify 🔗\n"
                "2. Дождись обработки запроса ⏳\n"
                "3. Получи файл или варианты скачивания 💾\n"
                "4. Либо отправь голосовое с фрагментом песни —\n"
                "   бот попробует распознать её через Shazam и предложит треки 🎤🔍📩\n"
                "5. Можно запросить текст песни, информацию об исполнителе и другое 📜👨‍🎤\n\n"
                "💡 Подсказка: можно искать по названию, части текста или имени исполнителя.\n\n"
                "Возникли вопросы по боту? Напиши своему админу/владельцу бота."
            )

    @staticmethod
    def get_search_result_message(language: str) -> str:
        if language == "en":
            return "🎵 Here are the main results that match your query:\n"
        else:
            return "🎵 Вот основные результаты, которые соответствуют вашему запросу:\n"

    @staticmethod
    def get_core_selection_message(language: str) -> str:
        if language == "en":
            return "🎵 Choose your download core (Download Core) 🎵\n\n"
        else:
            return "🎵 Выберите ядро загрузки (Download Core) 🎵\n\n"

    @staticmethod
    def get_join_channel_message(language: str) -> str:
        if language == "en":
            return "It looks like you are not subscribed to our channel yet.\nPlease join to continue using the bot."
        else:
            return "Похоже, вы ещё не подписаны на наш канал.\nПожалуйста, вступите, чтобы продолжить использование бота."

    @staticmethod
    def get_search_playlist_message(language: str) -> str:
        if language == "en":
            return "The playlist contains these tracks:"
        else:
            return "В плейлисте найдены следующие треки:"

    @staticmethod
    async def send_message(event, text, buttons=None):
        chat_id = event.chat_id
        user_id = event.sender_id
        await BotState.initialize_user_state(user_id)
        await BotState.BOT_CLIENT.send_message(chat_id, text, buttons=buttons)

    @staticmethod
    async def edit_message(event, message_text, buttons=None):
        user_id = event.sender_id

        await BotState.initialize_user_state(user_id)
        try:
            await event.edit(message_text, buttons=buttons)
        except MessageNotModifiedError:
            pass

    @staticmethod
    async def edit_quality_setting_message(e):
        music_quality = await db.get_user_music_quality(e.sender_id)
        language = await db.get_user_language(e.sender_id)
        if music_quality:
            if language == "en":
                message = (f"Your quality settings:\nFormat: {music_quality['format']}\nQuality: {music_quality['quality']}"
                           f"\n\nAvailable qualities:")
            else:
                message = (f"Ваши настройки качества:\nФормат: {music_quality['format']}\nКачество: {music_quality['quality']}"
                           f"\n\nДоступные варианты качества:")
        else:
            message = "No quality settings found." if language == "en" else "Настройки качества пока не найдены."
        await BotMessageHandler.edit_message(e, message, buttons=Buttons.get_quality_setting_buttons(music_quality))

    @staticmethod
    async def edit_core_setting_message(e):
        downloading_core = await db.get_user_downloading_core(e.sender_id)
        language = await db.get_user_language(e.sender_id)
        if downloading_core:
            core_text = BotMessageHandler.get_core_selection_message(language)
            suffix = f"\nCurrent core: {downloading_core}" if language == "en" else f"\nТекущее ядро: {downloading_core}"
            message = core_text + suffix
        else:
            core_text = BotMessageHandler.get_core_selection_message(language)
            suffix = "\nNo core selected yet." if language == "en" else "\nЯдро загрузки пока не выбрано."
            message = core_text + suffix
        await BotMessageHandler.edit_message(e, message, buttons=Buttons.get_core_setting_buttons(downloading_core))

    @staticmethod
    async def edit_subscription_status_message(e):
        is_subscribed = await db.is_user_subscribed(e.sender_id)
        language = await db.get_user_language(e.sender_id)
        if language == "en":
            message = f"Subscription settings:\n\nYour current status: {is_subscribed}"
        else:
            message = f"Настройки подписки:\n\nВаш текущий статус: {is_subscribed}"
        await BotMessageHandler.edit_message(e, message,
                                             buttons=Buttons.get_subscription_setting_buttons(is_subscribed))

    @staticmethod
    async def edit_language_setting_message(e):
        from utils import db
        user_id = e.sender_id
        current_language = await db.get_user_language(user_id)
        if current_language == 'en':
            message = "Language settings:\n\nCurrent language: English"
        else:
            message = "Настройки языка:\n\nТекущий язык: Русский"
        await BotMessageHandler.edit_message(e, message,
                                             buttons=Buttons.get_language_setting_buttons(current_language))
