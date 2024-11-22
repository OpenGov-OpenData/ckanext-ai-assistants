import pytest


@pytest.fixture
def clean_db(reset_db, migrate_db_for):
    reset_db()
    try:
        migrate_db_for("harvest")
    except:
        pass
