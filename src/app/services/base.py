from typing import Generic, TypeVar
from src.app.repositories.base import BaseRepository

RepoType = TypeVar("RepoType", bound=BaseRepository)


class BaseService(Generic[RepoType]):
    """
    Base service layer pattern coordinate data operations through repositories.
    """
    def __init__(self, repository: RepoType):
        self.repository = repository
