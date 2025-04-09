class Format:
    end = '\033[0m'
    # blue_underline = '\033[34;4;1m'
    blue = '\033[34m'
    yellow = '\033[33m'
    green = '\033[32m'
    red = '\033[31m'

def indent_print(text, indent=4):
    print(' ' * indent + text)

def prompt(text, indent=4):
    return input(f"{' ' * indent}{text} (y/n): ").strip().lower()

def header_print(text, indent=0):
    print(Format.blue + ' ' * indent + text + Format.end)
    print()

def warning_confirmation(text, indent=4):
    return input(f"{Format.yellow}{' ' * indent}***** WARNING ***** : {text} (yes/no): {Format.end}").strip().lower()

def success_print(text, indent=4):
    print(Format.green + ' ' * indent + text + Format.end)

def failure_print(text, indent=4):
    print(Format.red + ' ' * indent + text + Format.end)

def response_print(text, indent=6):
    print(' ' * indent + text)
    print()