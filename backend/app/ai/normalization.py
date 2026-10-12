"""Small, explicit Russian/Kazakh dictionaries, not a claim of full linguistic coverage."""
import re
import unicodedata

CATEGORIES = ['Водоснабжение','Электроснабжение','Дороги','Отопление','Освещение','Общественный транспорт','Вывоз мусора','Благоустройство','Экология','Другое']
CATEGORY_RULES = {
    'Водоснабжение': [r'\bвод(?:а|ы|у|е|ой)\b',r'\bводоснаб\w*',r'\bводопровод\w*',r'\bнапор\w*',r'\bсу\b',r'\bсумен\b',r'\bқұбыр\w*',r'\bсусыз\b'],
    'Электроснабжение': [r'\bэлектр\w*',r'\bэлектроэнерг\w*',r'\bсвет[а]?\b',r'\bток\b',r'\bкернеу\w*',r'\bжарық\s+жоқ'],
    'Дороги': [r'\bдорог\w*',r'\bасфальт\w*',r'\bям[аыуе]\b',r'\bвыбоин\w*',r'\bшұңқыр\w*',r'\bжол\w*'],
    'Отопление': [r'\bотоплен\w*',r'\bбатаре\w*',r'\bтеплоснаб\w*',r'\bжылу\w*',r'\bрадиатор\w*'],
    'Освещение': [r'\bосвещен\w*',r'\bфонар\w*',r'\bшам\w*',r'\bжарықтандыр\w*',r'\bуличн\w*\s+свет',r'\bкөше\w*\s+жарығ\w*'],
    'Общественный транспорт': [r'\bавтобус\w*',r'\bмаршрут\w*',r'\bостановк\w*',r'\bаялдама\w*',r'\bқоғамдық\s+көлік',r'\bтрамва\w*'],
    'Вывоз мусора': [r'\bмусор\w*',r'\bқоқыс\w*',r'\bконтейнер\w*',r'\bвывоз\w*',r'\bқалдық\w*'],
    'Благоустройство': [r'\bблагоустрой\w*',r'\bкачел\w*',r'\bплощадк\w*',r'\bскамей\w*',r'\bалаша\w*',r'\bабаттандыр\w*',r'\bойын\w*',r'\bәткеншек\w*',r'\bтротуар\w*',r'\bағаш\w*',r'\bдерев\w*'],
    'Экология': [r'\bэколог\w*',r'\bзагрязнен\w*',r'\bдым\w*',r'\bвыброс\w*',r'\bластан\w*',r'\bтүтін\w*',r'\bзапах\w*',r'\bауан\w*'],
}

# Canonical problem concepts bridge a LIMITED shared vocabulary in fallback mode.
CONCEPTS = {
    'water': r'\b(?:водоснаб\w*|водопровод\w*|вод(?:а|ы|у|е|ой)|су|сумен|сусыз)\b',
    'power': r'\b(?:электр\w*|электроэнерг\w*|ток|кернеу\w*|свет[а]?)\b',
    'lighting': r'\b(?:освещен\w*|фонар\w*|шам\w*|жарықтандыр\w*)\b',
    'heating': r'\b(?:отоплен\w*|батаре\w*|жылу\w*|радиатор\w*)\b',
    'road': r'\b(?:дорог\w*|асфальт\w*|жол\w*)\b',
    'pothole': r'\b(?:ям[аыуе]|выбоин\w*|шұңқыр\w*)\b',
    'transport': r'\b(?:автобус\w*|маршрут\w*|қоғамдық\s+көлік|трамва\w*)\b',
    'stop': r'\b(?:остановк\w*|аялдама\w*)\b',
    'waste': r'\b(?:мусор\w*|қоқыс\w*|контейнер\w*|қалдық\w*)\b',
    'playground': r'\b(?:качел\w*|площадк\w*|ойын\w*|әткеншек\w*)\b',
    'pollution': r'\b(?:загрязнен\w*|ластан\w*|выброс\w*|дым\w*|түтін\w*|запах\w*)\b',
    'pressure': r'\b(?:напор\w*|қысым\w*)\b',
    'leak': r'\b(?:прорыв\w*|протеч\w*|утеч\w*|ағып\s+жатыр|аққан)\b',
    'dirty': r'\b(?:грязн\w*|ржав\w*|лас|ластанған|сапасыз)\b',
    'absence': r'\b(?:нет|отсутств\w*|отключ\w*|перебо\w*|пропал\w*|жоқ|өш\w*|тоқта\w*|берілм\w*|болмай\w*)\b|не\s+(?:работа\w*|горит|горят|поступа\w*|пода[ею]\w*)|істемей\w*',
    'restored': r'\b(?:восстанов\w*|возобнов\w*|почини\w*|қалпына\s+кел\w*|қайта\s+беріл\w*|жөндел\w*)\b',
    'delay': r'\b(?:задерж\w*|не\s+вывоз\w*|кешіг\w*|жиналып\w*|шығарылм\w*)\b',
    'broken': r'\b(?:сломан\w*|поврежд\w*|бұзыл\w*|сынған)\b',
}
TOPIC_CONCEPTS={'water','power','lighting','heating','road','transport','stop','waste','playground','pollution'}

def clean(text: str) -> str:
    return unicodedata.normalize('NFKC', text).casefold().replace('ё','е').strip()

