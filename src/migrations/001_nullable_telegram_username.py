def migrate(migrator, database, fake=False, **kwargs):
    migrator.drop_not_null('user', 'telegram_username')
