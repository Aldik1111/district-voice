"""Offline E5 embeddings with an explicitly labelled character TF-IDF fallback.

Every case is a complete-link clique within a bounded date span. Recurrent
problems also require pairwise compatible cases, not connected components.
No HTTP/model download path is reachable from analyze().
"""
import hashlib
import importlib.util
import json
import os
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from ..privacy import mask
from .normalization import CATEGORIES, TOPIC_CONCEPTS, canonical_text, clean, concepts, has_negated_event, is_specific_address, lexical_category, normalize_address, publication_text, text_addresses

_LOADED_MODEL_PATHS=set()
MODEL_ID='intfloat/multilingual-e5-small'
MODEL_REVISION='614241f622f53c4eeff9890bdc4f31cfecc418b3'
MAX_APPEALS=500
CASE_DAYS=3
RECURRENCE_MIN_DAYS=7
RECURRENCE_MAX_DAYS=90
THRESHOLDS={'multilingual-e5-small':0.84,'tfidf_char':0.34}
PROTOTYPES={
    'Водоснабжение':['Нет воды, низкий напор, протечка водопровода.','Су жоқ, судың қысымы төмен, құбырдан су ағып жатыр.'],
    'Электроснабжение':['Отключение электричества, нет света в доме, напряжение в электросети.','Үйде электр қуаты жоқ, электр желісінің кернеуі төмен.'],
    'Дороги':['На дороге ямы, повреждён асфальт, требуется ремонт дороги.','Жолда шұңқырлар бар, асфальт бұзылған.'],
    'Отопление':['Нет отопления, холодные батареи, дом не отапливается.','Үйде жылу жоқ, батареялар суық.'],
    'Освещение':['Не работают уличные фонари, во дворе темно.','Көше шамдары жанбайды, аулада жарық жоқ.'],
    'Общественный транспорт':['Автобус не приезжает на остановку, нарушает расписание маршрута.','Автобус аялдамаға келмейді, кесте бұзылған.'],
    'Вывоз мусора':['Мусор не вывозят, переполненные контейнеры, скопление отходов.','Қоқыс шығарылмайды, контейнерлер толып қалған.'],
    'Благоустройство':['Сломаны качели на детской площадке, повреждены скамейки и тротуар.','Балалар алаңындағы әткеншек сынған, ауланы абаттандыру керек.'],
    'Экология':['Загрязнение воздуха, дым, выбросы завода, неприятный запах.','Ауа ластанған, зауыттан түтін мен жағымсыз иіс шығады.'],
    'Другое':['Иной вопрос, не относящийся к городской инфраструктуре.','Қала инфрақұрылымына қатысы жоқ басқа мәселе.'],
}

def model_path() -> Path:
    return Path(os.getenv('DISTRICT_VOICE_MODEL_PATH',str(Path(__file__).resolve().parents[2]/'models'/'multilingual-e5-small'))).resolve()

@lru_cache(maxsize=2)
def _cached_model(path: str):
    # Even a broken or incomplete local cache must NEVER initiate network traffic.
    os.environ['HF_HUB_OFFLINE']='1'
    os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
    os.environ['TRANSFORMERS_OFFLINE']='1'
    from sentence_transformers import SentenceTransformer
    import torch
    torch.set_num_threads(max(1,min(4,os.cpu_count() or 1)))
    model=SentenceTransformer(path,device='cpu',local_files_only=True,trust_remote_code=False,token=False)
    model.max_seq_length=512
    _LOADED_MODEL_PATHS.add(path)
    return model

def _load_model():
    path=model_path()
    if not (path/'model.safetensors').is_file() or not (path/'modules.json').is_file():
        raise FileNotFoundError('Local model is not installed')
    return _cached_model(str(path))

def _model_revision():
    try:
        manifest=json.loads((model_path()/'MODEL-MANIFEST.json').read_text(encoding='utf-8'))
        return manifest.get('revision') if manifest.get('model_id')==MODEL_ID else None
    except (OSError,ValueError):
        return None

def _metadata(semantic: bool, reason: str | None = None) -> dict:
    return {'name':'multilingual-e5-small' if semantic else 'tfidf_char','label':'Multilingual E5 · локальные embeddings' if semantic else 'TF-IDF · символьные n-граммы (резервный текстовый метод)',
            'semantic':semantic,'model_id':MODEL_ID if semantic else None,'model_revision':_model_revision() if semantic else None,'fallback_reason':reason,'available':True,
            'case_window_days':CASE_DAYS,'recurrence_min_days':RECURRENCE_MIN_DAYS,'recurrence_max_days':RECURRENCE_MAX_DAYS,
            'similarity_threshold':THRESHOLDS['multilingual-e5-small' if semantic else 'tfidf_char'],'max_appeals':MAX_APPEALS,'score_is_probability':False}

