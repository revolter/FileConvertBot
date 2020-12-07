# -*- coding: utf-8 -*-

import datetime

# See also: https://developers.google.com/analytics/devguides/collection/protocol/v1/parameters
GOOGLE_ANALYTICS_BASE_URL = 'https://www.google-analytics.com/collect?v=1&t=event&tid={}&cid={}&ec={}&ea={}'

LOGS_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

GENERIC_DATE_FORMAT = '%Y-%m-%d'
GENERIC_DATE_TIME_FORMAT = f'{GENERIC_DATE_FORMAT} %H:%M:%S'

EPOCH_DATE = datetime.datetime(1970, 1, 1)

MAX_PHOTO_FILESIZE_UPLOAD = int(10E6)  # (50 MB)
MAX_VIDEO_NOTE_LENGTH = 60

AUDIO_CODEC_NAMES = ['aac', 'mp3']

VIDEO_CODEC_NAMES = ['h264', 'hevc', 'mpeg4', 'vp6', 'vp8']
VIDEO_NOTE_CROP_OFFSET_PARAMS = 'abs(in_w-in_h)/2'
VIDEO_NOTE_CROP_SIZE_PARAMS = 'min(in_w,in_h)'


class OutputType:
    NONE = 'none'
    AUDIO = 'audio'
    VIDEO = 'video'
    VIDEO_NOTE = 'video_note'
    PHOTO = 'photo'
    STICKER = 'sticker'
    FILE = 'file'
