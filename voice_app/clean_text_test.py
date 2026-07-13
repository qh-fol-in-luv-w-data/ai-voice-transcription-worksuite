import re
def clean_xml(text):
    return re.sub(r'[\x00-\x08\x0b-\x0c\x0e-\x1f]', '', text)

print(clean_xml("hello\x08world"))