def get_engine_status() -> dict:
    path=model_path()
    ready=(path/'model.safetensors').is_file() and (path/'modules.json').is_file() and importlib.util.find_spec('sentence_transformers') is not None
    result=_metadata(ready,None if ready else 'Локальная модель отсутствует. Доступен резервный TF-IDF.')
    result['model_load_verified']=ready and str(path) in _LOADED_MODEL_PATHS
    result['note']='Модель загружена в этом процессе; фактический алгоритм указан в результате запуска.' if result['model_load_verified'] else 'Доступность файлов не гарантирует загрузку; фактический алгоритм указан в результате запуска.'
    return result

def _represent(texts: list[str], mode: str):
    reason='Резервный метод выбран пользователем.' if mode=='tfidf' else None
    if mode=='auto':
        try:
            model=_load_model()
            prototypes=[text for cat in CATEGORIES for text in PROTOTYPES[cat]]
            # E5 model card: query prefix for BOTH inputs in symmetric similarity / clustering.
            encoded=model.encode(['query: '+text for text in texts+prototypes],normalize_embeddings=True,batch_size=16,show_progress_bar=False,convert_to_numpy=True)
            if not np.isfinite(encoded).all(): raise ValueError('Invalid model vectors')
            vectors=encoded[:len(texts)]
            proto_scores=np.clip(vectors@encoded[len(texts):].T,0,1)
            return np.clip(vectors@vectors.T,0,1),proto_scores,_metadata(True)
        except Exception as exc:
            # Do not expose model/parser exception messages: they can echo user inputs and machine paths.
            reason=f'Локальные embeddings недоступны ({type(exc).__name__}); использован TF-IDF. Тексты никуда не отправлялись.'
    vectorizer=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),min_df=1,max_features=40000,sublinear_tf=True,dtype=np.float32)
    normalized=[canonical_text(text) or 'пусто' for text in texts]
    matrix=vectorizer.fit_transform(normalized)
    return np.clip(cosine_similarity(matrix),0,1),None,_metadata(False,reason)

def _classify(text, proto_scores, override):
    category,matches,weights=lexical_category(text)
    uncertainties=[]
    score=min(0.95,0.60+0.10*weights.get(category,0)) if matches else 0.0
    method='bilingual_rules'
    if len(matches)>1:
        uncertainties.append('Несколько тематических признаков: '+', '.join(matches)+'. Категорию нужно проверить.')
    if proto_scores is not None:
        category_scores=np.max(np.asarray(proto_scores).reshape(len(CATEGORIES),2),axis=1)
        ranking=np.argsort(category_scores)[::-1]
        best=CATEGORIES[int(ranking[0])]; margin=float(category_scores[ranking[0]]-category_scores[ranking[1]])
        method='e5_prototypes+bilingual_rules'
        if not matches:
            if category_scores[ranking[0]]>=0.80 and margin>=0.015:
                category=best; score=float(category_scores[ranking[0]])
                uncertainties.append('Категория предложена сходством с прототипами, требуется ручная проверка.')
            else:
                category='Другое'; score=float(category_scores[ranking[0]])
        else:
            score=float(category_scores[CATEGORIES.index(category)])
            if best!=category and margin>0.015:
                uncertainties.append('Словарные признаки и модель предлагают разные категории; сохранена словарная категория.')
    if category=='Другое': uncertainties.append('Недостаточно признаков для определённой категории.')
    proposed=category
    if override in CATEGORIES:
        category=override; method='manual_override'; score=1.0
        # A manual category does not certify an event or address, only this category field.
    return category,proposed,method,round(score,4),uncertainties

def _key(prefix: str, ids: list[str]) -> str:
    return prefix+'-'+hashlib.sha256('\n'.join(sorted(ids)).encode()).hexdigest()[:20]

