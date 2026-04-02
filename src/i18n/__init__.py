from .vi import VI
from .en import EN

STRINGS = {"vi": VI, "en": EN}


def t(key: str, lang: str = "vi", **kwargs) -> str:
    strings = STRINGS.get(lang, VI)
    text = strings.get(key, VI.get(key, key))
    if kwargs:
        try:
            return text.format(**kwargs)
        except (KeyError, IndexError):
            return text
    return text
