# -*- coding: utf-8 -*-

import io
import json
import logging
import typing

import ffmpeg
import telegram
import telegram.ext

import analytics
import constants

logger = logging.getLogger(__name__)


def check_admin(bot: telegram.Bot, message: telegram.Message, analytics_handler: analytics.AnalyticsHandler, admin_user_id: int) -> bool:
    analytics_handler.track(analytics.AnalyticsType.COMMAND, message.from_user, message.text)

    if not admin_user_id or message.from_user.id != admin_user_id:
        bot.send_message(message.chat_id, 'You are not allowed to use this command')

        return False

    return True


def ensure_size_under_limit(size: int, limit: int, update: telegram.Update, context: telegram.ext.CallbackContext, file_reference_text='File') -> bool:
    if size <= limit:
        return True

    chat_type = update.effective_chat.type

    if chat_type == telegram.Chat.PRIVATE:
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


def ensure_valid_converted_file(file_bytes: typing.Optional[bytes], update: telegram.Update, context: telegram.ext.CallbackContext) -> bool:
    if file_bytes is not None:
        return True

    chat_type = update.effective_chat.type

    if chat_type == telegram.Chat.PRIVATE:
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


def send_video(bot: telegram.Bot, chat_id: int, message_id: int, output_bytes: io.BytesIO, caption: typing.Optional[str], chat_type: str) -> None:
    if chat_type == telegram.Chat.PRIVATE:
        button = telegram.InlineKeyboardButton('Rounded', callback_data=json.dumps({}))
        reply_markup = telegram.InlineKeyboardMarkup([[button]])
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


def send_video_note(bot: telegram.Bot, chat_id: int, message_id: int, output_bytes: io.BytesIO) -> None:
    bot.send_video_note(
        chat_id,
        output_bytes,
        reply_to_message_id=message_id
    )


def get_file_size(video_url: str) -> int:
    info = ffmpeg.probe(video_url, show_entries='format=size')
    size = info.get('format', {}).get('size')

    return int(size)


def has_audio_stream(video_url: typing.Optional[str]) -> bool:
    if not video_url:
        return False

    info = ffmpeg.probe(video_url, select_streams='a', show_entries='format=:streams=index')
    streams = info.get('streams', [])

    return len(streams) > 0


def convert(output_type: str, input_video_url: typing.Optional[str] = None, input_audio_url: typing.Optional[str] = None) -> typing.Optional[bytes]:
    try:
        if output_type == constants.OutputType.AUDIO:
            return (
                ffmpeg
                    .input(input_audio_url)
                    .output('pipe:', format='opus', strict='-2')
                    .run(capture_stdout=True)
            )[0]
        elif output_type == constants.OutputType.VIDEO:
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
        elif output_type == constants.OutputType.VIDEO_NOTE:
            # Copied from https://github.com/kkroening/ffmpeg-python/issues/184#issuecomment-504390452.

            ffmpeg_input = (
                ffmpeg
                    .input(input_video_url, t=constants.MAX_VIDEO_NOTE_LENGTH)
            )
            ffmpeg_input_video = (
                ffmpeg_input
                    .video
                    .crop(
                        constants.VIDEO_NOTE_CROP_OFFSET_PARAMS,
                        constants.VIDEO_NOTE_CROP_OFFSET_PARAMS,
                        constants.VIDEO_NOTE_CROP_SIZE_PARAMS,
                        constants.VIDEO_NOTE_CROP_SIZE_PARAMS
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
        elif output_type == constants.OutputType.FILE:
            return (
                ffmpeg
                    .input(input_audio_url)
                    .output('pipe:', format='mp3', strict='-2')
                    .run(capture_stdout=True)
            )[0]
    except ffmpeg.Error as error:
        logger.error('ffmpeg error: {}'.format(error))

    return None


def get_size_string_from_bytes(bytes_count: int, suffix='B') -> str:
    """
    Partially copied from https://stackoverflow.com/a/1094933/865175.
    """

    for unit in ['', 'K', 'M', 'G', 'T', 'P', 'E', 'Z']:
        if abs(bytes_count) < 1000.0:
            return '%3.1f %s%s' % (bytes_count, unit, suffix)

        converted_bytes_count = bytes_count / 1000.0

    return '%.1f %s%s' % (converted_bytes_count, 'Y', suffix)
