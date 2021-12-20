#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import configparser
import io
import json
import logging
import os
import sys
import threading

import ffmpeg
import pdf2image
import PIL
import telegram.ext
import telegram.utils.helpers
import telegram_utils
import yt_dlp as youtube_dl

import analytics
import constants
import custom_logger
import database
import utils

custom_logger.configure_root_logger()

logger = logging.getLogger(__name__)

BOT_NAME: str
BOT_TOKEN: str

ADMIN_USER_ID: int

updater: telegram.ext.Updater
analytics_handler: analytics.AnalyticsHandler


def stop_and_restart() -> None:
    updater.stop()
    os.execl(sys.executable, sys.executable, *sys.argv)


def create_or_update_user(bot: telegram.Bot, user: telegram.User) -> None:
    db_user = database.User.create_or_update_user(user.id, user.username)

    if db_user:
        prefix = 'New user:'

        bot.send_message(
            chat_id=ADMIN_USER_ID,
            text=(
                f'{telegram_utils.escape_v2_markdown_text(prefix)} '
                f'{db_user.get_markdown_description()}'
            ),
            parse_mode=telegram.ParseMode.MARKDOWN_V2,
            disable_notification=True
        )


def start_command_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    message = update.message

    if message is None:
        return

    bot = context.bot

    chat_id = message.chat_id
    user = message.from_user

    if user is None:
        return

    create_or_update_user(bot, user)

    analytics_handler.track(context, analytics.AnalyticsType.COMMAND, user, '/start')

    bot.send_message(chat_id, 'Send me a file to try to convert it to something better.')


def restart_command_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    message = update.message

    if message is None:
        return

    bot = context.bot

    if not utils.check_admin(bot, context, message, analytics_handler, ADMIN_USER_ID):
        return

    bot.send_message(message.chat_id, 'Restarting...')

    threading.Thread(target=stop_and_restart).start()


def logs_command_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    message = update.message

    if message is None:
        return

    bot = context.bot

    chat_id = message.chat_id

    if not utils.check_admin(bot, context, message, analytics_handler, ADMIN_USER_ID):
        return

    try:
        bot.send_document(chat_id, open('errors.log', 'rb'))
    except telegram.TelegramError:
        bot.send_message(chat_id, 'Log is empty')


def users_command_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    message = update.message

    if message is None:
        return

    bot = context.bot

    chat_id = message.chat_id

    if not utils.check_admin(bot, context, message, analytics_handler, ADMIN_USER_ID):
        return

    args = context.args or []

    bot.send_message(
        chat_id=chat_id,
        text=database.User.get_users_table('updated' in args),
        parse_mode=telegram.ParseMode.MARKDOWN_V2
    )


