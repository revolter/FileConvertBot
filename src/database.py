# -*- coding: utf-8 -*-

from __future__ import annotations

import datetime
import logging
import typing
import uuid

import peewee
import peewee_migrate
import playhouse.sqlite_ext
import telegram

import constants
import telegram_utils

logger = logging.getLogger(__name__)

database = peewee.SqliteDatabase('file_convert.sqlite')

database.connect()

router = peewee_migrate.Router(database, migrate_table='migration', logger=logger)


def get_current_datetime() -> str:
    return datetime.datetime.now().strftime(constants.GENERIC_DATE_TIME_FORMAT)


class BaseModel(peewee.Model):
    rowid = playhouse.sqlite_ext.RowIDField()

    created_at = peewee.DateTimeField(default=get_current_datetime)
    updated_at = peewee.DateTimeField()

    class Meta:
        database = database


class User(BaseModel):
    id = peewee.TextField(unique=True, default=uuid.uuid4)
    telegram_id = peewee.BigIntegerField(unique=True)
    telegram_username = peewee.TextField(null=True)

    def get_markdown_description(self) -> str:
        if self.telegram_username is None:
            username = telegram_utils.escape_v2_markdown_text('-')
        else:
            escaped_username = telegram_utils.escape_v2_markdown_text(
                text=f'@{self.telegram_username}',
                entity_type=telegram.MessageEntity.CODE
            )
            username = f'`{escaped_username}`'

        user_id = telegram_utils.escape_v2_markdown_text_link(
            text=str(self.telegram_id),
            url=f'tg://user?id={self.telegram_id}'
        )

        return (
            f'{self.rowid}{telegram_utils.ESCAPED_FULL_STOP} {telegram_utils.ESCAPED_VERTICAL_LINE} '
            f'{user_id} {telegram_utils.ESCAPED_VERTICAL_LINE} '
            f'{username}'
        )

    def get_created_at(self) -> str:
        date = typing.cast(datetime.datetime, self.created_at)

        return date.strftime(constants.GENERIC_DATE_TIME_FORMAT)

    def get_updated_ago(self) -> str:
        if self.updated_at == self.created_at:
            return '-'

        delta_seconds = round((datetime.datetime.now() - self.updated_at).total_seconds())
        time_ago = str(datetime.datetime.fromtimestamp(delta_seconds) - constants.EPOCH_DATE)

        return f'{time_ago} ago'

    @classmethod
    def create_or_update_user(cls, id: int, username: str) -> typing.Optional[User]:
        current_date_time = get_current_datetime()

        try:
            defaults = {
                'telegram_username': username,

                'updated_at': current_date_time
            }

            (db_user, is_created) = cls.get_or_create(telegram_id=id, defaults=defaults)

            db_user.telegram_username = username
            db_user.updated_at = current_date_time

            db_user.save()

            if is_created:
                return db_user
        except peewee.PeeweeException as error:
            logger.error(f'Database error: "{error}" for id: {id} and username: {username}')

        return None

    @classmethod
    def get_users_table(cls, sorted_by_updated_at=False) -> str:
        users_table = ''

        try:
            sort_field = cls.updated_at if sorted_by_updated_at else cls.created_at

            query = cls.select()

            if sorted_by_updated_at:
                query = query.where(cls.created_at != cls.updated_at)

            query = query.order_by(sort_field.desc()).limit(10)

            for user in reversed(query):
                users_table += (
                    f'\n{user.get_markdown_description()} {telegram_utils.ESCAPED_VERTICAL_LINE} '
                    f'{telegram_utils.escape_v2_markdown_text(user.get_created_at())} {telegram_utils.ESCAPED_VERTICAL_LINE} '
                    f'{telegram_utils.escape_v2_markdown_text(user.get_updated_ago())}'
                )
        except peewee.PeeweeException:
            pass

        if not users_table:
            users_table = 'No users'

        return users_table


migrator = router.migrator

migrator.create_table(User)

router.run()
