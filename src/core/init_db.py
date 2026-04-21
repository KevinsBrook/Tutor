from src.core.database import Base, engine
from src.core import models  # noqa: F401


def init_db() -> None:
    Base.metadata.create_all(bind=engine)