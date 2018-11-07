#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import configparser
import io
import logging
import os
import sys
import time

from telegram import ChatAction
from telegram.ext import (
    CommandHandler, MessageHandler,
    Filters, Updater
)

import ffmpeg

from analytics import Analytics, AnalyticsType
from constants import LOGS_FORMAT
from database import User
from utils import check_admin

BOT_TOKEN = None

ADMIN_USER_ID = None

logging.basicConfig(format=LOGS_FORMAT, level=logging.INFO)

error_logging_handler = logging.FileHandler('errors.log')
error_logging_handler.setFormatter(logging.Formatter(LOGS_FORMAT))
error_logging_handler.setLevel(logging.ERROR)

logging.getLogger().addHandler(error_logging_handler)

logger = logging.getLogger(__name__)

analytics = None


def start_command_handler(bot, update):
    message = update.message

    chat_id = message.chat_id
    user = message.from_user

    analytics.track(AnalyticsType.COMMAND, user, '/start')

    db_user = User.create_user(user.id, user.username)

    if db_user and ADMIN_USER_ID:
        bot.send_message(ADMIN_USER_ID, 'New user: {} (@{})'.format(db_user.telegram_id, db_user.telegram_username))

    bot.send_message(chat_id, 'Send me an audio file to convert it to a voice message.')


def restart_command_handler(bot, update):
    message = update.message

    if not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    bot.send_message(message.chat_id, 'Restarting...' if cli_args.debug else 'Restarting in 1 second...')

    time.sleep(0.2 if cli_args.debug else 1)

    os.execl(sys.executable, sys.executable, *sys.argv)


def logs_command_handler(bot, update):
    message = update.message
    chat_id = message.chat_id

    if not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    try:
        bot.send_document(chat_id, open('errors.log', 'rb'))
    except:
        bot.send_message(chat_id, 'Log is empty')


def users_command_handler(bot, update):
    message = update.message
    chat_id = message.chat_id

    if not check_admin(bot, message, analytics, ADMIN_USER_ID):
        return

    bot.send_message(chat_id, User.get_users_table())


def message_handler(bot, update):
    message = update.message

    message_id = message.message_id
    chat_id = message.chat.id
    user = message.from_user
    attachment = message.effective_attachment

    input_file_id = attachment.file_id
    input_file_name = attachment.file_name if getattr(attachment, 'file_name', None) else attachment.title

    analytics.track(AnalyticsType.MESSAGE, user)

    input_file = bot.get_file(input_file_id)
    input_file_path = input_file.file_path

    probe = ffmpeg.probe(input_file_path)

    with io.BytesIO() as input_bytes:
        for stream in probe['streams']:
            codec_name = stream['codec_name']

            if codec_name == 'mp3':
                opus_bytes = ffmpeg.input(input_file_path).output('pipe:', format='opus', strict='-2').run(capture_stdout=True)[0]

                input_bytes.write(opus_bytes)

                break
            elif codec_name == 'opus':
                input_file.download(out=input_bytes)

                break
            else:
                return

        bot.send_chat_action(chat_id, ChatAction.UPLOAD_AUDIO)

        input_bytes.seek(0)

        bot.send_voice(
            chat_id,
            input_bytes,
            caption=input_file_name,
            reply_to_message_id=message_id
        )


def error_handler(bot, update, error):
    logger.error('Update "{}" caused error "{}"'.format(update, error))


def main():
    updater = Updater(BOT_TOKEN)

    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start_command_handler))

    dispatcher.add_handler(CommandHandler('restart', restart_command_handler))
    dispatcher.add_handler(CommandHandler('logs', logs_command_handler))
    dispatcher.add_handler(CommandHandler('users', users_command_handler))

    dispatcher.add_handler(MessageHandler(Filters.audio | Filters.document, message_handler))

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
                    updater.bot.setWebhook = (lambda *args, **kwargs: None)

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

    analytics = Analytics()

    try:
        ADMIN_USER_ID = config.getint('Telegram', 'Admin')

        analytics.googleToken = config.get('Google', 'Key')
    except configparser.Error as error:
        logger.warning('Config error: {}'.format(error))

    main()
