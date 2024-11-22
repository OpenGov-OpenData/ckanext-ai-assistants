import pytest
import logging


@pytest.fixture
def clean_db(reset_db, migrate_db_for):
    reset_db()
    try:
        migrate_db_for('harvest')
    except Exception:
        logging.info('Migration failed, but that is fine for this plugin. Ignore it.')
