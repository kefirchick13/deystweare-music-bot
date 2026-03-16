from run import Button


class Buttons:
    main_menu_buttons = [
        [Button.inline("Инструкция", b"instructions"), Button.inline("Настройки", b"setting")],
        [Button.url("Связаться с владельцем", url="https://t.me/saintCityLover")],
    ]

    back_button = Button.inline("<< В главное меню", b"back")

    setting_button = [
        [Button.inline("Качество", b"setting/quality")],
        [Button.inline("Язык / Language", b"setting/language")],
        [Button.inline("Подписка", b"setting/subscription")],
        [back_button]
    ]

    back_button_to_setting = Button.inline("<< Назад", b"setting/back")

    cancel_broadcast_button = [Button.inline("Отменить рассылку", data=b"admin/cancel_broadcast")]

    admins_buttons = [
        [Button.inline("Рассылка", b"admin/broadcast")],
        [Button.inline("Статистика", b"admin/stats")],
        [Button.inline("Отмена", b"cancel")]
    ]

    broadcast_options_buttons = [
        [Button.inline("Рассылка всем пользователям", b"admin/broadcast/all")],
        [Button.inline("Рассылка только подписчикам", b"admin/broadcast/subs")],
        [Button.inline("Рассылка выбранным пользователям", b"admin/broadcast/specified")],
        [Button.inline("Отмена", b"cancel")]
    ]

    cancel_subscription_button_quite = [Button.inline("Отписаться", b"setting/subscription/cancel/quite")]

    cancel_button = [Button.inline("Отмена", b"cancel")]

    @staticmethod
    def get_subscription_setting_buttons(subscription):
        if subscription:
            return [
                [Button.inline("Отписаться", data=b"setting/subscription/cancel")],
                [Buttons.back_button, Buttons.back_button_to_setting]
            ]
        else:
            return [
                [Button.inline("Подписаться", data=b"setting/subscription/add")],
                [Buttons.back_button, Buttons.back_button_to_setting]
            ]

    @staticmethod
    def get_core_setting_buttons(core):
        if core == "Auto":
            return [
                [Button.inline("🔸 Auto", data=b"setting/core/auto")],
                [Button.inline("YoutubeDL", b"setting/core/youtubedl")],
                [Button.inline("SpotDL", b"setting/core/spotdl")],
                [Buttons.back_button, Buttons.back_button_to_setting],
            ]
        if core == "SpotDL":
            return [
                [Button.inline("Auto", data=b"setting/core/auto")],
                [Button.inline("YoutubeDL", b"setting/core/youtubedl")],
                [Button.inline("🔸 SpotDL", b"setting/core/spotdl")],
                [Buttons.back_button, Buttons.back_button_to_setting],
            ]
        if core == "YoutubeDL":
            return [
                [Button.inline("Auto", data=b"setting/core/auto")],
                [Button.inline("🔸 YoutubeDL", b"setting/core/youtubedl")],
                [Button.inline("SpotDL", b"setting/core/spotdl")],
                [Buttons.back_button, Buttons.back_button_to_setting],
            ]
        return []

    @staticmethod
    def get_quality_setting_buttons(music_quality):
        if isinstance(music_quality['quality'], int):
            music_quality['quality'] = str(music_quality['quality'])

        fmt = music_quality.get('format')
        q = music_quality.get('quality')
        if fmt == 'flac' and q == "693":
            return [
                [Button.inline("◽️ Flac", b"setting/quality/flac")],
                [Button.inline("Mp3 (320)", b"setting/quality/mp3/320")],
                [Button.inline("Mp3 (128)", b"setting/quality/mp3/128")],
                [Buttons.back_button, Buttons.back_button_to_setting],
            ]
        if fmt == "mp3" and q == "320":
            return [
                [Button.inline("Flac", b"setting/quality/flac")],
                [Button.inline("◽️ Mp3 (320)", b"setting/quality/mp3/320")],
                [Button.inline("Mp3 (128)", b"setting/quality/mp3/128")],
                [Buttons.back_button, Buttons.back_button_to_setting],
            ]
        if fmt == "mp3" and q == "128":
            return [
                [Button.inline("Flac", b"setting/quality/flac")],
                [Button.inline("Mp3 (320)", b"setting/quality/mp3/320")],
                [Button.inline("◽️ Mp3 (128)", b"setting/quality/mp3/128")],
                [Buttons.back_button, Buttons.back_button_to_setting],
            ]
        return []

    @staticmethod
    def get_search_result_buttons(sanitized_query, search_result, page=1) -> list:

        button_list = [
            [Button.inline(f"🎧 {details['track_name']} - {details['artist_name']} 🎧 ({details['release_year']})",
                           data=f"spotify/info/{details['track_id']}")]
            for details in search_result[(page-1) * 10:]
        ]

        if len(search_result) > 1:
            button_list.append([Button.inline("Previous Page", f"prev_page/s/{sanitized_query}/page/{page - 1}"),
                                Button.inline("Next Page", f"next_page/s/{sanitized_query}/page/{page + 1}")])
        button_list.append([Button.inline("Cancel", b"cancel")])

        return button_list

    @staticmethod
    def get_playlist_search_buttons(playlist_id, search_result, page=1) -> list:
        button_list = [
            [Button.inline(f"🎧 {details['track_name']} - {details['artist_name']} 🎧 ({details['release_year']})",
                           data=f"spotify/info/{details['track_id']}")]
            for details in search_result[(page-1) * 10:]
        ]

        if len(search_result) > 1:
            button_list.append([Button.inline("Previous Page", f"prev_page/p/{playlist_id}/page/{page - 1}"),
                                Button.inline("Next Page", f"next_page/p/{playlist_id}/page/{page + 1}")])
        button_list.append([Button.inline("Cancel", b"cancel")])

        return button_list

    @staticmethod
    def get_main_menu_buttons(language: str):
        if language == "en":
            return [
                [Button.inline("Instructions", b"instructions"), Button.inline("Settings", b"setting")],
                [Button.url("Contact owner", url="https://t.me/saintCityLover")],
            ]
        else:
            return [
                [Button.inline("Инструкция", b"instructions"), Button.inline("Настройки", b"setting")],
                [Button.url("Связаться с владельцем", url="https://t.me/saintCityLover")],
            ]

    @staticmethod
    def get_setting_buttons(language: str):
        if language == "en":
            return [
                [Button.inline("Quality", b"setting/quality")],
                [Button.inline("Language", b"setting/language")],
                [Button.inline("Subscription", b"setting/subscription")],
                [Buttons.back_button]
            ]
        else:
            return [
                [Button.inline("Качество", b"setting/quality")],
                [Button.inline("Язык / Language", b"setting/language")],
                [Button.inline("Подписка", b"setting/subscription")],
                [Buttons.back_button]
            ]

    @staticmethod
    def get_language_setting_buttons(current_language: str):
        if current_language == 'en':
            return [
                [Button.inline("Русский", data=b"setting/language/ru"),
                 Button.inline("🔹 English", data=b"setting/language/en")],
                [Buttons.back_button, Buttons.back_button_to_setting]
            ]
        else:
            return [
                [Button.inline("🔹 Русский", data=b"setting/language/ru"),
                 Button.inline("English", data=b"setting/language/en")],
                [Buttons.back_button, Buttons.back_button_to_setting]
            ]
