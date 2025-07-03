"""Database base classes and utilities."""

import re

from sqlalchemy.orm import DeclarativeBase, declared_attr


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Generate table name from class name by converting CamelCase to snake_case."""
        return re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
