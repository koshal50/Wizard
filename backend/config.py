import os
from dataclasses import dataclass
from urllib.parse import urlsplit


def origin(value: str, local: bool = False) -> str:
    parsed = urlsplit(value)
    if (
        (
            parsed.scheme != "https"
            and not (
                local
                and parsed.scheme == "http"
                and parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            )
        )
        or not parsed.netloc
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(
            "Use an HTTPS origin (loopback HTTP requires explicit local development)"
        )
    if parsed.path not in {"", "/"}:
        raise ValueError("An origin cannot contain a path")
    return value.rstrip("/")


@dataclass(frozen=True)
class Settings:
    database_url: str
    public_origin: str
    secret: bytes
    local: bool = False

    def __post_init__(self):
        origin(self.public_origin, self.local)
        if len(self.secret) < 32:
            raise ValueError("WIZARD_ACCOUNT_SECRET must contain at least 32 bytes")
        if not self.database_url:
            raise ValueError("WIZARD_ACCOUNT_DATABASE_URL is required")

    @classmethod
    def environment(cls):
        return cls(
            os.environ.get("WIZARD_ACCOUNT_DATABASE_URL", ""),
            os.environ.get("WIZARD_ACCOUNT_PUBLIC_ORIGIN", ""),
            os.environ.get("WIZARD_ACCOUNT_SECRET", "").encode(),
            os.environ.get("WIZARD_ACCOUNT_LOCAL_DEV") == "1",
        )
