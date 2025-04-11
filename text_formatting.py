"""
Text formatting functions for terminal output

Functions:
    header_print(text, indent) -> None
    subheader_print(text, indent) -> None
    indent_print(text, indent) -> None
    success_print(text, indent) -> None
    failure_print(text, indent) -> None
    response_print(text, indent) -> None
    prompt(text, indent) -> str
    warning_confirmation(text, indent) -> str
"""


class Format:
    """Color codes to use for text formatting."""
    end = '\033[0m'
    blue = '\033[34m'
    cyan = '\033[36;1m'
    yellow = '\033[33m'
    green = '\033[32m'
    red = '\033[31m'

def header_print(text: str, indent: int = 0) -> None:
    """
    Format text as a header and print it

    Text is colored blue and printed with no indent by default.

    Args:
        text (str): Text to be formatted and printed
        indent (int, optional): Number of spaces to indent the text. Defaults to 0.
    """
    print(Format.blue + ' ' * indent + text + Format.end)
    print()

def subheader_print(text: str, indent: int=4) -> None:
    """
    Format text as a subheader and print it

    Text is colored cyan and printed with an indent of 4 spaces by default.

    Args:
        text (str): Text to be formatted and printed
        indent (int, optional): Number of spaces to indent the text. Defaults to 4.
    """
    print(Format.cyan + ' ' * indent + text + Format.end)
    print()

def indent_print(text: str, indent: int=4) -> None:
    """
    Indent text and print it

    Text is printed with an indent of 4 spaces by default.

    Args:
        text (str): Text to be indented and printed
        indent (int, optional): Number of spaces to indent the text. Defaults to 4.
    """
    print(' ' * indent + text)

def success_print(text: str, indent: int=4) -> None:
    """
    Format text as a success message and print it

    Text is colored green and printed with an indent of 4 spaces by default.

    Args:
        text (str): Text to be formatted and printed
        indent (int, optional): Number of spaces to indent the text. Defaults to 4.
    """
    print(Format.green + ' ' * indent + text + Format.end)

def failure_print(text: str, indent: int=4) -> None:
    """
    Format text as a failure message and print it

    Text is colored red and printed with an indent of 4 spaces by default.

    Args:
        text (str): Text to be formatted and printed
        indent (int, optional): Number of spaces to indent the text. Defaults to 4.
    """
    print(Format.red + ' ' * indent + text + Format.end)

def response_print(text: str, indent: int=6) -> None:
    """
    Print multi-line text with each line indented

    Defaults to indenting each line 6 spaces. Used for printing responses with
    json.dumps while retaining original formatting, but indenting each line the same.

    Args:
        text (str): Multi-line text to be printed
        indent (int, optional): Number of spaces to indent each line. Defaults to 6.
    """
    indent_str = ' ' * indent
    for line in text.splitlines():
        print(indent_str + line)
    print()

def prompt(text: str, indent: int=4) -> str:
    """
    Format text as a prompt and return the user's response

    Accepts text and displays as a prompt, adding (y/n) at the end, then
    returns the user's response as a string. Defaults to an indent of 4 spaces.

    Args:
        text (str): Text to display as a prompt
        indent (int, optional): Number of spaced to indent the prompt text. Defaults to 4.

    Returns:
        str: Input from the user, stripped and lowercased.
    """
    return input(f"{' ' * indent}{text} (y/n): ").strip().lower()

def warning_confirmation(text: str, indent: int=4) -> str:
    """
    Format text as a warning and prompt for confirmation

    Accepts text and displays as a warning, adding (yes/no) at the end, as
    well as WARNING capitalized formatted in yellow. The user's input is returned
    as a string. Defaults to an indent of 4 spaces.

    Args:
        text (str): Text to display as a warning and prompt
        indent (int, optional): Number of spaces to indent the warning prompt. Defaults to 4.

    Returns:
        str: Input from the user, stripped and lowercased.
    """
    return input(f"{Format.yellow}{' ' * indent}***** WARNING ***** : {text} (yes/no): {Format.end}").strip().lower()
