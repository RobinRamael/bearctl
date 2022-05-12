
def snake2camel(s):
    return "".join(word.title() for word in s.split("_"))

