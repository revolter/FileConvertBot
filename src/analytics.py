# -*- coding: utf-8 -*-

from enum import Enum

import logging

from telegram.ext.dispatcher import run_async

import requests

from constants import GOOGLE_HEADERS, GOOGLE_ANALYTICS_BASE_URL

logger = logging.getLogger(__name__)


class AnalyticsType(Enum):
    COMMAND = 'command'
    MESSAGE = 'message'


class Analytics:
    def __init__(self):
        self.googleToken = None

    def __google_track(self, analytics_type, user, data):
        if not self.googleToken:
            return

        url = GOOGLE_ANALYTICS_BASE_URL.format(self.googleToken, user.id, analytics_type.value, data)

        response = requests.get(url, headers=GOOGLE_HEADERS)

        if response.status_code != 200:
            logger.error('Google analytics error: {}'.format(response.status_code))

    @run_async
    def track(self, analytics_type, user, data=''):
        self.__google_track(analytics_type, user, data)