def message_file_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    message = update.effective_message
    chat = update.effective_chat

    if chat is None:
        return

    chat_type = chat.type
    bot = context.bot

    if message is None:
        return

    if cli_args.debug and not utils.check_admin(bot, context, message, analytics_handler, ADMIN_USER_ID):
        return

    message_id = message.message_id
    chat_id = message.chat.id
    attachment = message.effective_attachment

    if attachment is None:
        return

    if type(attachment) is list:
        if chat_type == telegram.Chat.PRIVATE:
            bot.send_message(
                chat_id,
                'You need to send the image as a file to convert it to a sticker.',
                reply_to_message_id=message_id
            )

        return

    if not isinstance(attachment, (
        telegram.Audio,
        telegram.Document,
        telegram.Voice,
        telegram.Sticker
    )):
        return

    message_type = telegram.utils.helpers.effective_message_type(message)

    file_size = attachment.file_size

    if file_size is None:
        return

    if not utils.ensure_size_under_limit(file_size, telegram.constants.MAX_FILESIZE_DOWNLOAD, update, context):
        return

    user = message.from_user

    input_file_id = attachment.file_id
    input_file_name = None

    if isinstance(attachment, (telegram.Audio, telegram.Document)):
        input_file_name = attachment.file_name

        if input_file_name is None and isinstance(attachment, telegram.Audio):
            input_file_name = attachment.title

    if user is not None:
        create_or_update_user(bot, user)

        analytics_handler.track(context, analytics.AnalyticsType.MESSAGE, user)

    if chat_type == telegram.Chat.PRIVATE:
        bot.send_chat_action(chat_id, telegram.ChatAction.TYPING)

    input_file = bot.get_file(input_file_id)
    input_file_url = input_file.file_path

    probe = None

    try:
        probe = ffmpeg.probe(input_file_url)
    except ffmpeg.Error:
        pass

    with io.BytesIO() as output_bytes:
        output_type = constants.OutputType.NONE
        caption = None
        invalid_format = None

        if message_type == 'voice':
            output_type = constants.OutputType.FILE

            mp3_bytes = utils.convert(output_type, input_audio_url=input_file_url)

            if not utils.ensure_valid_converted_file(
                file_bytes=mp3_bytes,
                update=update,
                context=context
            ):
                return

            if mp3_bytes is not None:
                output_bytes.write(mp3_bytes)

            output_bytes.name = 'voice.mp3'
        elif message_type == 'sticker':
            with io.BytesIO() as input_bytes:
                input_file.download(out=input_bytes)

                try:
                    image = PIL.Image.open(input_bytes)

                    with io.BytesIO() as image_bytes:
                        image.save(image_bytes, format='PNG')

                        image_bytes.seek(0)

                        output_bytes.write(image_bytes.read())

                        output_type = constants.OutputType.PHOTO

                        sticker = message['sticker']
                        emoji = sticker['emoji']
                        set_name = sticker['set_name']

                        caption = f'Sticker for the emoji "{emoji}" from the set "{set_name}"'
                except Exception as error:
                    logger.error(f'PIL error: {error}')
        else:
            if probe:
                for stream in probe['streams']:
                    codec_name = stream.get('codec_name')

                    if codec_name is not None:
                        invalid_format = codec_name

                    if codec_name in constants.VIDEO_CODEC_NAMES:
                        output_type = constants.OutputType.VIDEO

                        mp4_bytes = utils.convert(output_type, input_video_url=input_file_url)

                        if not utils.ensure_valid_converted_file(
                            file_bytes=mp4_bytes,
                            update=update,
                            context=context
                        ):
                            return

                        if mp4_bytes is not None:
                            output_bytes.write(mp4_bytes)

                        break

                    continue

                if output_type == constants.OutputType.NONE:
                    for stream in probe['streams']:
                        codec_name = stream.get('codec_name')

                        if codec_name is not None:
                            invalid_format = codec_name

                        if codec_name in constants.AUDIO_CODEC_NAMES:
                            output_type = constants.OutputType.AUDIO

                            opus_bytes = utils.convert(output_type, input_audio_url=input_file_url)

                            if not utils.ensure_valid_converted_file(
                                file_bytes=opus_bytes,
                                update=update,
                                context=context
                            ):
                                return

                            if opus_bytes is not None:
                                output_bytes.write(opus_bytes)

                            break
                        elif codec_name == 'opus':
                            input_file.download(out=output_bytes)

                            output_type = constants.OutputType.AUDIO

                            break

                        continue

        if output_type == constants.OutputType.NONE:
            with io.BytesIO() as input_bytes:
                input_file.download(out=input_bytes)

                input_bytes.seek(0)

                try:
                    images = pdf2image.convert_from_bytes(input_bytes.read())
                    image = images[0]

                    with io.BytesIO() as image_bytes:
                        image.save(image_bytes, format='PNG')

                        image_bytes.seek(0)

                        output_bytes.write(image_bytes.read())

                        output_type = constants.OutputType.PHOTO
                except Exception as error:
                    logger.error(f'pdf2image error: {error}')

                if output_type == constants.OutputType.NONE:
                    try:
                        image = PIL.Image.open(input_bytes)

                        with io.BytesIO() as image_bytes:
                            image.save(image_bytes, format='WEBP')

                            image_bytes.seek(0)

                            output_bytes.write(image_bytes.read())

                            output_type = constants.OutputType.STICKER
                    except Exception as error:
                        logger.error(f'PIL error: {error}')

        if output_type == constants.OutputType.NONE:
            if chat_type == telegram.Chat.PRIVATE:
                if invalid_format is None and input_file_url is not None:
                    parts = os.path.splitext(input_file_url)

                    if parts is not None and len(parts) >= 2:
                        extension = parts[1]

                        if extension is not None:
                            invalid_format = extension[1:]

                bot.send_message(
                    chat_id=chat_id,
                    text=f'File type "{invalid_format}" is not yet supported.',
                    reply_to_message_id=message_id
                )

            return

        output_bytes.seek(0)

        output_file_size = output_bytes.getbuffer().nbytes

        if caption is None and input_file_name is not None:
            caption = input_file_name[:telegram.constants.MAX_CAPTION_LENGTH]

        if output_type == constants.OutputType.AUDIO:
            if not utils.ensure_size_under_limit(output_file_size, telegram.constants.MAX_FILESIZE_UPLOAD, update, context, file_reference_text='Converted file'):
                return

            bot.send_chat_action(chat_id, telegram.ChatAction.UPLOAD_VOICE)

            bot.send_voice(
                chat_id,
                output_bytes,
                caption=caption,
                reply_to_message_id=message_id
            )

            return
        elif output_type == constants.OutputType.VIDEO:
            if not utils.ensure_size_under_limit(output_file_size, telegram.constants.MAX_FILESIZE_UPLOAD, update, context, file_reference_text='Converted file'):
                return

            bot.send_chat_action(chat_id, telegram.ChatAction.UPLOAD_VIDEO)

            utils.send_video(bot, chat_id, message_id, output_bytes, caption, chat_type)

            return
        elif output_type == constants.OutputType.PHOTO:
            if not utils.ensure_size_under_limit(output_file_size, telegram.constants.MAX_PHOTOSIZE_UPLOAD, update, context, file_reference_text='Converted file'):
                return

            bot.send_photo(
                chat_id,
                output_bytes,
                caption=caption,
                reply_to_message_id=message_id
            )

            return
        elif output_type == constants.OutputType.STICKER:
            bot.send_sticker(
                chat_id,
                output_bytes,
                reply_to_message_id=message_id
            )

            return
        elif output_type == constants.OutputType.FILE:
            if not utils.ensure_size_under_limit(output_file_size, telegram.constants.MAX_FILESIZE_UPLOAD, update, context, file_reference_text='Converted file'):
                return

            bot.send_chat_action(chat_id, telegram.ChatAction.UPLOAD_DOCUMENT)

            bot.send_document(
                chat_id,
                output_bytes,
                reply_to_message_id=message_id
            )

            return

    if chat_type == telegram.Chat.PRIVATE:
        bot.send_message(
            chat_id,
            'File type is not yet supported.',
            reply_to_message_id=message_id
        )


