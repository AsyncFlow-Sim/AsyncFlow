"""Application constants and configuration values."""

from enum import Enum


class UserLevel(str, Enum):
    """constants to define the different levels the user can have in the application"""

    USER = "user"
    ADMIN = "admin"

class SubscriptionLevel(str, Enum):
    """
    constants to define the different subscription levels the user can have
    in the application
    """

    FREE = "free"
    EXPERT = "expert"
    PRO = "pro"
    ENTERPRISE = "enterprise"


