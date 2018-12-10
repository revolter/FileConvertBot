# -*- coding: utf-8 -*-

from datetime import datetime

GOOGLE_HEADERS = {'User-Agent': 'FileConvertBot'}

#: See also: https://developers.google.com/analytics/devguides/collection/protocol/v1/parameters
GOOGLE_ANALYTICS_BASE_URL = 'https://www.google-analytics.com/collect?v=1&t=event&tid={}&cid={}&ec={}&ea={}'

LOGS_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

GENERIC_DATE_FORMAT = '%Y-%m-%d'
GENERIC_DATE_TIME_FORMAT = '{} %H:%M:%S'.format(GENERIC_DATE_FORMAT)

EPOCH_DATE = datetime(1970, 1, 1)


class LoggerFilter(object):
    def __init__(self, level):
        self.__level = level

    def filter(self, log_record):
        return log_record.levelno <= self.__level
