from functools import lru_cache

from square import Square
from square.environment import SquareEnvironment

from esl.config import settings


@lru_cache(maxsize=1)
def get_client() -> Square:
    env = (
        SquareEnvironment.SANDBOX
        if settings.square_environment.upper() == "SANDBOX"
        else SquareEnvironment.PRODUCTION
    )
    return Square(
        token=settings.square_token,
        environment=env,
        version=settings.square_api_version,
    )
