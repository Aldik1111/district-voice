"""Conservative offline masking; these rules do not guarantee full anonymisation."""
import re
from dataclasses import dataclass

EMAIL = re.compile(r"(?<![\w.+-])[\w.!#$%&'*+/=?^`{|}~-]+@[\w-]+(?:\.[\w-]+)+", re.I)
IIN = re.compile(r"(?<!\d)\d{12}(?!\d)")
LABELED_IIN = re.compile(r"(?i)\b(?:иин|жсн)\s*[:№-]?\s*(?:\d[ \t-]*){11}\d(?!\d)")
LABELED_PHONE = re.compile(r"(?i)\b(?:тел(?:ефон)?\.?|моб\.?|байланыс нөмірі)\s*[:—-]?\s*\+?\d(?:[ \t().-]*\d){6,14}(?!\d)")
PHONE = re.compile(r"(?<!\w)(?:\+?7|8)[\s(.-]*\d{3}[\s).\-]*\d{3}[\s.\-]*\d{2}[\s.\-]*\d{2}(?!\d)")
GENERIC_PHONE = re.compile(r"(?<!\w)\+\d(?:[\s().-]*\d){8,14}(?!\d)")
LABELED_NAME = re.compile(
    r"(?i)(?:Ф\.?\s?И\.?\s?О\.?|меня зовут|аты[- ]жөні|менің атым)\s*[:—-]?\s*"
    r"[А-ЯЁӘҒҚҢӨҰҮҺІA-Z][а-яёәғқңөұүһіa-z-]+(?:\s+[А-ЯЁӘҒҚҢӨҰҮҺІA-Z][а-яёәғқңөұүһіa-z-]+){0,2}"
)
FULL_NAME = re.compile(
    r"\b[А-ЯЁӘҒҚҢӨҰҮҺІ][а-яёәғқңөұүһі-]+\s+[А-ЯЁӘҒҚҢӨҰҮҺІ][а-яёәғқңөұүһі-]+"
    r"\s+[А-ЯЁӘҒҚҢӨҰҮҺІ][а-яёәғқңөұүһі-]*(?:вич|вна|ұлы|қызы)\b"
)
PERSONAL_DOCUMENT = re.compile(r"(?i)\b(?:паспорт|удостоверение(?: личности)?|жеке куәлік|карт[аы]|сч[её]т|iban)\s*(?:№|номер|:)?\s*[A-ZА-Я0-9][A-ZА-Я0-9 -]{5,30}")
APARTMENT = re.compile(r"(?i)\b(?:кв\.?|квартира|пәтер)\s*[:№-]?\s*\d+[А-Яа-яA-Za-z]?")
SUSPECT_LABEL = re.compile(r"(?i)\b(?:паспорт|удостоверение|жеке куәлік|дата рождения|туған күні|мой номер|телефон|иин|жсн)\b")


@dataclass
class Masked:
    text: str
    status: str
    warnings: list[str]


def mask(value: str) -> Masked:
    warnings = []
    status = "clear"
    for pattern, replacement in ((EMAIL, "[EMAIL]"), (LABELED_IIN, "[ИИН]"), (IIN, "[ИИН]"), (LABELED_PHONE, "[ТЕЛЕФОН]"), (PHONE, "[ТЕЛЕФОН]"), (GENERIC_PHONE, "[ТЕЛЕФОН]")):
        value, count = pattern.subn(replacement, value)
        if count:
            status = "masked"
    for pattern, replacement in ((LABELED_NAME, "[ИМЯ СКРЫТО]"), (FULL_NAME, "[ИМЯ СКРЫТО]"), (PERSONAL_DOCUMENT, "[ДОКУМЕНТ СКРЫТ]"), (APARTMENT, "[КВАРТИРА СКРЫТА]")):
        value, count = pattern.subn(replacement, value)
        if count:
            status = "review_required"
            warnings.append("Вероятные персональные сведения скрыты; требуется ручная проверка.")
    checked = re.sub(r"(?i)(?:телефон|иин|жсн|мой номер)\s*[:№-]?\s*\[[^\]]+\]", "", value)
    if SUSPECT_LABEL.search(re.sub(r"\[[^\]]+\]", "", checked)):
        status = "review_required"
        warnings.append("В тексте есть признаки персональных сведений; проверьте обезличивание.")
    if status == "masked":
        warnings.append("Телефоны, email или ИИН скрыты автоматически. Полнота обезличивания не гарантируется.")
    return Masked(value, status, list(dict.fromkeys(warnings)))


def detect_language(text: str) -> str:
    if re.search(r"[әғқңөұүһі]", text, re.I):
        return "kk"
    if re.search(r"[а-яё]", text, re.I):
        return "ru"
    return "unknown"
