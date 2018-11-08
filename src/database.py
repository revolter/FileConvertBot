# -*- coding: utf-8 -*-

from datetime import datetime
from uuid import uuid4

import logging

from peewee import (
    Model,
    DateTimeField, TextField, BigIntegerField,
    PeeweeException
)
from playhouse.sqlite_ext import SqliteExtDatabase

logger = logging.getLogger(__name__)

database = SqliteExtDatabase('file_convert.sqlite')


class BaseModel(Model):
    created_at = DateTimeField(default=datetime.now)
    updated_at = DateTimeField()

    class Meta:
        database = database


class User(BaseModel):
    id = TextField(primary_key=True, unique=True, default=uuid4)
    telegram_id = BigIntegerField(unique=True)
    telegram_username = TextField()

    def get_description(self):
        return '{0.telegram_id} | {0.telegram_username}'.format(self)

    @classmethod
    def create_user(cls, id, username):
        current_date_time = datetime.now()

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
        except PeeweeException as error:
            logger.error('Database error: {}'.format(error))

        return None

    @classmethod
    def get_users_table(cls):
        users_table = ''

        try:
            for user in cls.select():
                users_table = '{}\n{} | {}'.format(users_table, user.get_description(), user.created_at)
        except PeeweeException:
            pass

        if not users_table:
            users_table = 'No users'

        return users_table

database.connect()

User.create_table(True)
