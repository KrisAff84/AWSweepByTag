class Format:
    end = '\033[0m'
    # blue_underline = '\033[34;4;1m'
    blue = '\033[34m'
    yellow = '\033[33m'
    green = '\033[32m'
    red = '\033[31m'

def header_print(text, indent=0):
    print(Format.blue + ' ' * indent + text + Format.end)
    print()

def indent_print(text, indent=4):
    print(' ' * indent + text)

def success_print(text, indent=4):
    print(Format.green + ' ' * indent + text + Format.end)

def failure_print(text, indent=4):
    print(Format.red + ' ' * indent + text + Format.end)

def response_print(text, indent=6):
    indent_str = ' ' * indent
    for line in text.splitlines():
        print(indent_str + line)
    print()

def prompt(text, indent=4):
    return input(f"{' ' * indent}{text} (y/n): ").strip().lower()

def warning_confirmation(text, indent=4):
    return input(f"{Format.yellow}{' ' * indent}***** WARNING ***** : {text} (yes/no): {Format.end}").strip().lower()

#########################################
# Textwrap Version
#########################################

# import textwrap
# import shutil

# def format_wrapped(text, indent=4, width=None):
#     if width is None:
#         try:
#             width = shutil.get_terminal_size().columns - 1
#         except OSError:
#             width = 80  # fallback if terminal size can't be detected

#     wrapper = textwrap.TextWrapper(
#         initial_indent=' ' * indent,
#         subsequent_indent=' ' * indent,
#         width=width
#     )
#     return wrapper.fill(text)

# def header_print(text, indent=0):
#     print(Format.blue + ' ' * indent + text + Format.end)
#     print()

# def indent_print(text, indent=4):
#     print(format_wrapped(text, indent=indent))

# def success_print(text, indent=4):
#     print(Format.green + format_wrapped(text, indent=indent) + Format.end)

# def failure_print(text, indent=4):
#     print(Format.red + format_wrapped(text, indent=indent) + Format.end)

# def response_print(text, indent=6):
#     indent_str = ' ' * indent
#     for line in text.splitlines():
#         print(indent_str + line)
#     print()

# def prompt(text, indent=4):
#     formatted = format_wrapped(f"{text} (y/n):", indent=indent)
#     return input(formatted + ' ').strip().lower()

# def warning_confirmation(text, indent=4):
#     warning_prefix = "***** WARNING ***** : "
#     formatted = format_wrapped(f"{warning_prefix}{text} (yes/no):", indent=indent)
#     return input(Format.yellow + formatted + Format.end + ' ').strip().lower()
