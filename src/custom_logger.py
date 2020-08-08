import logging

import constants


class LoggerFilter(logging.Filter):
    def __init__(self, level: int, name='') -> None:
        super().__init__(name=name)
        
        self.level = level

    def filter(self, log_record: logging.LogRecord) -> bool:
        return log_record.levelno <= self.level


def configure_root_logger() -> None:
    logger = logging.getLogger()

    logging.basicConfig(format=constants.LOGS_FORMAT, level=logging.INFO)

    error_logging_handler = logging.FileHandler('errors.log')
    error_logging_handler.setFormatter(logging.Formatter(constants.LOGS_FORMAT))
    error_logging_handler.setLevel(logging.ERROR)
    error_logging_handler.addFilter(LoggerFilter(logging.ERROR))

    logger.addHandler(error_logging_handler)

    warning_logging_handler = logging.FileHandler('warnings.log')
    warning_logging_handler.setFormatter(logging.Formatter(constants.LOGS_FORMAT))
    warning_logging_handler.setLevel(logging.WARNING)
    warning_logging_handler.addFilter(LoggerFilter(logging.WARNING))

    logger.addHandler(warning_logging_handler)