def concepts(text: str) -> set[str]:
    value=clean(text)
    return {name for name,pattern in CONCEPTS.items() if re.search(pattern,value)}

def lexical_category(text: str):
    value=clean(text)
    scores={cat:sum(bool(re.search(pattern,value)) for pattern in patterns) for cat,patterns in CATEGORY_RULES.items()}
    # A streetlight is not evidence of failure of household power.
    if scores['Освещение'] and not re.search(r'\b(?:электр\w*|электроэнерг\w*|кернеу\w*|ток)\b',value): scores['Электроснабжение']=0
    ordered=sorted(scores,key=lambda c:(-scores[c],CATEGORIES.index(c)))
    matches=[c for c in ordered if scores[c]]
    return (matches[0] if matches else 'Другое'), matches, scores

STREET_ALIAS={
    'абая':'абай','абай':'абай','абаев':'абай',
    'сейфуллина':'сейфуллин','сейфуллин':'сейфуллин','сәкен сейфуллин':'сейфуллин',
    'ауэзова':'ауэзов','әуезов':'ауэзов','ауэзов':'ауэзов',
    'достык':'достық','достық':'достық',
    'абылай хана':'абылай хан',
}

def normalize_address(address: str) -> str | None:
    value=clean(address)
    if value in {'','неизвестно','не указан','не указано','адрес не указан','unknown','белгісіз','-','—'}: return None
    value=re.sub(r'\[[^\]]*\]',' ',value)
    value=re.sub(r'\b(?:кв\.?|квартира|пәтер)\s*\d+\w*',' ',value)
    value=re.sub(r'(\d+)[ -]*(?:үй\w*)',r'\1',value)
    value=re.sub(r'(?<!\w)(?:ул|д|г)\.\s*',' ',value)
    value=re.sub(r'\b(?:улиц[аыеу]|ул\.?|көшес\w*|көше\w*|дом[ае]?|д\.|г\.|город)\b',' ',value)
    value=re.sub(r'\b(?:проспект\w*|пр-т|даңғыл\w*)\b','проспект',value)
    value=re.sub(r'[.,;:#№]',' ',value)
    value=re.sub(r'\s+',' ',value).strip()
    for source,target in sorted(STREET_ALIAS.items(),key=lambda item:-len(item[0])):
        value=re.sub(r'(?<!\w)'+re.escape(source)+r'(?!\w)',target,value)
    return value or None

def is_specific_address(value: str | None) -> bool:
    return bool(value and re.search(r'\d',value) and re.search(r'[а-яәғқңөұүһіa-z]',value) and not re.fullmatch(r'(?:район|микрорайон|мкр\.?|аудан|ықшамаудан)\s+[\w -]+',value))

def text_addresses(text: str) -> list[str]:
    value=clean(text)
    patterns=[
        r'(?:\bулиц[аеуы]\s+|\bул(?:\.\s*|\s+))([а-яәғқңөұүһі-]+(?:\s+[а-яәғқңөұүһі-]+)?)[, ]+(?:д(?:ом)?\.?\s*)?(\d+[а-яa-z]?(?:/\d+)?)',
        r'\bна\s+([а-яәғқңөұүһі-]+)\s*,?\s*(\d+[а-яa-z]?(?:/\d+)?)',
        r'\b([а-яәғқңөұүһі-]+)\s+көшес\w*\s*,?\s*(\d+)',
    ]
    found=[]
    for pattern in patterns:
        for street,building in re.findall(pattern,value):
            found.append(normalize_address(street+' '+building))
    return list(dict.fromkeys(found))

def canonical_text(text: str) -> str:
    value=clean(text)
    tags=concepts(value)
    for name,pattern in CONCEPTS.items(): value=re.sub(pattern,' '+name+' ',value)
    # Location and times are separate hard constraints; they must not inflate text similarity.
    for pattern in (r'\[[^\]]*\]',r'\d+',r'\b(?:ул|улиц\w*|көш\w*|дом\w*|үй\w*|день|дня|күн\w*|сегодня|вчера|бүгін|кеше|третий|второй)\b'):
        value=re.sub(pattern,' ',value)
    for alias in STREET_ALIAS: value=re.sub(r'(?<!\w)'+re.escape(alias)+r'(?!\w)',' ',value)
    value=re.sub(r'[^\w\s]',' ',value)
    value=re.sub(r'\b(?:на|в|во|и|не|по|у|с|со|за|из|для|после|очень|уже|теперь|совсем|тестовый|синтетический|пример)\b',' ',value)
    # Repeat canonical words to reduce dependence on a language's surface form, without inventing concepts.
    return ' '.join(sorted(tags))*1+' '+' '.join(sorted(tags))+' '+re.sub(r'\s+',' ',value).strip()

def publication_text(text: str) -> str:
    value=clean(text)
    value=re.sub(r'\b(?:репост|перепубликация|копия обращения)\s*:?','',value)
    return re.sub(r'\s+',' ',re.sub(r'[^\w\s\[\]]',' ',value)).strip()


def has_negated_event(text: str) -> bool:
    value=clean(text)
    return bool(re.search(r'\bне\s+(?:отключ\w*|поврежд\w*|сломан\w*|загрязн\w*|восстанов\w*|устран\w*)|\b(?:отключени\w*|авари\w*|проблем\w*|повреждени\w*)\s+нет|\b(?:өшкен|бұзылған|ластанған)\s+жоқ', value))
