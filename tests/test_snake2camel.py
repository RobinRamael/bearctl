from bear.utils import snake2camel


def test_snake2camel():
    result = snake2camel("homti_tom")
    assert result == "HomtiTom"


def test_snake2camel_no_capitalize_first():
    result = snake2camel("homti_tom", capitalize_first=False)
    assert result == "homtiTom"
