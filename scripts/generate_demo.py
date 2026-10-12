"""Deterministic fictional dataset. Gold labels are authored here, never inferred by AI."""
import csv
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = ["ДЕМО · Портал", "ДЕМО · Открытый чат", "ДЕМО · Приёмная"]
rows, labels = [], []


def add(text, address, day, case, category, problem=None, duplicate_of=None, accepted=True):
    index = len(rows) + 1
    record = {"source_record_id": f"SYN-{index:03d}", "source": SOURCES[(index - 1) % 3], "date": day, "text": text, "address": address, "official_status": "СИНТЕТИЧЕСКИЙ ПРИМЕР"}
    rows.append(record)
    labels.append({"row": index + 1, "source_record_id": record["source_record_id"], "source": record["source"], "import": "accepted" if accepted else "invalid_date", "case": case, "problem": problem, "category": category, "republication_of": duplicate_of})


NOTES_RU = ["Сообщаю о ситуации утром.", "Замечено в дневное время.", "Нужна проверка на месте.", "Прошу принять обращение.", "Ситуация сохраняется к вечеру.", "Просьба уточнить срок работ.", "Это наблюдение с указанного адреса.", "Прошу зарегистрировать проблему."]
NOTES_KK = ["Таңертең байқадым.", "Күндіз де сол жағдай.", "Осы жерді тексеруді сұраймын.", "Өтінішті қабылдаңыз.", "Кешке дейін өзгеріс жоқ.", "Жұмыс мерзімін нақтылаңыз.", "Бұл көрсетілген мекенжайдағы жағдай.", "Мәселені тіркеуді сұраймын."]


