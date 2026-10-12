"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowDownToLine, ArrowRight, Check, CheckCircle2, ChevronDown, FileSpreadsheet, LoaderCircle, RefreshCw, ShieldCheck, UploadCloud, X } from "lucide-react";
import { api, Batch, date, ImportResult, number, Preview, shortId } from "@/lib/api";
import { Empty, ErrorBox, Loading, PageTitle, PrivacyBadge } from "@/components/ui";

const fields = [
  { key: "source", label: "Источник", required: true },
  { key: "source_record_id", label: "ID в источнике", required: true },
  { key: "date", label: "Дата обращения", required: true },
  { key: "text", label: "Текст обращения", required: true },
  { key: "address", label: "Адрес", required: false },
  { key: "official_status", label: "Официальный статус", required: false },
];

export default function ImportPage() {
  const fileInput = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [mappingDirty, setMappingDirty] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState<"preview" | "confirm" | null>(null);
  const [error, setError] = useState("");
  const [result, setResult] = useState<ImportResult | null>(null);
  const [batches, setBatches] = useState<Batch[]>([]);
  const [historyLoading, setHistoryLoading] = useState(true);
  const [historyError, setHistoryError] = useState("");
  const [onlyIssues, setOnlyIssues] = useState(false);
  const [previewPage, setPreviewPage] = useState(1);
  const loadHistory = useCallback(async () => {
    setHistoryLoading(true); setHistoryError("");
    try { setBatches(await api<Batch[]>("/imports")); }
    catch (e) { setHistoryError(e instanceof Error ? e.message : "Не удалось получить историю"); }
    finally { setHistoryLoading(false); }
  }, []);
  useEffect(() => { void loadHistory(); }, [loadHistory]);
  async function loadPreview(selected: File, customMapping?: Record<string, string>) {
    setBusy("preview"); setError(""); setResult(null); setPreviewPage(1);
    const data = new FormData();
    data.append("file", selected);
    if (customMapping) data.append("mapping", JSON.stringify(customMapping));
    try {
      const value = await api<Preview>("/imports/preview", { method: "POST", body: data });
      setPreview(value); setMapping(value.mapping); setMappingDirty(false);
    } catch (e) { setError(e instanceof Error ? e.message : "Ошибка чтения файла"); }
    finally { setBusy(null); }
  }
  function selectFile(selected?: File) {
    if (!selected || busy) return;
    setPreview(null); setResult(null); setMappingDirty(false); setFile(null);
    if (!/\.(csv|xlsx)$/i.test(selected.name)) { setError("Выберите файл .csv или .xlsx."); return; }
    if (selected.size > 5 * 1024 * 1024) { setError("Файл слишком большой. Максимальный размер — 5 МБ."); return; }
    setFile(selected); setPreview(null); setResult(null); setOnlyIssues(false);
    void loadPreview(selected);
  }
  async function openDemo() {
    if (busy) return;
    setError("");
    try {
      const response = await fetch("/demo-180.csv");
      if (!response.ok) throw new Error("Демонстрационный файл недоступен.");
      const blob = await response.blob();
      selectFile(new File([blob], "district-voice-synthetic-180.csv", { type: "text/csv" }));
    } catch (e) { setError(e instanceof Error ? e.message : "Не удалось открыть пример"); }
  }
  function reset() {
    setFile(null); setPreview(null); setResult(null); setError(""); setMapping({}); setMappingDirty(false);
    if (fileInput.current) fileInput.current.value = "";
  }
  async function confirm() {
    if (!preview || busy || mappingDirty || result) return;
    setBusy("confirm"); setError("");
    try {
      const value = await api<ImportResult>("/imports/confirm", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ preview_id: preview.preview_id }) });
      setResult(value); await loadHistory();
    } catch (e) { setError(e instanceof Error ? e.message : "Ошибка сохранения"); }
    finally { setBusy(null); }
  }
  const rows = preview?.rows.filter(row => !onlyIssues || row.errors.length > 0 || row.warnings.length > 0 || row.duplicate_status !== "new") || [];
  const visibleRows = rows.slice((previewPage - 1) * 20, previewPage * 20);
  return <>
    <PageTitle eyebrow="ПОДГОТОВКА ДАННЫХ" title="Загрузка данных" description="Загрузите файл, проверьте поля и добавьте обращения в реестр."><button className="button button-white" onClick={openDemo} disabled={!!busy} title="180 синтетических строк: русский и казахский, ошибки и дубли"><FileSpreadsheet size={16} />Загрузить демоданные</button><a className="button button-white button-icon" href="/demo-180.csv" download aria-label="Скачать пример CSV" title="Скачать пример CSV"><ArrowDownToLine size={16} /></a></PageTitle>
    <div className="steps"><div className={`step ${file ? "complete" : "current"}`}><span>{file ? <Check size={14} /> : "1"}</span>Загрузить файл</div><div className="step-connector" /><div className={`step ${result ? "complete" : preview ? "current" : ""}`}><span>{result ? <Check size={14} /> : "2"}</span>Проверить данные</div><div className="step-connector" /><div className={`step ${result ? "complete" : ""}`}><span>{result ? <Check size={14} /> : "3"}</span>Сохранить в реестр</div></div>
    {error && <ErrorBox message={error} />}
    {result ? <section className="import-success"><div className="success-icon"><CheckCircle2 size={31} /></div><h2>Партия #{shortId(result.batch_id)} сохранена</h2><p>Результаты импорта файла «{file?.name}»</p><div className="result-counts"><div><strong>{number(result.accepted)}</strong><span>добавлено</span></div><div><strong>{number(result.rejected)}</strong><span>отклонено</span></div><div><strong>{number(result.duplicates)}</strong><span>дубликатов</span></div><div><strong>{number(result.conflicts)}</strong><span>конфликтов</span></div></div><div className="success-actions"><button className="button button-white" onClick={reset}>Загрузить ещё файл</button><Link className="button button-primary" href="/analysis">Перейти к анализу <ArrowRight size={16} /></Link></div></section> : <>
      <div className="import-top-grid"><section className="panel upload-panel"><div className="panel-heading"><div><h2>Файл с обращениями</h2><p>Поддерживаются CSV и Excel (.xlsx)</p></div><span className="badge badge-neutral">До 5 МБ</span></div><input ref={fileInput} type="file" id="appeals-file" aria-label="Файл обращений CSV или Excel" accept=".csv,.xlsx" className="sr-only" disabled={!!busy} onChange={e => selectFile(e.target.files?.[0])} /><button type="button" className={`dropzone ${dragging ? "dragging" : ""}`} disabled={!!busy} onClick={() => fileInput.current?.click()} onDragOver={e => { e.preventDefault(); if (!busy) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); selectFile(e.dataTransfer.files[0]); }}><span className="upload-icon">{busy === "preview" ? <LoaderCircle size={27} className="spin" /> : <UploadCloud size={28} />}</span><strong>{busy === "preview" ? "Читаем файл и проверяем данные…" : file ? "Выбрать другой файл" : "Нажмите для загрузки или перетащите файл"}</strong><span>Первая строка — заголовки столбцов</span></button>{file && <div className="selected-file"><FileSpreadsheet size={22} /><div><strong>{file.name}</strong><span>{number(Math.ceil(file.size / 1024))} КБ · {preview ? `${number(preview.total_rows)} строк` : "Проверка файла"}</span></div><button className="icon-button" aria-label="Убрать выбранный файл" onClick={reset} disabled={!!busy}><X size={17} /></button></div>}</section>
      <aside className="import-help"><ShieldCheck size={23} /><h3>Данные проходят проверку</h3><p>Перед сохранением система проверит обязательные поля, даты и повторяющиеся ID, скроет телефоны, email и ИИН.</p><div className="help-divider" /><strong>Подготовьте файл</strong><ul><li>Источник, ID, дата и текст обязательны.</li><li>Для даты используйте ГГГГ-ММ-ДД.</li><li>Одна строка — одно обращение.</li></ul><small>Пример CSV: 180 строк, только синтетические данные.</small></aside></div>
      {preview && <>
        <section className="panel mapping-panel"><div className="panel-heading"><div><h2>Сопоставление столбцов</h2><p>Проверьте, откуда брать каждое поле. * — обязательные поля.</p></div><span className="badge badge-blue">{mappingDirty ? "Есть изменения" : "Сопоставлено"}</span></div><div className="mapping-grid">{fields.map(field => <label className="field" key={field.key}><span>{field.label}{field.required && <em> *</em>}</span><div className="select-wrap"><select value={mapping[field.key] || ""} disabled={!!busy} onChange={e => { setMapping({ ...mapping, [field.key]: e.target.value }); setMappingDirty(true); }}><option value="">Не выбрано</option>{preview.columns.map(column => <option value={column} key={column}>{column}</option>)}</select><ChevronDown size={15} /></div></label>)}</div>{mappingDirty && <div className="mapping-actions"><span>Обновите предпросмотр, чтобы применить сопоставление.</span><button className="button button-primary" disabled={!!busy || !file} onClick={() => file && loadPreview(file, mapping)}><RefreshCw size={15} className={busy === "preview" ? "spin" : ""} />Обновить предпросмотр</button></div>}</section>
        <section className="panel preview-panel"><div className="panel-heading"><div><h2>Проверка данных</h2><p>Показано обезличенное представление · исходный файл не сохраняется</p></div><label className="checkbox-label"><input type="checkbox" checked={onlyIssues} onChange={e => { setOnlyIssues(e.target.checked); setPreviewPage(1); }} />Только замечания</label></div><div className="validation-counts"><span>Всего строк <strong>{number(preview.total_rows)}</strong></span><span className="count-green">Валидных <strong>{number(preview.valid_rows)}</strong></span><span className={preview.invalid_rows ? "count-red" : ""}>С ошибками <strong>{number(preview.invalid_rows)}</strong></span><span>Дубликатов <strong>{number(preview.duplicate_rows)}</strong></span><span className={preview.conflict_rows ? "count-amber" : ""}>Конфликтов ID <strong>{number(preview.conflict_rows)}</strong></span></div>
        {preview.invalid_rows + preview.conflict_rows + preview.duplicate_rows > 0 && <div className="inline-notice"><AlertTriangle size={17} /><p>Строки с ошибками, повторными ID и конфликтами будут пропущены. Остальные можно сохранить. Если один ID содержит разные обращения, исправьте исходный файл.</p></div>}
        <div className="table-scroll"><table className="data-table preview-table"><thead><tr><th>Строка / ID</th><th>Источник / дата</th><th>Обращение</th><th>Проверка</th></tr></thead><tbody>{visibleRows.map(row => <tr key={row.row_number} className={row.errors.length ? "row-error" : ""}><td><strong>Строка {row.row_number}</strong><small>{row.source_record_id || "ID отсутствует"}</small></td><td><strong>{row.source || "—"}</strong><small>{date(row.date)}</small></td><td className="preview-text"><p>{row.text || "Текст отсутствует"}</p><small>{row.address || "Адрес не указан"}</small></td><td className="validation-cell"><PrivacyBadge status={row.privacy_status} />{row.duplicate_status !== "new" && <span className="badge badge-amber">{row.duplicate_status === "conflict" ? "Конфликт ID" : "Дубликат"}</span>}{row.errors.map((item, i) => <p key={`e${i}`} className="validation-error">{item}</p>)}{row.warnings.map((item, i) => <p key={`w${i}`} className="validation-warning">{item}</p>)}</td></tr>)}</tbody></table></div>{!rows.length && <div className="table-empty">Нет строк с выбранными условиями</div>}<div className="table-footer"><span>{rows.length ? `${(previewPage - 1) * 20 + 1}–${Math.min(previewPage * 20, rows.length)} из ${number(rows.length)}` : "0 строк"}</span><div className="pagination"><button disabled={previewPage === 1} onClick={() => setPreviewPage(p => p - 1)}>Назад</button><button disabled={previewPage * 20 >= rows.length} onClick={() => setPreviewPage(p => p + 1)}>Вперёд</button></div></div><div className="confirm-bar"><div><ShieldCheck size={18} /><p>Маскирование может быть неполным.<br /><span>Подозрительные записи попадут в очередь ручной проверки.</span></p></div><button className="button button-primary" disabled={!!busy || mappingDirty || preview.valid_rows === 0} onClick={confirm}>{busy === "confirm" ? <LoaderCircle size={16} className="spin" /> : <CheckCircle2 size={17} />}{busy === "confirm" ? "Сохраняем…" : "Подтвердить импорт"}</button></div></section>
      </>}
    </>}
    <section className="panel history-panel" id="history"><div className="panel-heading"><div><h2>История импорта</h2><p>Все сохранённые партии и результаты обработки</p></div><button className="icon-button" aria-label="Обновить историю импорта" disabled={historyLoading} onClick={loadHistory}><RefreshCw size={16} className={historyLoading ? "spin" : ""} /></button></div>{historyLoading && !batches.length ? <Loading /> : historyError ? <ErrorBox message={historyError} retry={loadHistory} /> : batches.length ? <div className="table-scroll"><table className="data-table"><thead><tr><th>Файл / партия</th><th>Дата загрузки</th><th>Добавлено</th><th>Отклонено</th><th>Дубликаты</th><th>Конфликты</th></tr></thead><tbody>{batches.map(batch => <tr key={batch.id}><td><strong>{batch.filename}</strong><small>Партия #{shortId(batch.id)}</small></td><td>{date(batch.created_at)}</td><td><span className="badge badge-green">{number(batch.accepted)}</span></td><td>{number(batch.rejected)}</td><td>{number(batch.duplicates)}</td><td>{number(batch.conflicts)}</td></tr>)}</tbody></table></div> : <Empty title="Пока нет сохранённых партий" description="После подтверждения импорта здесь появится его результат." />}</section>
  </>;
}