def analyze(records: list[dict], mode: str = 'auto') -> dict:
    if mode not in {'auto','tfidf'}: raise ValueError('Unknown mode')
    if len(records)>MAX_APPEALS: raise ValueError('Maximum 500 appeals per analysis')
    if len({r['id'] for r in records})!=len(records): raise ValueError('Duplicate input ID')
    ordered=sorted(records,key=lambda r:(r['date'],r['source'],r['source_record_id'],r['id']))
    active=[]; results=[]; internals={}
    for record in ordered:
        # Reapply masking in memory as defence in depth. Unreviewed suspicious rows are never embedded.
        safe_text=mask(record['text']); safe_address=mask(record.get('address') or '')
        if record.get('privacy_status')=='review_required' or safe_text.text!=record['text'] or safe_address.text!=(record.get('address') or ''):
            results.append({'appeal_id':record['id'],'category':record.get('override_category') or 'Другое','proposed_category':'Другое','classification_method':'blocked_privacy','score':0.0,
                            'uncertainties':['Анализ остановлен: сначала проверьте персональные сведения.'],'territory':None,'duplicate_kind':'independent','duplicate_of':None,'explanations':[],
                            'status':'blocked','input_version':record.get('version',1)})
        else: active.append(record)
    if active:
        similarities,prototypes,algorithm=_represent([r['text'] for r in active],mode)
    else:
        similarities=np.empty((0,0)); prototypes=None; algorithm=_metadata(False,'Нет допустимых записей для анализа.')
    for index,record in enumerate(active):
        category,proposed,method,score,uncertainties=_classify(record['text'],None if prototypes is None else prototypes[index],record.get('override_category'))
        territory=normalize_address(record.get('address') or '')
        extracted=text_addresses(record['text'])
        conflict=False
        if territory is None:
            uncertainties.append('Адрес/территория неизвестны; автоматическое объединение запрещено.')
        elif not is_specific_address(territory):
            uncertainties.append('Территория слишком широкая или без номера дома; автоматическое объединение запрещено.')
        if territory and extracted:
            # Only compare a complete explicit extracted street+number to complete field values.
            if any(item!=territory and not territory.endswith(' '+item) for item in extracted):
                uncertainties.append('Противоречие адреса: адрес в тексте отличается от поля адреса.');conflict=True
        signs=concepts(record['text'])
        if has_negated_event(record['text']):
            uncertainties.append('Есть отрицание события или противоречащие признаки; автоматическое объединение запрещено.'); conflict=True
        if 'restored' in signs:
            uncertainties.append('Сообщение о восстановлении: его нельзя автоматически объединять с сообщением об отсутствии услуги.');conflict=True
        if algorithm['semantic'] and len(record['text'])>1800:
            uncertainties.append('Длинный текст: модель учитывает до 512 токенов; возможна потеря деталей.')
        _,category_matches,_=lexical_category(record['text'])
        if len(category_matches)>1 and not record.get('override_category'): conflict=True
        result={'appeal_id':record['id'],'category':category,'proposed_category':proposed,'classification_method':method,'score':score,
                'uncertainties':uncertainties,'territory':territory,'duplicate_kind':'independent','duplicate_of':None,
                'explanations':['Категория по локальным прототипам и словарям.' if prototypes is not None else 'Категория по ограниченному русско-казахскому словарю.'],
                'status':'review_required' if uncertainties else 'analyzed','input_version':record.get('version',1)}
        results.append(result)
        internals[record['id']]={'record':record,'result':result,'index':index,'day':date.fromisoformat(record['date']),'signs':signs,
                                'can_group':is_specific_address(territory) and not conflict and category!='Другое'}
    rows=list(internals.values())
    threshold=algorithm['similarity_threshold']

    def compatible(a,b,max_days=CASE_DAYS):
        ra,rb=a['result'],b['result']
        if not a['can_group'] or not b['can_group']: return False
        if ra['category']!=rb['category'] or ra['territory']!=rb['territory']: return False
        if abs((a['day']-b['day']).days)>max_days: return False
        # Disjoint specific symptoms are not merged merely because the topic matches.
        sa=a['signs']-TOPIC_CONCEPTS; sb=b['signs']-TOPIC_CONCEPTS
        if sa and sb and not(sa & sb):
            # Outage and weak pressure can describe a supply interruption; other contrasts stay separate.
            if not(sa|sb <= {'absence','pressure'}): return False
        return float(similarities[a['index'],b['index']])>=threshold

    # Publication candidates: wording identity at the same known location within the recurrence window.
    # A later copy must not become an independent recurring event just because its posting date differs.
    for index,b in enumerate(rows):
        for a in rows[:index]:
            anchor=internals[a['result']['duplicate_of'] or a['record']['id']]
            if abs((anchor['day']-b['day']).days)>RECURRENCE_MAX_DAYS: continue
            if a['result']['territory'] is None or a['result']['territory']!=b['result']['territory']: continue
            if a['result']['category']!=b['result']['category'] or abs((a['day']-b['day']).days)>RECURRENCE_MAX_DAYS: continue
            va=publication_text(a['record']['text']); vb=publication_text(b['record']['text'])
            if va==vb and len(va)>=15:
                b['result']['duplicate_kind']='republication_candidate'
                b['result']['duplicate_of']=a['result']['duplicate_of'] or a['record']['id']
                b['result']['uncertainties'].append('Возможная повторная публикация: текст совпадает; независимость свидетельства не подтверждена.')
                b['result']['status']='review_required'
                break

    # Deterministic complete-link: candidates must pass ALL members and the entire date span.
    clusters=[]
    for row in rows:
        candidates=[group for group in clusters if all(compatible(row,member) for member in group)]
        if candidates:
            best=max(candidates,key=lambda group:min(float(similarities[row['index'],m['index']]) for m in group))
            best.append(row)
        else: clusters.append([row])

    def group_json(members,kind):
        ids=[m['record']['id'] for m in members]
        dates=[m['record']['date'] for m in members]
        minimum=min((float(similarities[a['index'],b['index']]) for i,a in enumerate(members) for b in members[i+1:]),default=1.0)
        uncertainties=list(dict.fromkeys(u for m in members for u in m['result']['uncertainties']))
        uncertainties.append('Предложение системы; требуется решение аналитика. Независимость авторов сообщений не установлена.')
        if not algorithm['semantic']: uncertainties.append('Сходство рассчитано резервным TF-IDF; это не полноценная семантическая модель.')
        if len(members)==1: uncertainties.append('Одиночное сообщение; других подтверждений в группе нет.')
        explanations=[f"Категория: {members[0]['result']['category']}.",f"Территория из поля адреса: {members[0]['result']['territory'] or 'неизвестно'}."]
        if len(members)>1:
            explanations += [f'Проверены все пары сообщений; минимальное сходство {minimum:.3f}, порог {threshold:.2f}.',
                             f'Даты обращений: {min(dates)} — {max(dates)}. Это даты сообщений, а не установленное время аварии.']
        else: explanations.append('Сохранён отдельный случай без автоматического объединения.')
        if any(m['result']['duplicate_of'] for m in members): explanations.append('Совпадающие публикации учитываются одной условной цепочкой, а не дополнительным независимым свидетельством.')
        return {'key':_key(kind,ids),'category':members[0]['result']['category'],'territory':members[0]['result']['territory'],
                'start_date':min(dates),'end_date':max(dates),'appeal_ids':ids,'message_count':len(ids),
                'source_count':len({m['record']['source'] for m in members}),
                'independent_evidence_count':sum(m['result']['duplicate_of'] is None for m in members),
                'explanations':explanations,'uncertainties':uncertainties,'status':'proposed','minimum_similarity':round(max(0,min(1,minimum)),4)}
    cases=[group_json(group,'case') for group in clusters]
    recurring=[]
    for i,cluster in enumerate(clusters):
        def recurring_match(j):
            earlier=clusters[j]
            families=lambda group: {m['result']['duplicate_of'] or m['record']['id'] for m in group}
            if families(cluster) & families(earlier): return False
            gap=(min(m['day'] for m in cluster)-max(m['day'] for m in earlier)).days
            return gap>=RECURRENCE_MIN_DAYS and all(compatible(a,b,RECURRENCE_MAX_DAYS) for a in cluster for b in earlier)
        candidates=[group for group in recurring if all(recurring_match(j) for j in group)]
        if candidates: candidates[0].append(i)
        else: recurring.append([i])
    problems=[]
    for indexes in recurring:
        if len(indexes)<2: continue
        members=[member for i in indexes for member in clusters[i]]
        problem=group_json(members,'problem'); problem['case_keys']=[cases[i]['key'] for i in indexes]
        problem['explanations'].append(f'Связаны {len(indexes)} отдельных случаев, разделённых минимум {RECURRENCE_MIN_DAYS} днями, в пределах {RECURRENCE_MAX_DAYS} дней. Причина повторения не установлена.')
        problems.append(problem)
    return {'algorithm':algorithm,'results':results,'cases':cases,'problems':problems}
