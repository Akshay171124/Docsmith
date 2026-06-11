"""Example application module."""


def create_user(name: str, email: str) -> dict:
    """Create a user record.

    Args:
        name: The user's display name.
        email: The user's email address.
    Returns:
        A dict with the new user's fields.
    """
    return {"name": name, "email": email}


class UserService:
    """Manages user lifecycle."""

    def deactivate(self, user_id: int) -> bool:
        """Deactivate a user by id."""
        return True
