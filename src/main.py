#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from threading import Thread

import argparse
import configparser
import io
import json
import logging
import os
import sys

from constants import LOGS_FORMAT, LoggerFilter

logging.basicConfig(format=LOGS_FORMAT, level=logging.INFO)

error_logging_handler = logging.FileHandler('errors.log')
error_logging_handler.setFormatter(logging.Formatter(LOGS_FORMAT))
error_logging_handler.setLevel(logging.ERROR)
error_logging_handler.addFilter(LoggerFilter(logging.ERROR))

logging.getLogger().addHandler(error_logging_handler)

warning_logging_handler = logging.FileHandler('warnings.log')
warning_logging_handler.setFormatter(logging.Formatter(LOGS_FORMAT))
warning_logging_handler.setLevel(logging.WARNING)
warning_logging_handler.addFilter(LoggerFilter(logging.WARNING))

logging.getLogger().addHandler(warning_logging_handler)

from PIL import Image
from pdf2image import convert_from_bytes
from telegram import Chat, ChatAction, MessageEntity, ParseMode, Update
from telegram.constants import MAX_CAPTION_LENGTH, MAX_FILESIZE_DOWNLOAD, MAX_FILESIZE_UPLOAD
from telegram.ext import (
    CallbackQueryHandler, CommandHandler, MessageHandler,
    Filters, Updater,
    CallbackContext
)

import ffmpeg
import youtube_dl

from analytics import Analytics, AnalyticsType
from constants import (
    MAX_PHOTO_FILESIZE_UPLOAD, VIDEO_CODEC_NAMES, VIDEO_CODED_TYPE, ATTACHMENT_FILE_ID_KEY,
    OutputType
)
from database import User
from utils import (
    check_admin, ensure_size_under_limit,
    send_video, send_video_note,
    convert
)

BOT_TOKEN = None

ADMIN_USER_ID = None

logger = logging.getLogger(__name__)

updater = None
analytics = None


def stop_and_restart():
    updater.stop()
    os.execl(sys.executable, sys.executable, *sys.argv)


def create_or_update_user(bot, user):
    db_user = User.create_or_update_user(user.id, user.username)

    if db_user and ADMIN_USER_ID:
        bot.send_message(ADMIN_USER_ID, 'New user: {}'.format(db_user.get_markdown_description()), parse_mode=ParseMode.MARKDOWN)


def start_command_handler(update: Update, context: CallbackContext):
    message = update.message
    bot = context.bot

    chat_id = message.chat_id
    user = message.from_user

    create_or_update_user(bot, user)

    analytics.track(AnalyticsType.COMMAND, user, '/start')

    bot.send_message(chat_id, 'Send me a file to try to convert it to a nice message or a sticker.')


def restart_command_handler(update: Update, context: CallbackContext):
    message = update.message
    bot = context.bot

    if not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    bot.send_message(message.chat_id, 'Restarting...')

    Thread(target=stop_and_restart).start()


def logs_command_handler(update: Update, context: CallbackContext):
    message = update.message
    bot = context.bot

    chat_id = message.chat_id

    if not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    try:
        bot.send_document(chat_id, open('errors.log', 'rb'))
    except:
        bot.send_message(chat_id, 'Log is empty')


def users_command_handler(update: Update, context: CallbackContext):
    message = update.message
    bot = context.bot

    chat_id = message.chat_id

    if not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    bot.send_message(chat_id, User.get_users_table('updated' in context.args), parse_mode=ParseMode.MARKDOWN)


