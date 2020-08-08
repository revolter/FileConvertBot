import typing

import peewee
import peewee_migrate

GENERIC_DATE_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'


def migrate(migrator: peewee_migrate.Migrator, database: peewee.Database, fake=False, **kwargs: typing.Any) -> None:
    if fake is True:
        return

    user_class = migrator.orm['user']

    for user in user_class.select():
        user.created_at = user.created_at.strftime(GENERIC_DATE_TIME_FORMAT)
        user.updated_at = user.updated_at.strftime(GENERIC_DATE_TIME_FORMAT)

        user.save()
