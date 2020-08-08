import typing

import peewee
import peewee_migrate


def migrate(migrator: peewee_migrate.Migrator, _database: peewee.Database, fake=False, **_kwargs: typing.Any) -> None:
    if fake is True:
        return

    migrator.drop_not_null('user', 'telegram_username')