def message_video_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    message = update.effective_message

    if message is None:
        return

    chat = update.effective_chat

    if chat is None:
        return

    chat_type = chat.type
    bot = context.bot

    if chat_type != telegram.Chat.PRIVATE:
        return

    if cli_args.debug and not utils.check_admin(bot, context, message, analytics_handler, ADMIN_USER_ID):
        return

    message_id = message.message_id
    chat_id = message.chat.id
    attachment = message.video

    if attachment is None:
        return

    file_size = attachment.file_size

    if file_size is not None and not utils.ensure_size_under_limit(file_size, telegram.constants.MAX_FILESIZE_DOWNLOAD, update, context):
        return

    user = update.effective_user

    input_file_id = attachment.file_id

    if user is not None:
        create_or_update_user(bot, user)

        analytics_handler.track(context, analytics.AnalyticsType.MESSAGE, user)

    bot.send_chat_action(chat_id, telegram.ChatAction.TYPING)

    input_file = bot.get_file(input_file_id)
    input_file_url = input_file.file_path

    probe = None

    try:
        probe = ffmpeg.probe(input_file_url)
    except ffmpeg.Error:
        pass

    with io.BytesIO() as output_bytes:
        output_type = constants.OutputType.NONE

        invalid_format = None

        if probe:
            for stream in probe['streams']:
                codec_name = stream.get('codec_name')

                if codec_name is not None:
                    invalid_format = codec_name

                if codec_name in constants.VIDEO_CODEC_NAMES:
                    output_type = constants.OutputType.VIDEO_NOTE

                    mp4_bytes = utils.convert(output_type, input_video_url=input_file_url)

                    if not utils.ensure_valid_converted_file(
                        file_bytes=mp4_bytes,
                        update=update,
                        context=context
                    ):
                        return

                    if mp4_bytes is not None:
                        output_bytes.write(mp4_bytes)

                    break

                continue

        if output_type == constants.OutputType.NONE:
            if invalid_format is None and input_file_url is not None:
                parts = os.path.splitext(input_file_url)

                if parts is not None and len(parts) >= 2:
                    extension = parts[1]

                    if extension is not None:
                        invalid_format = extension[1:]

            bot.send_message(
                chat_id=chat_id,
                text=f'File type "{invalid_format}" is not yet supported.',
                reply_to_message_id=message_id
            )

            return

        output_bytes.seek(0)

        output_file_size = output_bytes.getbuffer().nbytes

        if output_type == constants.OutputType.VIDEO_NOTE:
            if not utils.ensure_size_under_limit(output_file_size, telegram.constants.MAX_FILESIZE_UPLOAD, update, context, file_reference_text='Converted file'):
                return

            bot.send_chat_action(chat_id, telegram.ChatAction.UPLOAD_VIDEO)

            utils.send_video_note(bot, chat_id, message_id, output_bytes)

            return

    bot.send_message(
        chat_id,
        'File type is not yet supported.',
        reply_to_message_id=message_id
    )