def scenario(count, address, day, case, category, ru, kk, problem=None):
    for index in range(count):
        kazakh = index % 3 == 1
        base = (kk if kazakh else ru)[(index // 3) % 2]
        note = (NOTES_KK if kazakh else NOTES_RU)[index % 8]
        add(base + " " + note, address, day, case, category, problem)


scenario(20, "ул. Абая, 150", "2026-10-05", "water-main", "Водоснабжение",
         ["На улице Абая 150 нет холодной воды.", "На улице Абая 150 отключили подачу холодной воды."],
         ["Абай көшесі 150 үйде су жоқ.", "Абай көшесі 150 үйде су беру тоқтады."])
# A deliberate semantic trap: same symptom/place/time, but a separate internal repair.
# This gold label is independent of whether a particular model merges the message.
add("На улице Абая 150 нет холодной воды. Здесь отдельный ремонт внутреннего крана, относится только к мастерской.", "ул. Абая, 150", "2026-10-05", "water-workshop", "Водоснабжение")
for original in (0, 1, 2):
    add(rows[original]["text"], rows[original]["address"], rows[original]["date"], "water-main", "Водоснабжение", duplicate_of=rows[original]["source_record_id"])
for episode, day, ru_time, kk_time in [(1, "2026-09-01", "В начале сентября", "Қыркүйек басында"), (2, "2026-09-16", "В середине сентября", "Қыркүйек ортасында"), (3, "2026-10-01", "В начале октября", "Қазан басында")]:
    scenario(14, "ул. Сейфуллина, 220", day, f"power-{episode}", "Электроснабжение",
             [f"{ru_time} на улице Сейфуллина 220 пропало электричество.", f"{ru_time} на улице Сейфуллина 220 перебои электроснабжения."],
             [f"{kk_time} Сейфуллин көшесі 220 үйде электр өшті.", f"{kk_time} Сейфуллин көшесі 220 үйде электр тогы жоқ."], "recurring-power")
scenario(20, "ул. Достык, 330", "2026-10-04", "streetlights", "Освещение", ["На улице Достык 330 не работают уличные фонари.", "На улице Достык 330 не горят фонари освещения."], ["Достық көшесі 330 үй жанында көше шамдары істемейді.", "Достық көшесі 330 үй жанында көше жарықтандыруы істемейді."])
scenario(18, "ул. Ауэзова, 440", "2026-10-03", "potholes", "Дороги", ["На улице Ауэзова 440 ямы на дороге.", "На улице Ауэзова 440 повреждён асфальт, глубокие выбоины."], ["Әуезов көшесі 440 үй жанында жолда шұңқырлар бар.", "Әуезов көшесі 440 үй жанында асфальт бұзылған."])
scenario(18, "ул. Абая, 550", "2026-10-02", "waste", "Вывоз мусора", ["На улице Абая 550 не вывозят мусор из контейнеров.", "На улице Абая 550 мусор переполнил контейнеры."], ["Абай көшесі 550 үй жанында қоқыс шығарылмайды.", "Абай көшесі 550 үй жанында контейнерде қоқыс жиналған."])
scenario(14, "ул. Абая, 660", "2026-10-05", "water-other-address", "Водоснабжение", ["На улице Абая 660 нет холодной воды.", "На улице Абая 660 отключили подачу холодной воды."], ["Абай көшесі 660 үйде су жоқ.", "Абай көшесі 660 үйде су беру тоқтады."])
scenario(8, "ул. Достык, 770", "2026-10-06", "heating", "Отопление", ["На улице Достык 770 нет отопления, батареи холодные.", "На улице Достык 770 не работает отопление."], ["Достық көшесі 770 үйде жылу жоқ.", "Достық көшесі 770 үйде жылу беру тоқтады."])
scenario(8, "ул. Ауэзова, 880", "2026-10-07", "bus", "Общественный транспорт", ["На улице Ауэзова 880 автобус опаздывает к остановке.", "На улице Ауэзова 880 задержка автобуса на остановке."], ["Әуезов көшесі 880 үй жанында автобус кешігеді.", "Әуезов көшесі 880 үй жанындағы аялдамаға автобус кеш келеді."])
scenario(8, "ул. Сейфуллина, 990", "2026-10-08", "playground", "Благоустройство", ["На улице Сейфуллина 990 сломаны качели на площадке.", "На улице Сейфуллина 990 повреждена игровая площадка."], ["Сейфуллин көшесі 990 үй жанында әткеншек сынған.", "Сейфуллин көшесі 990 үй жанында ойын алаңы бұзылған."])
scenario(6, "ул. Достык, 110", "2026-10-09", "ecology", "Экология", ["На улице Достык 110 дым и загрязнение воздуха.", "На улице Достык 110 сильный запах дыма."], ["Достық көшесі 110 үй жанында түтін көп.", "Достық көшесі 110 үй жанында ауа ластанған."])
for index in range(6):
    add(("Нет холодной воды. " + NOTES_RU[index]) if index % 2 else ("Су жоқ. " + NOTES_KK[index]), "", "2026-10-05", f"unknown-{index + 1}", "Водоснабжение")
for index, text in enumerate(["На улице Абая 150 нет воды, но подача воды уже восстановлена.", "На улице Абая 660 нет холодной воды.", "На улице Достык 330 не работают фонари и пропало электричество в доме.", "На улице Сейфуллина 220 отключения электричества нет."]):
    add(text, ["ул. Абая, 150", "ул. Абая, 150", "ул. Достык, 330", "ул. Сейфуллина, 220"][index], "2026-10-05", f"review-{index + 1}", ["Водоснабжение", "Водоснабжение", "Электроснабжение", "Электроснабжение"][index])
for invalid in ("2026-02-30", "неизвестная дата"):
    add("Синтетическая строка с ошибочной датой. Нет воды.", "ул. Абая, 150", invalid, None, "Водоснабжение", accepted=False)
for original in (0, 24):
    rows.append(dict(rows[original]))
    labels.append({**labels[original], "row": len(rows) + 1, "import": "technical_duplicate", "technical_duplicate_of": original + 2})
assert len(rows) == 180
buffer = io.StringIO(newline="")
writer = csv.DictWriter(buffer, fieldnames=list(rows[0]))
writer.writeheader()
writer.writerows(rows)
for destination in (ROOT / "data/demo-180.csv", ROOT / "frontend/public/demo-180.csv"):
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(buffer.getvalue().encode("utf-8-sig"))
cases = {}
for label in labels:
    if label["import"] == "accepted":
        cases.setdefault(label["case"], []).append(label["source_record_id"])
gold = {"synthetic": True, "description": "Все сообщения, адреса и события вымышлены. Эталон задан авторами сценариев до запуска алгоритма; это контрольные данные, не оценка качества на реальных обращениях.",
        "expected_import": {"rows": 180, "accepted": 176, "rejected": 2, "duplicates": 2, "conflicts": 0},
        "cases": cases, "problems": {"recurring-power": ["power-1", "power-2", "power-3"]},
        "manual_review_target": {"record": "SYN-021", "reason": "Отдельный внутренний ремонт крана мастерской не является подтверждением общего отключения воды.", "expected_case": "water-workshop"},
        "notes": ["Шесть обращений без адреса остаются отдельными неопределёнными случаями.", "Четыре противоречивые записи review-* требуют ручной проверки и не подтверждают основную группу.", "Дословные копии внутри шаблонов также могут быть кандидатами в перепубликации; независимость авторов не установлена."], "rows": labels}
(ROOT / "data/demo-180-gold.json").write_text(json.dumps(gold, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(json.dumps(gold["expected_import"]))
