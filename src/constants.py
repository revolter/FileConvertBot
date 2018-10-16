# -*- coding: utf-8 -*-

GOOGLE_HEADERS = {'User-Agent': 'FileConvertBot'}

#: See also: https://developers.google.com/analytics/devguides/collection/protocol/v1/parameters
GOOGLE_ANALYTICS_BASE_URL = 'https://www.google-analytics.com/collect?v=1&t=event&tid={}&cid={}&ec={}&ea={}'

LOGS_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
