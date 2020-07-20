# -*- coding: utf-8 -*-

import json
import logging

import ffmpeg
from telegram import (
    Chat, Update,
    InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import CallbackContext

from analytics import AnalyticsType
from constants import (
    MAX_VIDEO_NOTE_LENGTH,
    VIDEO_NOTE_CROP_OFFSET_PARAMS, VIDEO_NOTE_CROP_SIZE_PARAMS,
    OutputType
)

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
        message = update.effective_message
        chat = update.effective_chat

        message_id = message.message_id
        chat_id = chat.id

        context.bot.send_message(
            chat_id,
            '{} size {} exceeds the maximum limit of {} (limit imposed by Telegram, not by this bot).'.format(
                file_reference_text,
                get_size_string_from_bytes(size),
                get_size_string_from_bytes(limit)
            ),
            reply_to_message_id=message_id
        )

    return False


def ensure_valid_converted_file(file_bytes, update: Update, context: CallbackContext):
    if file_bytes is not None:
        return True

    chat_type = update.effective_chat.type

    if chat_type == Chat.PRIVATE:
        message = update.effective_message
        chat = update.effective_chat

        message_id = message.message_id
        chat_id = chat.id

        context.bot.send_message(
            chat_id=chat_id,
            text='File could not be converted.',
            reply_to_message_id=message_id
        )

    return False


def send_video(bot, chat_id, message_id, output_bytes, caption, chat_type):
    if chat_type == Chat.PRIVATE:
        data = {}

        button = InlineKeyboardButton('Rounded', callback_data=json.dumps(data))
        reply_markup = InlineKeyboardMarkup([[button]])
    else:
        reply_markup = None

    bot.send_video(
        chat_id,
        output_bytes,
        caption=caption,
        supports_streaming=True,
        reply_to_message_id=message_id,
        reply_markup=reply_markup
    )


def send_video_note(bot, chat_id, message_id, output_bytes):
    bot.send_video_note(
        chat_id,
        output_bytes,
        reply_to_message_id=message_id
    )


def get_file_size(video_url):
    info = ffmpeg.probe(video_url, show_entries='format=size')
    size = info.get('format', {}).get('size')

    return int(size)


def has_audio_stream(video_url):
    info = ffmpeg.probe(video_url, select_streams='a', show_entries='format=:streams=index')
    streams = info.get('streams', [])

    return len(streams) > 0


def convert(output_type, input_video_url=None, input_audio_url=None):
    try:
        if output_type == OutputType.AUDIO:
            return (
                ffmpeg
                    .input(input_audio_url)
                    .output('pipe:', format='opus', strict='-2')
                    .run(capture_stdout=True)
            )[0]
        elif output_type == OutputType.VIDEO:
            if input_audio_url is None:
                return (
                    ffmpeg
                        .input(input_video_url)
                        .output('pipe:', format='mp4', movflags='frag_keyframe+empty_moov', strict='-2')
                        .run(capture_stdout=True)
                )[0]
            else:
                input_video = ffmpeg.input(input_video_url)
                input_audio = ffmpeg.input(input_audio_url)

                return (
                    ffmpeg
                        .output(input_video, input_audio, 'pipe:', format='mp4', movflags='frag_keyframe+empty_moov', strict='-2')
                        .run(capture_stdout=True)
                )[0]
        elif output_type == OutputType.VIDEO_NOTE:
            # Copied from https://github.com/kkroening/ffmpeg-python/issues/184#issuecomment-504390452.

            ffmpeg_input = (
                ffmpeg
                    .input(input_video_url, t=MAX_VIDEO_NOTE_LENGTH)
            )
            ffmpeg_input_video = (
                ffmpeg_input
                    .video
                    .crop(
                        VIDEO_NOTE_CROP_OFFSET_PARAMS,
                        VIDEO_NOTE_CROP_OFFSET_PARAMS,
                        VIDEO_NOTE_CROP_SIZE_PARAMS,
                        VIDEO_NOTE_CROP_SIZE_PARAMS
                    )
            )

            ffmpeg_output: ffmpeg.nodes.OutputStream

            if has_audio_stream(input_video_url):
                ffmpeg_input_audio = ffmpeg_input.audio
                ffmpeg_joined = ffmpeg.concat(ffmpeg_input_video, ffmpeg_input_audio, v=1, a=1).node
                ffmpeg_output = ffmpeg.output(ffmpeg_joined[0], ffmpeg_joined[1], 'pipe:', format='mp4', movflags='frag_keyframe+empty_moov', strict='-2')
            else:
                ffmpeg_joined = ffmpeg.concat(ffmpeg_input_video, v=1).node
                ffmpeg_output = ffmpeg.output(ffmpeg_joined[0], 'pipe:', format='mp4', movflags='frag_keyframe+empty_moov', strict='-2')

            return ffmpeg_output.run(capture_stdout=True)[0]
        elif output_type == OutputType.FILE:
            return (
                ffmpeg
                    .input(input_audio_url)
                    .output('pipe:', format='mp3', strict='-2')
                    .run(capture_stdout=True)
            )[0]
    except ffmpeg.Error:
        return None


def get_size_string_from_bytes(bytes_count, suffix='B'):
    """
    Partially copied from https://stackoverflow.com/a/1094933/865175.
    """

    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(bytes_count) < 1000.0:
            return '%3.1f %s%s' % (bytes_count, unit, suffix)

        bytes_count /= 1000.0

    return '%.1f %s%s' % (bytes_count, 'Y', suffix)
