import typing

import peewee
import peewee_migrate


def migrate(migrator: peewee_migrate.Migrator, database: peewee.Database, fake=False, **kwargs: typing.Any) -> None:
    if fake is True:
        return

    migrator.drop_not_null('user', 'telegram_username')