def message_file_handler(update: Update, context: CallbackContext):
    message = update.message
    chat_type = update.effective_chat.type
    bot = context.bot

    if cli_args.debug and not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    message_id = message.message_id
    chat_id = message.chat.id
    attachment = message.effective_attachment

    if type(attachment) is list:
        if chat_type == Chat.PRIVATE:
            bot.send_message(
                chat_id,
                'You need to send the image as a file to convert it to a sticker.',
                reply_to_message_id=message_id
            )

        return

    if not ensure_size_under_limit(attachment.file_size, MAX_FILESIZE_DOWNLOAD, update, context):
        return

    user = message.from_user

    input_file_id = attachment.file_id
    input_file_name = attachment.file_name if getattr(attachment, 'file_name', None) else attachment.title

    create_or_update_user(bot, user)

    analytics.track(AnalyticsType.MESSAGE, user)

    if chat_type == Chat.PRIVATE:
        bot.send_chat_action(chat_id, ChatAction.TYPING)

    input_file = bot.get_file(input_file_id)
    input_file_url = input_file.file_path

    probe = None

    try:
        probe = ffmpeg.probe(input_file_url)
    except:
        pass

    with io.BytesIO() as output_bytes:
        output_type = OutputType.NONE

        invalid_format = None

        if probe:
            for stream in probe['streams']:
                codec_name = stream.get('codec_name')
                codec_type = stream.get('codec_type')

                if codec_name is not None and codec_type == VIDEO_CODED_TYPE:
                    invalid_format = codec_name

                if codec_name == 'mp3':
                    output_type = OutputType.AUDIO

                    opus_bytes = convert(output_type, input_audio_url=input_file_url)

                    output_bytes.write(opus_bytes)

                    break
                elif codec_name == 'opus':
                    input_file.download(out=output_bytes)

                    output_type = OutputType.AUDIO

                    break
                elif codec_name in VIDEO_CODEC_NAMES:
                    output_type = OutputType.VIDEO

                    mp4_bytes = convert(output_type, input_video_url=input_file_url)

                    output_bytes.write(mp4_bytes)

                    break
                else:
                    continue

        if output_type == OutputType.NONE:
            with io.BytesIO() as input_bytes:
                input_file.download(out=input_bytes)

                try:
                    images = convert_from_bytes(input_bytes.getbuffer())
                    image = images[0]

                    with io.BytesIO() as image_bytes:
                        image.save(image_bytes, format='PNG')

                        output_bytes.write(image_bytes.getbuffer())

                        output_type = OutputType.PHOTO
                except Exception as error:
                    logger.error('pdf2image error: {}'.format(error))

                if output_type == OutputType.NONE:
                    try:
                        image = Image.open(input_bytes)

                        with io.BytesIO() as image_bytes:
                            image.save(image_bytes, format='WEBP')

                            output_bytes.write(image_bytes.getbuffer())

                            output_type = OutputType.STICKER
                    except Exception as error:
                        logger.error('PIL error: {}'.format(error))

        if output_type == OutputType.NONE:
            if chat_type == Chat.PRIVATE:
                if invalid_format is None:
                    invalid_format = os.path.splitext(input_file_url)[1][1:]

                bot.send_message(
                    chat_id,
                    'File type "{}" is not yet supported.'.format(invalid_format),
                    reply_to_message_id=message_id
                )

            return

        output_bytes.seek(0)

        output_file_size = output_bytes.getbuffer().nbytes
        caption = None

        if input_file_name is not None:
            caption = input_file_name[:MAX_CAPTION_LENGTH]

        if output_type == OutputType.AUDIO:
            if not ensure_size_under_limit(output_file_size, MAX_FILESIZE_UPLOAD, update, context, file_reference_text='Converted file'):
                return

            bot.send_chat_action(chat_id, ChatAction.UPLOAD_AUDIO)

            bot.send_voice(
                chat_id,
                output_bytes,
                caption=caption,
                reply_to_message_id=message_id
            )

            return
        elif output_type == OutputType.VIDEO:
            if not ensure_size_under_limit(output_file_size, MAX_FILESIZE_UPLOAD, update, context, file_reference_text='Converted file'):
                return

            bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)

            send_video(bot, chat_id, message_id, output_bytes, attachment, caption, chat_type)

            return
        elif output_type == OutputType.PHOTO:
            if not ensure_size_under_limit(output_file_size, MAX_PHOTO_FILESIZE_UPLOAD, update, context, file_reference_text='Converted file'):
                return

            bot.send_photo(
                chat_id,
                output_bytes,
                caption=caption,
                reply_to_message_id=message_id
            )

            return
        elif output_type == OutputType.STICKER:
            bot.send_sticker(
                chat_id,
                output_bytes,
                reply_to_message_id=message_id
            )

            return

    if chat_type == Chat.PRIVATE:
        bot.send_message(
            chat_id,
            'File type is not yet supported.',
            reply_to_message_id=message_id
        )


