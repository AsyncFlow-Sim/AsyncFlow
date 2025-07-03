"""helper functions for the auth process"""

import string
from typing import cast

from passlib.context import CryptContext

MAX_PASSWORD_LENGTH = 128 # prevent DoS
MIN_PASSWORD_LENGTH = 8
SPECIAL_CHARS = set(string.punctuation)

pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",

)

def is_password_safe(password: str) -> bool:
    """Function to verify if a password is safe"""
    has_upper = False
    has_lower = False
    has_digit = False
    has_special = False

    if len(password) < MIN_PASSWORD_LENGTH  or len(password) > MAX_PASSWORD_LENGTH:
        return False

    for char in password:
        if char.isupper():
            has_upper = True
        elif char.islower():
            has_lower = True
        elif char.isdigit():
            has_digit = True
        elif char in SPECIAL_CHARS:
            has_special = True

        if has_upper and has_lower and has_digit and has_special:
            return True

    return False


def verify_passwords_equality(password: str, confirmed_password: str) -> bool:
    """Verify if the passwords given in the registration form are equivalent."""
    return password == confirmed_password


def hash_password(password: str) -> str:
    """
    Receive the password
    give back the hashed password
    """
    return cast("str", pwd_context.hash(password))


def verify_hashed_pwd_plain_pwd_equality(plain_pwd: str, hashed_pwd: str) -> bool:
    """
    Verify during the login if the plain password
    correspond to the hashed password
    """
    return cast("bool", pwd_context.verify(plain_pwd, hashed_pwd))