def message_text_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    message = update.effective_message

    if message is None:
        return

    chat = update.effective_chat

    if chat is None:
        return

    chat_type = chat.type
    bot = context.bot

    if cli_args.debug and not utils.check_admin(bot, context, message, analytics_handler, ADMIN_USER_ID):
        return

    message_id = message.message_id
    chat_id = message.chat.id
    user = message.from_user
    entities = message.parse_entities()

    if user is not None:
        create_or_update_user(bot, user)

        analytics_handler.track(context, analytics.AnalyticsType.MESSAGE, user)

    valid_entities = {
        entity: text for entity, text in entities.items() if entity.type in [telegram.MessageEntity.URL, telegram.MessageEntity.TEXT_LINK]
    }
    entity, text = next(iter(valid_entities.items()))

    if entity is None:
        return

    input_link = entity.url

    if input_link is None:
        input_link = text

    with io.BytesIO() as output_bytes:
        caption = None
        video_url = None
        audio_url = None

        try:
            yt_dl_options = {
                'logger': logger,
                'no_color': True
            }

            with youtube_dl.YoutubeDL(yt_dl_options) as yt_dl:
                video_info = yt_dl.extract_info(input_link, download=False)

            if 'entries' in video_info:
                video = video_info['entries'][0]
            else:
                video = video_info

            if 'title' in video:
                caption = video['title']
            else:
                caption = input_link

            file_size = None

            if 'requested_formats' in video:
                requested_formats = video['requested_formats']

                video_data = list(filter(lambda requested_format: requested_format['vcodec'] != 'none', requested_formats))[0]
                audio_data = list(filter(lambda requested_format: requested_format['acodec'] != 'none', requested_formats))[0]

                if 'filesize' in video_data:
                    file_size = video_data['filesize']

                video_url = video_data['url']

                if file_size is None:
                    file_size = utils.get_file_size(video_url)

                audio_url = audio_data['url']
            elif 'url' in video:
                video_url = video['url']
                file_size = utils.get_file_size(video_url)

            if file_size is not None:
                if not utils.ensure_size_under_limit(file_size, telegram.constants.MAX_FILESIZE_UPLOAD, update, context):
                    return

        except Exception as error:
            logger.error(f'youtube-dl error: {error}')

        if chat_type == telegram.Chat.PRIVATE and (caption is None or video_url is None):
            bot.send_message(
                chat_id,
                'No video found on this link.',
                disable_web_page_preview=True,
                reply_to_message_id=message_id
            )

            return

        mp4_bytes = utils.convert(constants.OutputType.VIDEO, input_video_url=video_url, input_audio_url=audio_url)

        if not utils.ensure_valid_converted_file(
            file_bytes=mp4_bytes,
            update=update,
            context=context
        ):
            return

        if mp4_bytes is not None:
            output_bytes.write(mp4_bytes)

        output_bytes.seek(0)

        if caption is not None:
            caption = caption[:telegram.constants.MAX_CAPTION_LENGTH]

        utils.send_video(bot, chat_id, message_id, output_bytes, caption, chat_type)


