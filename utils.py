import re

def escape_markdown(text: str) -> str:
    return re.sub(r'([_*[\]()~`>#+=|{}.!-])', r'\\\1', str(text))