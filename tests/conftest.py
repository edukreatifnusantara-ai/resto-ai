import os
import tempfile
from pathlib import Path

import pytest

# Keep every test deterministic and independent from any developer database.
_TEST_DIR = Path(tempfile.mkdtemp(prefix="resto-ai-tests-"))
os.environ["RESTO_DATABASE_URL"] = f"sqlite:///{_TEST_DIR / 'test.db'}"
os.environ["RESTO_API_TOKEN"] = "test-token"

from app.database import Base, SessionLocal, engine, seed_db  # noqa: E402

Base.metadata.create_all(bind=engine)
seed_db()


@pytest.fixture(autouse=True)
def reset_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed_db()
    yield
    db = SessionLocal()
    db.rollback()
    db.close()
