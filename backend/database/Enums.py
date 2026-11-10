from enum import Enum

class Role(str, Enum):
    ADMIN = "ADMIN"
    OWNER = "OWNER"
    WORKER = "WORKER"

    @classmethod
    def values(cls) -> list[str]:
        return [r.value for r in cls]

    def __str__(self) -> str:
        return self.value