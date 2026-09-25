"""Password hashing and the password policy.

Hashes are Argon2id with ``argon2-cffi``'s defaults (RFC 9106's low-memory profile: three
passes over 64 MiB, four lanes), each with its own random salt; the encoded hash records its
parameters, so they can be raised later and old hashes upgraded at the next sign-in
(``needs_rehash``). The policy follows NIST SP 800-63B: a minimum length, no composition
rules, and a refusal of the most commonly used passwords and of one's own e-mail or name.
"""

from __future__ import annotations

from functools import lru_cache

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_LENGTH = 12
MAX_LENGTH = 128

_hasher = PasswordHasher()

# Frequently used passwords of twelve characters or more (and the product's own name), so a
# long but predictable choice is still refused. Compared case-insensitively.
COMMON = frozenset(
    {
        "123456789012",
        "1234567890123",
        "12345678901234",
        "123456789abc",
        "1q2w3e4r5t6y",
        "abc123456789",
        "abcdefghijkl",
        "aaaaaaaaaaaa",
        "administrator",
        "changeme1234",
        "iloveyou1234",
        "letmein12345",
        "password1234",
        "password12345",
        "password123!",
        "passwordpassword",
        "qwerty123456",
        "qwertyuiop12",
        "qwertyuiopasdf",
        "welcome12345",
        "rumin1234567",
        "ruminrumin12",
        "rumin-password",
        "trustno1trustno1",
        "zaq12wsxcde3",
    }
)


# Words people wrap in digits and symbols to meet a length ("Password1234!", "Welcome@2026").
# A password whose letters are only one of these, or only the person's name or e-mail, is
# refused however many digits and symbols surround it.
COMMON_WORDS = frozenset(
    {
        "abc",
        "abcdef",
        "admin",
        "administrator",
        "baseball",
        "changeme",
        "dragon",
        "football",
        "iloveyou",
        "letmein",
        "login",
        "master",
        "monkey",
        "passw",
        "password",
        "princess",
        "qwerty",
        "qwertyuiop",
        "rumin",
        "secret",
        "sunshine",
        "trustno",
        "welcome",
    }
)


# Digits and symbols written for letters inside a word ("p@ssw0rd").
_LOOKALIKES = str.maketrans({"@": "a", "4": "a", "$": "s", "5": "s", "0": "o", "1": "i", "3": "e"})


def _letters(text: str) -> str:
    return "".join(character for character in text.lower() if character.isalpha())


def _core_letters(password: str) -> str:
    """The letters of the part between the first and the last letter, look-alikes read as
    letters: "p@ssw0rd-2026!" gives "password"."""
    lowered = password.lower()
    positions = [index for index, character in enumerate(lowered) if character.isalpha()]
    if not positions:
        return ""
    core = lowered[positions[0] : positions[-1] + 1].translate(_LOOKALIKES)
    return _letters(core)


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    """Whether ``password`` matches ``stored_hash``; a malformed hash never matches."""
    try:
        return _hasher.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    try:
        return _hasher.check_needs_rehash(stored_hash)
    except InvalidHashError:
        return True


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return _hasher.hash("rumin: no such account")


def burn_verification(password: str) -> None:
    """Spend the time a real check would, for an e-mail that has no account, so response
    times do not reveal which addresses are registered."""
    verify_password(_dummy_hash(), password)


def password_problems(password: str, *, email: str = "", name: str = "") -> list[str]:
    """Why ``password`` is not acceptable (empty when it is)."""
    problems: list[str] = []
    if len(password) < MIN_LENGTH:
        problems.append(f"Use at least {MIN_LENGTH} characters.")
    if len(password) > MAX_LENGTH:
        problems.append(f"Use at most {MAX_LENGTH} characters.")
    if password.strip() != password or not password.strip():
        problems.append("Do not start or end the password with spaces.")
    lowered = password.lower()
    if lowered in COMMON:
        problems.append("This password is too common; choose another.")
    if email and lowered in {email.lower(), email.lower().split("@")[0]}:
        problems.append("Do not use your e-mail address as the password.")
    if name and lowered == name.lower().replace(" ", ""):
        problems.append("Do not use your name as the password.")
    if len(set(password)) < 4:
        problems.append("Use more than three different characters.")
    letters = _core_letters(password)
    own = {_letters(name), _letters(email.split("@")[0])} - {""}
    if lowered not in COMMON and letters and (letters in COMMON_WORDS or letters in own):
        problems.append(
            "Digits and symbols around a common word or your own name are easy to guess; "
            "choose another."
        )
    return problems