def message_video_handler(update: Update, context: CallbackContext):
    message = update.effective_message
    chat_type = update.effective_chat.type
    bot = context.bot

    if chat_type != Chat.PRIVATE:
        return

    if cli_args.debug and not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    message_id = message.message_id
    chat_id = message.chat.id
    attachment = message.video

    if not ensure_size_under_limit(attachment.file_size, MAX_FILESIZE_DOWNLOAD, update, context):
        return

    user = update.effective_user

    input_file_id = attachment.file_id

    create_or_update_user(bot, user)

    analytics.track(AnalyticsType.MESSAGE, user)

    bot.send_chat_action(chat_id, ChatAction.TYPING)

    input_file = bot.get_file(input_file_id)
    input_file_url = input_file.file_path

    probe = None

    try:
        probe = ffmpeg.probe(input_file_url)
    except:
        pass

    with io.BytesIO() as output_bytes:
        output_type = OutputType.NONE

        invalid_format = None

        if probe:
            for stream in probe['streams']:
                codec_name = stream.get('codec_name')
                codec_type = stream.get('codec_type')

                if codec_name is not None and codec_type == VIDEO_CODED_TYPE:
                    invalid_format = codec_name

                if codec_name in VIDEO_CODEC_NAMES:
                    output_type = OutputType.VIDEO_NOTE

                    mp4_bytes = convert(output_type, input_video_url=input_file_url)

                    output_bytes.write(mp4_bytes)

                    break
                else:
                    continue

        if output_type == OutputType.NONE:
            if invalid_format is None:
                invalid_format = os.path.splitext(input_file_url)[1][1:]

            bot.send_message(
                chat_id,
                'File type "{}" is not yet supported.'.format(invalid_format),
                reply_to_message_id=message_id
            )

        output_bytes.seek(0)

        output_file_size = output_bytes.getbuffer().nbytes

        if output_type == OutputType.VIDEO_NOTE:
            if not ensure_size_under_limit(output_file_size, MAX_FILESIZE_UPLOAD, update, context, file_reference_text='Converted file'):
                return

            bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)

            send_video_note(bot, chat_id, message_id, output_bytes)

            return

    bot.send_message(
        chat_id,
        'File type is not yet supported.',
        reply_to_message_id=message_id
    )


def message_text_handler(update: Update, context: CallbackContext):
    message = update.message
    chat_type = update.effective_chat.type
    bot = context.bot

    if cli_args.debug and not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    message_id = message.message_id
    chat_id = message.chat.id
    user = message.from_user
    entities = message.parse_entities()

    create_or_update_user(bot, user)

    analytics.track(AnalyticsType.MESSAGE, user)

    entity, text = next(((entity, text) for entity, text in entities.items() if entity.type in [MessageEntity.URL, MessageEntity.TEXT_LINK]), None)

    if entity is None:
        return

    input_link = entity.url

    if input_link is None:
        input_link = text

    with io.BytesIO() as output_bytes:
        caption = None
        video_url = None

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

            requested_formats = video['requested_formats']

            video_data = list(filter(lambda format: format['vcodec'] != 'none', requested_formats))[0]
            audio_data = list(filter(lambda format: format['acodec'] != 'none', requested_formats))[0]

            if not ensure_size_under_limit(video_data['filesize'], MAX_FILESIZE_UPLOAD, update, context):
                return

            video_url = video_data['url']
            audio_url = audio_data['url']
        except Exception as error:
            logger.error('youtube-dl error: {}'.format(error))

        if chat_type == Chat.PRIVATE and (caption is None or video_url is None):
            bot.send_message(
                chat_id,
                'No video found on "{}".'.format(input_link),
                disable_web_page_preview=True,
                reply_to_message_id=message_id
            )

            return

        mp4_bytes = convert(OutputType.VIDEO, input_video_url=video_url, input_audio_url=audio_url)

        output_bytes.write(mp4_bytes)
        output_bytes.seek(0)

        caption = caption[:MAX_CAPTION_LENGTH]

        # Video note isn't supported for videos downloaded from URLs yet.
        send_video(bot, chat_id, message_id, output_bytes, None, caption, chat_type)


