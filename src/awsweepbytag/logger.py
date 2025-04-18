import logging

from awsweepbytag.text_formatting import Format


class ColorFormatter(logging.Formatter):
    """Logging Formatter to add colors based on log level."""

    def format(self, record):
        level_color = {
            logging.DEBUG: Format.cyan,
            logging.INFO: Format.blue,
            logging.WARNING: Format.yellow,
            logging.ERROR: Format.red,
            logging.CRITICAL: Format.red,
        }.get(record.levelno, Format.end)

        record.levelname = f"{level_color}{record.levelname}{Format.end}"

        return super().format(record)


def get_colored_stream_handler(level=logging.DEBUG) -> logging.Handler:
    handler = logging.StreamHandler()
    formatter = ColorFormatter("[%(levelname)s] %(message)s")
    handler.setFormatter(formatter)
    handler.setLevel(level)
    return handler