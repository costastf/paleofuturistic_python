"""{{ cookiecutter.project_slug }} module."""


def hello(someone: str = 'you') -> str:
    """Greet someone.

    Args:
        someone: The name of the person to greet.

    Returns:
        A greeting message.
    """
    return f'Hello {someone} from {{ cookiecutter.project_slug }}!'