def message_answer_handler(update: Update, context: CallbackContext):
    callback_query = update.callback_query
    callback_data = json.loads(callback_query.data)

    if not callback_data:
        callback_query.answer()

        return

    original_attachment_file_id = callback_data[ATTACHMENT_FILE_ID_KEY]

    message = update.effective_message
    chat_type = update.effective_chat.type
    bot = context.bot

    message_id = message.message_id
    chat_id = message.chat.id

    user = update.effective_user

    create_or_update_user(bot, user)

    analytics.track(AnalyticsType.MESSAGE, user)

    if chat_type == Chat.PRIVATE:
        bot.send_chat_action(chat_id, ChatAction.TYPING)

    input_file = bot.get_file(original_attachment_file_id)
    input_file_url = input_file.file_path

    probe = None

    try:
        probe = ffmpeg.probe(input_file_url)
    except:
        pass

    with io.BytesIO() as output_bytes:
        output_type = OutputType.NONE

        invalid_format = None

        if probe:
            for stream in probe['streams']:
                codec_name = stream.get('codec_name')
                codec_type = stream.get('codec_type')

                if codec_name is not None and codec_type == VIDEO_CODED_TYPE:
                    invalid_format = codec_name

                if codec_name in VIDEO_CODEC_NAMES:
                    output_type = OutputType.VIDEO_NOTE

                    mp4_bytes = convert(output_type, input_video_url=input_file_url)

                    output_bytes.write(mp4_bytes)

                    break
                else:
                    continue

        if output_type == OutputType.NONE:
            if chat_type == Chat.PRIVATE:
                if invalid_format is None:
                    invalid_format = os.path.splitext(input_file_url)[1][1:]

                bot.send_message(
                    chat_id,
                    'File type "{}" is not yet supported.'.format(invalid_format),
                    reply_to_message_id=message_id
                )

            callback_query.answer()

            return

        output_bytes.seek(0)

        output_file_size = output_bytes.getbuffer().nbytes

        if output_type == OutputType.VIDEO_NOTE:
            if not ensure_size_under_limit(output_file_size, MAX_FILESIZE_UPLOAD, update, context, file_reference_text='Converted file'):
                callback_query.answer()

                return

            bot.send_chat_action(chat_id, ChatAction.UPLOAD_VIDEO)

            send_video_note(bot, chat_id, message_id, output_bytes)

            callback_query.answer()

            return

    if chat_type == Chat.PRIVATE:
        bot.send_message(
            chat_id,
            'File type is not yet supported.',
            reply_to_message_id=message_id
        )

    callback_query.answer()


def error_handler(update: Update, context: CallbackContext):
    logger.error('Update "{}" caused error "{}"'.format(json.dumps(update.to_dict(), indent=4), context.error))


def main():
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start_command_handler))

    dispatcher.add_handler(CommandHandler('restart', restart_command_handler))
    dispatcher.add_handler(CommandHandler('logs', logs_command_handler))
    dispatcher.add_handler(CommandHandler('users', users_command_handler, pass_args=True))

    dispatcher.add_handler(MessageHandler((Filters.audio | Filters.document | Filters.photo) & (~ Filters.animation), message_file_handler))
    dispatcher.add_handler(MessageHandler(Filters.video, message_video_handler))
    dispatcher.add_handler(MessageHandler(Filters.private & (Filters.text & (Filters.entity(MessageEntity.URL) | Filters.entity(MessageEntity.TEXT_LINK))), message_text_handler))
    dispatcher.add_handler(CallbackQueryHandler(message_answer_handler))

    dispatcher.add_error_handler(error_handler)

    if cli_args.debug:
        logger.info('Started polling')

        updater.start_polling(timeout=0.01)
    else:
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
                    updater.bot.set_webhook = (lambda *args, **kwargs: None)

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

    if ADMIN_USER_ID:
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

        BOT_TOKEN = config.get('Telegram', 'Key' if cli_args.server else 'TestKey')
    except configparser.Error as error:
        logger.error('Config error: {}'.format(error))

        sys.exit(1)

    if not BOT_TOKEN:
        logger.error('Missing bot token')

        sys.exit(2)

    updater = Updater(BOT_TOKEN, use_context=True)
    analytics = Analytics()

    try:
        ADMIN_USER_ID = config.getint('Telegram', 'Admin')

        if not cli_args.debug:
            analytics.googleToken = config.get('Google', 'Key')
    except configparser.Error as error:
        logger.warning('Config error: {}'.format(error))

    main()
