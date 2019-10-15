# -*- coding: utf-8 -*-

import logging

from telegram import Chat, Update
from telegram.ext import CallbackContext

from analytics import AnalyticsType

logger = logging.getLogger(__name__)


def check_admin(bot, message, analytics, admin_user_id):
    analytics.track(AnalyticsType.COMMAND, message.from_user, message.text)

    if not admin_user_id or message.from_user.id != admin_user_id:
        bot.send_message(message.chat_id, 'You are not allowed to use this command')

        return False

    return True


def ensure_size_under_limit(size, limit, update: Update, context: CallbackContext, file_reference_text='File'):
    if size <= limit:
        return True

    chat_type = update.effective_chat.type

    if chat_type == Chat.PRIVATE:
        message = update.message

        message_id = message.message_id
        chat_id = message.chat.id

        context.bot.send_message(
            chat_id,
            '{} size {} exceeds the maximum limit of {}.'.format(
                file_reference_text,
                get_size_string_from_bytes(size),
                get_size_string_from_bytes(limit)
            ),
            reply_to_message_id=message_id
        )

    return False


def get_size_string_from_bytes(bytes, suffix='B'):
    """
    Partially copied from https://stackoverflow.com/a/1094933/865175.
    """

    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(bytes) < 1000.0:
            return "%3.1f %s%s" % (bytes, unit, suffix)

        bytes /= 1000.0

    return "%.1f %s%s" % (bytes, 'Y', suffix)
