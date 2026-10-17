import pytest

from backend.config import Settings, origin
from backend.security import password_hash, password_matches


def test_passwords_are_salted_scrypt_digests():
    one, two = password_hash("a secure password"), password_hash("a secure password")
    assert one != two and "a secure password" not in one
    assert password_matches("a secure password", one)
    assert not password_matches("wrong", one)
    assert not password_matches("x", "corrupt")


@pytest.mark.parametrize(
    "url",
    [
        "https://good.test/evil",
        "https://x:y@good.test",
        "https://good.test#x",
        "https://good.test?x=y",
        "http://remote.test",
    ],
)
def test_origins_reject_unsafe_configuration(url):
    with pytest.raises(ValueError):
        origin(url, True)


def test_configuration_requires_strong_key_and_database():
    with pytest.raises(ValueError):
        Settings("", "https://good.test", b"x" * 32)
    with pytest.raises(ValueError):
        Settings("postgresql://placeholder", "https://good.test", b"short")
