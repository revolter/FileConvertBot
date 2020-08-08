# -*- coding: utf-8 -*-

import typing

import telegram.utils.helpers


def escape_v2_markdown_text(text: str, entity_type: typing.Optional[str] = None) -> str:
    return telegram.utils.helpers.escape_markdown(
        text=text,
        version=2,
        entity_type=entity_type
    )


def escape_v2_markdown_text_link(text: str, url: str) -> str:
    escaped_text = escape_v2_markdown_text(text)
    escaped_url = escape_v2_markdown_text(
        text=url,
        entity_type=telegram.MessageEntity.TEXT_LINK
    )

    return '[{}]({})'.format(escaped_text, escaped_url)


ESCAPED_FULL_STOP = escape_v2_markdown_text('.')
ESCAPED_VERTICAL_LINE = escape_v2_markdown_text('|')
