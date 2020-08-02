def migrate(migrator, database, fake=False, **kwargs):
    if fake is True:
        return

    migrator.drop_not_null('user', 'telegram_username')
