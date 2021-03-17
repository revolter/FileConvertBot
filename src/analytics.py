# -*- coding: utf-8 -*-

import enum
import logging
import typing

import requests
import telegram.ext

import constants

logger = logging.getLogger(__name__)


class AnalyticsType(enum.Enum):
    COMMAND = 'command'
    MESSAGE = 'message'


class AnalyticsHandler:
    def __init__(self) -> None:
        self.googleToken: typing.Optional[str] = None
        self.userAgent: typing.Optional[str] = None

    def __google_track(self, analytics_type: AnalyticsType, user: telegram.User, data: str) -> None:
        if not self.googleToken:
            return

        url = constants.GOOGLE_ANALYTICS_BASE_URL.format(self.googleToken, user.id, analytics_type.value, data)

        response = requests.get(url, headers={'User-Agent': self.userAgent or 'TelegramBot'})

        if response.status_code != 200:
            logger.error(f'Google analytics error: {response.status_code}')

    def track(self, context: telegram.ext.CallbackContext, analytics_type: AnalyticsType, user: telegram.User, data='') -> None:
        if data is None:
            data = ''

        context.dispatcher.run_async(self.__google_track, analytics_type, user, data)
