import pytest
import pytest_asyncio
from bot.database.session import Database
from bot.database.repositories import Repository


@pytest_asyncio.fixture
async def repo(tmp_path):
    db = Database(str(tmp_path / "persistent.sqlite3"))
    await db.connect()
    repository = Repository(db)
    yield repository
    await db.close()