def message_answer_handler(update: telegram.Update, context: telegram.ext.CallbackContext) -> None:
    callback_query = update.callback_query

    if callback_query is None:
        return

    raw_callback_data = callback_query.data

    if raw_callback_data is None:
        callback_query.answer()

        return

    callback_data = json.loads(raw_callback_data)

    if callback_data is None:
        callback_query.answer()

        return

    message = update.effective_message

    if message is None:
        return

    chat = update.effective_chat

    if chat is None:
        return

    chat_type = chat.type
    bot = context.bot

    attachment = message.effective_attachment

    if attachment is None:
        return

    if not isinstance(attachment, telegram.Video):
        return

    file_size = attachment.file_size

    if file_size is not None and not utils.ensure_size_under_limit(file_size, telegram.constants.MAX_FILESIZE_DOWNLOAD, update, context):
        return

    attachment_file_id = attachment.file_id

    message_id = message.message_id
    chat_id = message.chat.id

    user = update.effective_user

    if user is not None:
        create_or_update_user(bot, user)

        analytics_handler.track(context, analytics.AnalyticsType.MESSAGE, user)

    if chat_type == telegram.Chat.PRIVATE:
        bot.send_chat_action(chat_id, telegram.ChatAction.TYPING)

    input_file = bot.get_file(attachment_file_id)
    input_file_url = input_file.file_path

    probe = None

    try:
        probe = ffmpeg.probe(input_file_url)
    except ffmpeg.Error:
        pass

    with io.BytesIO() as output_bytes:
        output_type = constants.OutputType.NONE

        invalid_format = None

        if probe:
            for stream in probe['streams']:
                codec_name = stream.get('codec_name')

                if codec_name is not None:
                    invalid_format = codec_name

                if codec_name in constants.VIDEO_CODEC_NAMES:
                    output_type = constants.OutputType.VIDEO_NOTE

                    mp4_bytes = utils.convert(output_type, input_video_url=input_file_url)

                    if not utils.ensure_valid_converted_file(
                        file_bytes=mp4_bytes,
                        update=update,
                        context=context
                    ):
                        callback_query.answer()

                        return

                    if mp4_bytes is not None:
                        output_bytes.write(mp4_bytes)

                    break

                continue

        if output_type == constants.OutputType.NONE:
            if chat_type == telegram.Chat.PRIVATE:
                if invalid_format is None and input_file_url is not None:
                    parts = os.path.splitext(input_file_url)

                    if parts is not None and len(parts) >= 2:
                        extension = parts[1]

                        if extension is not None:
                            invalid_format = extension[1:]

                bot.send_message(
                    chat_id=chat_id,
                    text=f'File type "{invalid_format}" is not yet supported.',
                    reply_to_message_id=message_id
                )

            callback_query.answer()

            return

        output_bytes.seek(0)

        output_file_size = output_bytes.getbuffer().nbytes

        if output_type == constants.OutputType.VIDEO_NOTE:
            if not utils.ensure_size_under_limit(output_file_size, telegram.constants.MAX_FILESIZE_UPLOAD, update, context, file_reference_text='Converted file'):
                callback_query.answer()

                return

            bot.send_chat_action(chat_id, telegram.ChatAction.UPLOAD_VIDEO)

            utils.send_video_note(bot, chat_id, message_id, output_bytes)

            callback_query.answer()

            return

    if chat_type == telegram.Chat.PRIVATE:
        bot.send_message(
            chat_id,
            'File type is not yet supported.',
            reply_to_message_id=message_id
        )

    callback_query.answer()


def error_handler(update: object, context: telegram.ext.CallbackContext) -> None:
    update_str = update.to_dict() if isinstance(update, telegram.Update) else str(update)

    logger.error(f'Update "{json.dumps(update_str, indent=4, ensure_ascii=False)}" caused error "{context.error}"')


