import os
import sys


def snake2camel(s):
    return "".join(word.title() for word in s.split("_"))


class HiddenPrints:
    def __init__(self):
        self._original_stdout = None

    def __enter__(self):
        self._original_stdout = sys.stdout
        sys.stdout = open(os.devnull, "w")

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.close()
        sys.stdout = self._original_stdout