def main() -> None:
    message_file_filters = (
        (
            telegram.ext.Filters.audio |
            telegram.ext.Filters.document |
            telegram.ext.Filters.photo
        ) & (
            ~ telegram.ext.Filters.animation
        )
    ) | (
        telegram.ext.Filters.chat_type.private & (
            telegram.ext.Filters.voice |
            telegram.ext.Filters.sticker
        )
    )

    message_text_filters = (
        telegram.ext.Filters.chat_type.private & (
            telegram.ext.Filters.text & (
                telegram.ext.Filters.entity(telegram.MessageEntity.URL) |
                telegram.ext.Filters.entity(telegram.MessageEntity.TEXT_LINK)
            )
        )
    )

    video_filter = telegram.ext.Filters.video

    dispatcher = updater.dispatcher

    dispatcher.add_handler(telegram.ext.CommandHandler('start', start_command_handler))

    dispatcher.add_handler(telegram.ext.CommandHandler('restart', restart_command_handler))
    dispatcher.add_handler(telegram.ext.CommandHandler('logs', logs_command_handler))
    dispatcher.add_handler(telegram.ext.CommandHandler('users', users_command_handler, pass_args=True))

    dispatcher.add_handler(telegram.ext.MessageHandler(message_file_filters, message_file_handler, run_async=True))
    dispatcher.add_handler(telegram.ext.MessageHandler(video_filter, message_video_handler, run_async=True))
    dispatcher.add_handler(telegram.ext.MessageHandler(message_text_filters, message_text_handler, run_async=True))
    dispatcher.add_handler(telegram.ext.CallbackQueryHandler(message_answer_handler, run_async=True))

    if cli_args.debug:
        logger.info('Started polling')

        updater.start_polling(timeout=0.01)
    else:
        dispatcher.add_error_handler(error_handler)

        if cli_args.server and not cli_args.polling:
            logger.info('Started webhook')

            if config:
                webhook = config['Webhook']

                port = int(webhook['Port'])
                key = webhook['Key']
                cert = webhook['Cert']
                url = webhook['Url'] + BOT_TOKEN

                if cli_args.set_webhook:
                    logger.info('Updated webhook')
                else:
                    setattr(updater.bot, 'set_webhook', (lambda *args, **kwargs: False))

                updater.start_webhook(
                    listen='0.0.0.0',
                    port=port,
                    url_path=BOT_TOKEN,
                    key=key,
                    cert=cert,
                    webhook_url=url
                )
            else:
                logger.error('Missing bot webhook config')

                return
        else:
            logger.info('Started polling')

            updater.start_polling()

    logger.info('Bot started. Press Ctrl-C to stop.')

    updater.bot.send_message(ADMIN_USER_ID, 'Bot has been restarted')
    updater.idle()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument('-d', '--debug', action='store_true')

    parser.add_argument('-p', '--polling', action='store_true')
    parser.add_argument('-sw', '--set-webhook', action='store_true')
    parser.add_argument('-s', '--server', action='store_true')

    cli_args = parser.parse_args()

    if cli_args.debug:
        logger.info('Debug')

    config = None

    try:
        config = configparser.ConfigParser()

        config.read('config.cfg')

        BOT_NAME = config.get('Telegram', 'Name' if cli_args.server else 'TestName')
        BOT_TOKEN = config.get('Telegram', 'Key' if cli_args.server else 'TestKey')
    except configparser.Error as config_error:
        logger.error(f'Config error: {config_error}')

        sys.exit(1)

    if not BOT_TOKEN:
        logger.error('Missing bot token')

        sys.exit(2)

    updater = telegram.ext.Updater(BOT_TOKEN)
    analytics_handler = analytics.AnalyticsHandler()

    try:
        ADMIN_USER_ID = config.getint('Telegram', 'Admin')

        if not cli_args.debug:
            analytics_handler.googleToken = config.get('Google', 'Key')
    except configparser.Error as config_error:
        logger.warning(f'Config error: {config_error}')

    analytics_handler.userAgent = BOT_NAME

    main()
