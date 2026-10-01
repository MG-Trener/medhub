<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ArrowLeft, Mic, Square, Upload, Sparkles, Save, Check, Send, ShieldCheck, RefreshCw, Plus, Trash2, Headphones, Pause, Play, Clock3, FileText, X } from 'lucide-vue-next'
import { api } from './api'
import { useRecorder } from './recorder'
import { liveUploader } from './live-upload'
import { hasConsent, canCapture, visitSeconds, recordingSecondsLeft, formatDuration, bodyMassIndex } from './visit'
import DiagnosisPicker from './DiagnosisPicker.vue'
import ClinicalField from './ClinicalField.vue'
import PagedText from './PagedText.vue'
import Pager from './Pager.vue'
import './consultation.css'

const props = defineProps(['initial', 'patient', 'settings', 'doctor'])
const emit = defineEmits(['back', 'updated', 'open-previous'])
const e = ref(JSON.parse(JSON.stringify(props.initial))), error = ref(''), notice = ref(''), busy = ref(false), dirty = ref(false), tab = ref('transcript')
const rec = useRecorder()
const live = ref(props.initial.live_session || null), liveProgress = ref(null), liveError = ref(''), livePending = ref(0)
let delivery, liveTimer, retryTimer, liveFinishing = false, connectionAlarm = false, liveFinalizing = false
const { devices, selected, recording, paused, recorderError, seconds, audioUrl, audioBlob, level } = rec
const records = ref([]), revisions = ref([]), previous = ref([]), selectedRecord = ref(''), player = ref(null), sourceIndex = ref(-1), stage = ref(''), approvalChecked = ref(false)
const privacyDirty = ref(false), audioReviewed = ref(false), showMaskedAudio = ref(false), leaveDestination = ref(''), leaveDialog = ref(null), audioFileInput = ref(null)
const transcriptDirty = ref(false), transcriptOpen = ref(false)
const serverOffset = ref(props.initial.server_time ? props.initial.server_time - Date.now() / 1000 : 0), now = ref(Date.now() / 1000 + serverOffset.value)
const persisted = computed(() => e.value.persisted !== false)
const readOnly = computed(() => !!e.value.read_only || e.value.can_edit === false)
const processing = computed(() => e.value.status === 'processing')
const reviewed = computed(() => ['approved', 'exported'].includes(e.value.status) && !dirty.value)
const locked = computed(() => busy.value || processing.value || recording.value || !!live.value || readOnly.value)
const canGenerate = computed(() => props.settings.llm_configured && (e.value.transcript.length || Object.keys({ ...fields, ...vitals }).some(key => !key.startsWith('ai_') && e.value.fields[key]?.trim())))
const recordAllowed = computed(() => canCapture(e.value, props.patient, now.value))
const canTranscribe = computed(() => props.settings.asr_configured && hasConsent(props.patient))
const elapsed = computed(() => formatDuration(visitSeconds(e.value, now.value)))
const captureLeft = computed(() => recordingSecondsLeft(e.value, now.value))
const prior = computed(() => previous.value.find(x => x.id === e.value.previous_encounter_id) || previous.value.find(x => ['approved', 'exported'].includes(x.status) && (x.started_at || x.created_at) < (e.value.started_at || e.value.created_at)))
const speakers = computed(() => [...new Set(e.value.transcript.map(s => s.speaker))])
const speakerOptions = computed(() => [...new Set(['SPEAKER_00', 'SPEAKER_01', 'SPEAKER_02', ...speakers.value])])
const audioSource = computed(() => selectedRecord.value ? `/api/v1/encounters/${e.value.id}/recordings/${selectedRecord.value}/audio` : '')
const age = computed(() => { if (!props.patient.birth_date) return '—'; const birth = new Date(props.patient.birth_date), today = new Date(); return today.getFullYear() - birth.getFullYear() - (today < new Date(today.getFullYear(), birth.getMonth(), birth.getDate()) ? 1 : 0) })
const date = value => value ? new Date(value * 1000).toLocaleString('ru-RU') : '—'
const roles = { doctor: 'Врач', patient: 'Пациент', nurse: 'Медсестра', unknown: 'Роль не определена' }
const fields = { complaints: 'Жалобы', anamnesis: 'Анамнез заболевания', life_history: 'Анамнез жизни', allergies: 'Аллергии и реакции', medications: 'Принимаемые лекарства', chronic_conditions: 'Хронические заболевания', family_history: 'Наследственность', operations: 'Операции и перенесённые заболевания', habits: 'Привычки и факторы риска', examination: 'Объективные данные', investigations: 'Исследования и результаты', diagnosis: 'Диагноз врача', recommendations: 'Назначения и рекомендации', follow_up: 'План наблюдения', ai_conclusion: 'Архивная подсказка ИИ', ai_test_recommendations: 'Дополнительные анализы и обследования', ai_diagnosis_variants: 'Предварительные варианты диагноза' }
const vitals = { temperature: 'Температура, °C', blood_pressure: 'АД, мм рт. ст.', pulse: 'Пульс, уд/мин', respiratory_rate: 'ЧДД, в минуту', spo2: 'SpO₂, %', height: 'Рост, см', weight: 'Вес, кг' }
const groups = [{ title: 'Жалобы', keys: ['complaints'] }, { title: 'Анамнез', keys: ['anamnesis', 'life_history', 'allergies', 'medications', 'chronic_conditions', 'family_history', 'operations', 'habits'] }, { title: 'Объективные данные', keys: ['examination'] }, { title: 'Исследования', keys: ['investigations'] }]
const resultGroups = [{ title: 'Диагноз', keys: ['diagnosis'] }, { title: 'Назначения и наблюдение', keys: ['recommendations', 'follow_up'] }]
const workspaceTab = ref('consultation'), clinicalTab = ref(0), fieldIndex = ref(0), aiTab = ref('ai_test_recommendations')
const audioTab = ref('transcript'), segmentPage = ref(0), archivePage = ref(0), audioSettings = ref(false), reviewOpen = ref(false)
const allGroups = [...groups, ...resultGroups]
const activeKeys = computed(() => allGroups[clinicalTab.value].keys)
const activeKey = computed(() => activeKeys.value[fieldIndex.value] || activeKeys.value[0])
const currentSegment = computed(() => e.value.transcript[segmentPage.value])
const maskedSegment = computed(() => e.value.redacted_transcript[segmentPage.value])
const archiveItems = computed(() => [...records.value.map(r => ({ kind: 'audio', ...r })), ...revisions.value.map(r => ({ kind: 'revision', ...r }))])
const archiveItem = computed(() => archiveItems.value[archivePage.value])
const archiveText = computed(() => {
  const item = archiveItem.value
  if (!item) return ''
  return item.kind === 'audio' ? (item.transcript || []).map(s => `${roles[item.speaker_roles?.[s.speaker]] || s.speaker}: ${s.text}`).join('\n\n') : Object.entries(fields).filter(([key]) => item.snapshot?.fields?.[key]).map(([key, label]) => `${label}: ${item.snapshot.fields[key]}`).join('\n\n')
})
const aiNotes = computed(() => [...(e.value.fields.warnings || []), ...(e.value.fields.diagnosis_suggestions || []).map(x => `${x.code} · ${x.name}: ${x.reason}`), e.value.fields.ai_conclusion ? 'Предыдущая версия: ' + e.value.fields.ai_conclusion : ''].filter(Boolean).join('\n\n'))
watch(clinicalTab, () => { fieldIndex.value = 0 })
watch(audioTab, () => { segmentPage.value = 0 })
watch(() => e.value.transcript.length, n => { segmentPage.value = Math.min(segmentPage.value, Math.max(0, n - 1)) })
let historyGuard = false
let autoSaveTimer
watch(() => [e.value.fields, e.value.transcript], () => {
  clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(() => {
    if (dirty.value && !privacyDirty.value && !locked.value && !audioBlob.value) run(save)
  }, 2000)
}, { deep: true })
function browserBack() { history.pushState({ medhubVisit: e.value.id }, ''); requestLeave('patients') }
let pollTimer, clockTimer, captureToken = '', deadlineStopping = false, updateSerial = 0, currentJob = ['running', 'queued'].includes(props.initial.last_job?.state) ? props.initial.last_job.id : null, destroyed = false, returnFocus

async function run(fn) { error.value = ''; notice.value = ''; busy.value = true; try { await fn() } catch (err) { error.value = err.message } finally { busy.value = false } }
function update(value) {
  if (value.server_time) { serverOffset.value = value.server_time - Date.now() / 1000; now.value = value.server_time }
  updateSerial++; e.value = value; dirty.value = false; transcriptDirty.value = false; privacyDirty.value = false; audioReviewed.value = false; approvalChecked.value = false; emit('updated', value)
}
function lifecycleBody() { return { version: e.value.version, ...(persisted.value ? {} : { draft_token: e.value.draft_token }) } }
function changed(key) {
  if (key === 'diagnosis') e.value.fields.diagnosis_code = ''
  dirty.value = true; approvalChecked.value = false
  e.value.fields.reviewed_fields = (e.value.fields.reviewed_fields || []).filter(x => x !== key)
  e.value.fields.sources = (e.value.fields.sources || []).filter(x => x.field !== key)
}
function reviewField(key) { const list = e.value.fields.reviewed_fields || []; e.value.fields.reviewed_fields = list.includes(key) ? list.filter(x => x !== key) : [...list, key]; dirty.value = true; approvalChecked.value = false }
function sources(key) { return e.value.fields.sources?.find(x => x.field === key)?.segments || [] }
async function refreshArchive() {
  if (!persisted.value || readOnly.value) return
  const [audio, history] = await Promise.all([api(`/encounters/${e.value.id}/recordings`), api(`/encounters/${e.value.id}/history`)])
  records.value = audio; revisions.value = history
  if (!selectedRecord.value || !audio.some(x => x.id === selectedRecord.value)) selectedRecord.value = audio.find(x => x.available)?.id || ''
}
async function save() {
  if (privacyDirty.value) throw new Error('Сначала подтвердите изменения маскирования во вкладке «Маскирование»')
  update(await api(`/encounters/${e.value.id}`, { method: persisted.value ? 'PATCH' : 'PUT', body: { ...(persisted.value ? { version: e.value.version } : { draft_token: e.value.draft_token }), fields: e.value.fields, ...(!persisted.value || transcriptDirty.value ? { transcript: e.value.transcript } : {}), speaker_roles: e.value.speaker_roles, previous_encounter_id: e.value.previous_encounter_id } }))
  await refreshArchive(); notice.value = persisted.value ? 'Черновик сохранён. Его можно доработать в разделе «Мои приёмы».' : 'Лист пока пуст. Он сохранится после добавления данных.'
}
async function poll() {
  clearTimeout(pollTimer)
  const serial = updateSerial
  try {
    if (currentJob) {
      const job = await api(`/jobs/${currentJob}`); stage.value = job.stage || job.kind
      if (job.error) error.value = job.error
      if (['done', 'failed'].includes(job.state)) currentJob = null
    }
    const result = await api(`/encounters/${e.value.id}`)
    if (destroyed) return
    if (result.last_job?.error) error.value = result.last_job.error
    if (result.live_session?.state === 'failed') live.value = result.live_session
    if (liveFinalizing && result.status !== 'processing') {
      if (!result.last_job?.error && !recorderError.value && !result.live_session) rec.clearAudio()
      liveFinalizing = false
    }
    // Не перетираем локальные изменения поздним ответом предыдущего запроса.
    if (serial === updateSerial && !dirty.value && !privacyDirty.value) update(result)
    if (result.status === 'processing') pollTimer = setTimeout(poll, 2000)
    else { await refreshArchive(); notice.value = result.last_job?.error ? 'Запись сохранена. Обработка требует повторной попытки.' : 'Обработка завершена. Проверьте расшифровку и лист консультации.' }
  } catch (err) { error.value = err.message; if (!destroyed) pollTimer = setTimeout(poll, 5000) }
}
async function queue(path, body) {
  const result = await api(`/encounters/${e.value.id}/${path}`, { method: 'POST', body })
  currentJob = result.job_id; e.value.persisted = true; e.value.status = 'processing'; stage.value = 'queued'
  clearTimeout(pollTimer); pollTimer = setTimeout(poll, 1000)
}
async function upload(blob) {
  if (!blob?.size) throw new Error('Запись пуста')
  if (!canTranscribe.value) throw new Error('Проверьте настройку ASR и согласие пациента в его карте')
  if (dirty.value) await save()
  const data = new FormData()
  data.append('file', blob, blob.name || 'consultation.' + (blob.type.includes('mp4') ? 'mp4' : 'webm')); data.append('analyze', 'true')
  if (!persisted.value) data.append('draft_token', e.value.draft_token)
  if (captureToken) data.append('capture_token', captureToken)
  await queue('audio', data)
  rec.clearAudio(); captureToken = ''
  notice.value = 'Запись сохранена на сервере. Распознавание и анализ запущены.'
}
async function pollLive() {
  clearTimeout(liveTimer); liveTimer = null
  if (!live.value) return
  const id = live.value.id
  try {
    const result = await api(`/encounters/${e.value.id}/live/${id}`)
    if (live.value?.id !== id || liveFinishing || destroyed) return
    liveProgress.value = result
    if (!dirty.value) { update(result.encounter); e.value.transcript = result.transcript }
    if (result.error) liveError.value = result.error
    if (['done', 'failed'].includes(result.state)) {
      if (result.state === 'done') { live.value = null; liveProgress.value = null; await refreshArchive(); return }
    }
  } catch (err) { if (delivery?.acknowledged) liveError.value = err.message }
  if (!destroyed && live.value) liveTimer = setTimeout(pollLive, 2000)
}
async function completeLive(interrupted = false) {
  if (liveFinishing || !live.value) return
  liveFinishing = true
  try {
    await delivery?.drain()
    livePending.value = delivery?.pending || 0
    const count = delivery?.acknowledged || liveProgress.value?.received || live.value.count || 0
    if (!count) throw new Error('Нет сохранённых фрагментов. Скачайте резервную запись.')
    await queue(`live/${live.value.id}/finish`, { count, interrupted })
    liveFinalizing = true
    clearTimeout(liveTimer); liveTimer = null; clearInterval(retryTimer)
    live.value = null; liveProgress.value = null; liveError.value = ''
    captureToken = ''
    notice.value = 'Фрагменты сохранены. Обрабатываем остаток и выполняем итоговый анализ.'
  } finally { liveFinishing = false }
}
async function startRecording() {
  if (!recordAllowed.value) throw new Error('Новая запись недоступна. Проверьте согласие и время приёма.')
  await rec.primeSounds()
  if (audioBlob.value) throw new Error('Сначала отправьте выбранную запись или удалите её')
  if (dirty.value) await save()
  const lease = await api(`/encounters/${e.value.id}/capture-lease`, { method: 'POST', body: lifecycleBody() })
  captureToken = lease.capture_token
  const sessionId = crypto.randomUUID()
  live.value = { id: sessionId, count: 0 }; liveProgress.value = null; liveError.value = ''; connectionAlarm = false
  delivery = liveUploader(async (blob, sequence) => {
    const form = new FormData(); form.append('file', blob, 'fragment.wav'); form.append('sequence', String(sequence))
    if (e.value.draft_token) form.append('draft_token', e.value.draft_token)
    form.append('capture_token', captureToken)
    const result = await api(`/encounters/${e.value.id}/live/${sessionId}/parts`, { method: 'POST', body: form, signal: AbortSignal.timeout(30000) })
    e.value.persisted = true; connectionAlarm = false; liveError.value = ''
    if (!liveTimer) liveTimer = setTimeout(pollLive, 300)
    return result
  }, message => {
    liveError.value = message + ' Фрагменты остаются в браузере; отправка будет повторена.'
    if (!connectionAlarm) { rec.alarm(); connectionAlarm = true }
  })
  try {
    await rec.start({ onChunk: blob => { delivery.add(blob); livePending.value = delivery.pending },
      onInterrupted: () => { void run(() => completeLive(true)) } })
  } catch (err) { live.value = null; throw err }
  workspaceTab.value = 'audio'; audioTab.value = 'transcript'; segmentPage.value = Math.max(0, e.value.transcript.length - 1)
  transcriptOpen.value = true
  retryTimer = setInterval(() => { if (delivery?.pending) void delivery.retry(); livePending.value = delivery?.pending || 0 }, 5000)
  if (Date.now() / 1000 + serverOffset.value >= e.value.recording_deadline) {
    await rec.stop()
    if (delivery.pending || delivery.acknowledged) await completeLive(true)
    else { live.value = null; clearInterval(retryTimer); clearTimeout(liveTimer); liveTimer = null }
    throw new Error('Время для записи истекло во время запроса микрофона. Резервную запись можно скачать.')
  }
}
async function finishDialogue() { const blob = await rec.stop(); if (live.value) await completeLive(!!recorderError.value); else await upload(blob) }
function chooseFile(event) {
  const file = event.target.files?.[0]; event.target.value = ''; if (!file || !recordAllowed.value) return
  if (file.size > 80 * 1024 * 1024) { error.value = 'Максимальный размер файла — 80 МБ'; return }
  const extensions = { mp3: 'audio/mpeg', wav: 'audio/wav', m4a: 'audio/mp4', mp4: 'audio/mp4', webm: 'audio/webm', ogg: 'audio/ogg', flac: 'audio/flac' }
  const mime = extensions[file.name.split('.').pop().toLowerCase()]
  if (!mime) { error.value = 'Выберите WAV, MP3, M4A, MP4, WebM, OGG или FLAC'; return }
  captureToken = ''; rec.setAudio(new Blob([file], { type: mime })); notice.value = `Выбрано: ${file.name}. Нажмите «Распознать и заполнить».`
}
async function preserveChanges() {
  if (privacyDirty.value) await privacy()
  if (recording.value) await finishDialogue()
  else if (live.value) await completeLive(!!recorderError.value)
  else if (audioBlob.value) await upload(audioBlob.value)
  if (dirty.value) await save()
}
async function finishVisit() {
  await preserveChanges()
  update(await api(`/encounters/${e.value.id}/finish`, { method: 'POST', body: lifecycleBody() }))
  if (e.value.discarded) { emit('back', { encounter: e.value, action: 'finish', discarded: true, destination: 'patient' }); return }
  notice.value = 'Приём завершён. Новая запись закрыта; лист можно доработать и проверить позже.'
}
async function resumeVisit() { update(await api(`/encounters/${e.value.id}/resume`, { method: 'POST', body: lifecycleBody() })); notice.value = 'Приём продолжен. Окно записи отсчитывается от первоначального начала.' }
async function generate(target = 'all') { if (privacyDirty.value) throw new Error('Подтвердите изменения маскирования'); if (dirty.value) await save(); await queue('generate', { version: e.value.version, target }) }
async function retryRecording(record) {
  if (privacyDirty.value) throw new Error('Сначала подтвердите маскирование')
  if (dirty.value) await save()
  await queue(`recordings/${record.id}/transcribe`, { version: e.value.version, analyze: true })
}
async function privacy() {
  if (dirty.value) throw new Error('Сначала сохраните правки расшифровки и полей')
  update(await api(`/encounters/${e.value.id}/privacy-review`, { method: 'POST', body: { version: e.value.version, segments: e.value.redacted_transcript } })); notice.value = 'Маскирование проверено'
}
async function approve() {
  if (!approvalChecked.value) throw new Error('Подтвердите проверку результата')
  if (dirty.value) await save()
  if (!persisted.value) throw new Error('Добавьте сведения о консультации')
  if (!e.value.ended_at) await finishVisit()
  update(await api(`/encounters/${e.value.id}/approve`, { method: 'POST', body: { version: e.value.version } })); await refreshArchive(); notice.value = 'Проверено врачом. Результат доступен МИС через API.'
}
async function rejectDraft() {
  if (!window.confirm('Очистить поля черновика? Сохранённые аудио, расшифровка и предыдущие версии останутся в архиве.')) return
  for (const key of Object.keys(e.value.fields)) { if (['visit_type', 'visit_format'].includes(key)) continue; e.value.fields[key] = Array.isArray(e.value.fields[key]) ? [] : '' }
  dirty.value = true; await save()
}
function selectDiagnosis(item) { changed('diagnosis'); e.value.fields.diagnosis_code = item.code; e.value.fields.diagnosis = item.name }
async function showSource(index) {
  workspaceTab.value = 'audio'; audioTab.value = 'transcript'; segmentPage.value = index
  transcriptOpen.value = true
  tab.value = 'transcript'; sourceIndex.value = index
  const time = e.value.transcript[index]?.start
  const record = records.value.find(record => record.available && time >= (record.timeline_offset || 0) &&
    (!record.duration || time < (record.timeline_offset || 0) + record.duration))
  if (record) selectedRecord.value = record.id
  await nextTick(); document.getElementById('segment-' + index)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  if (player.value && record && Number.isFinite(time)) player.value.currentTime = Math.max(0, time - (record.timeline_offset || 0))
}
function transcriptChanged() { dirty.value = true; transcriptDirty.value = true; approvalChecked.value = false; e.value.fields.reviewed_fields = [] }
function addSegment() { e.value.transcript.push({ speaker: 'SPEAKER_00', start: 0, end: 0, text: '' }); e.value.speaker_roles.SPEAKER_00 ||= 'unknown'; transcriptChanged() }
function leave(action, destination) {
  leaveDestination.value = ''
  emit('back', { encounter: e.value, action, discarded: !!e.value.discarded, destination })
}
async function requestLeave(destination = 'patient') {
  if (readOnly.value || (e.value.ended_at && !dirty.value && !privacyDirty.value && !audioBlob.value)) { leave('back', destination); return }
  leaveDestination.value = destination; returnFocus = document.activeElement
  await nextTick(); leaveDialog.value?.querySelector('button')?.focus()
}
function cancelLeave() { leaveDestination.value = ''; returnFocus?.focus() }
async function confirmLeave(action) {
  const destination = leaveDestination.value
  await preserveChanges()
  if (!e.value.ended_at) update(await api(`/encounters/${e.value.id}/${action === 'pause' ? 'pause' : 'finish'}`, { method: 'POST', body: lifecycleBody() }))
  leave(action, destination)
}
function trapFocus(event) {
  if (event.key !== 'Tab') return
  const buttons = [...leaveDialog.value.querySelectorAll('button:not(:disabled)')], first = buttons[0], last = buttons.at(-1)
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
const unload = event => { if ((!readOnly.value && !e.value.ended_at) || recording.value || audioBlob.value || dirty.value || privacyDirty.value) { event.preventDefault(); event.returnValue = '' } }
defineExpose({ requestLeave })
onMounted(async () => {
  clockTimer = setInterval(() => {
    now.value = Date.now() / 1000 + serverOffset.value
    if (recording.value && captureLeft.value <= 0 && !deadlineStopping && !busy.value) {
      deadlineStopping = true
      run(async () => { await finishDialogue(); notice.value = '15 минут истекли. Запись остановлена и отправлена на обработку.' }).finally(() => { deadlineStopping = false })
    }
  }, 500)
  window.addEventListener('beforeunload', unload)
  if (!readOnly.value && !e.value.ended_at) { history.pushState({ medhubVisit: e.value.id }, ''); historyGuard = true; window.addEventListener('popstate', browserBack) }
  if (live.value) liveTimer = setTimeout(pollLive, 100)
  try { await refreshArchive(); previous.value = (await api(`/patients/${props.patient.id}/encounters`)).filter(x => x.id !== e.value.id); if (processing.value) poll() } catch (err) { error.value = err.message }
})
onBeforeUnmount(() => { destroyed = true; clearTimeout(autoSaveTimer); clearTimeout(liveTimer); clearInterval(retryTimer); clearTimeout(pollTimer); clearInterval(clockTimer); window.removeEventListener('beforeunload', unload); if (historyGuard) window.removeEventListener('popstate', browserBack) })
</script>

<template>
<section class="visit-screen">
  <header class="visit-header">
    <button class="icon-button" aria-label="К карте пациента" @click="requestLeave()"><ArrowLeft :size="18"/></button>
    <div class="visit-identity"><strong>{{ patient.name }}</strong><small>{{ age }} лет · ИИН ••••••••{{ patient.iin?.slice(-4) }} · {{ date(e.started_at || e.created_at) }}</small></div>
    <span class="badge">{{ e.ended_at ? 'Завершён' : e.paused_at ? 'Пауза приёма' : 'Приём идёт' }} · {{ elapsed }}</span>
    <a v-if="persisted && !dirty && !processing" class="secondary" :href="'/api/v1/encounters/'+e.id+'/pdf'" target="_blank" rel="noopener">PDF</a>
    <button v-if="!readOnly && e.paused_at && !e.ended_at" class="secondary" :disabled="busy || processing" @click="run(resumeVisit)">Продолжить</button>
    <button v-if="!readOnly && !e.ended_at" class="primary" :disabled="busy" @click="run(finishVisit)">Завершить приём</button>
  </header>
  <div class="visit-controls">
    <nav class="workspace-tabs" aria-label="Рабочая область"><button :class="{ active: workspaceTab === 'consultation' }" @click="workspaceTab = 'consultation'">Консультация</button><button :class="{ active: workspaceTab === 'audio' }" @click="workspaceTab = 'audio'">Аудио и расшифровка · {{ e.transcript.length }}</button></nav>
    <span class="hint">{{ hasConsent(patient) ? 'Согласие получено' : 'Без согласия · вручную' }}</span>
    <template v-if="!readOnly"><span v-if="recording" class="recording-status">{{ paused ? 'Пауза' : 'Запись' }} {{ formatDuration(seconds) }}</span><button v-if="recording" class="secondary" :disabled="busy" @click="rec.pause">{{ paused ? 'Продолжить' : 'Пауза' }}</button><button v-if="recording" class="primary" :disabled="busy" @click="run(finishDialogue)">Остановить запись</button><button v-else-if="recordAllowed" class="secondary" :disabled="locked || !!audioBlob" @click="audioSettings = true">Начать запись</button></template>
  </div>
  <div v-if="error || recorderError || notice || processing || privacyDirty" class="compact-feedback" :class="{ error: error || recorderError }" role="status">{{ error || recorderError || (privacyDirty ? 'Подтвердите маскирование перед правкой листа.' : processing ? 'Обработка… Предыдущие данные сохранены.' : notice) }}</div>
  <div v-show="workspaceTab === 'consultation'" class="visit-columns">
    <section class="clinical-pane panel" :inert="privacyDirty || undefined">
      <div class="pane-heading"><h2>Данные приёма</h2><span class="badge">{{ reviewed ? 'Проверено врачом' : 'Черновик' }}</span><button class="text-button" @click="reviewOpen = true">Проверка и параметры</button></div>
      <nav class="workspace-tabs clinical-nav" aria-label="Раздел медицинской записи"><button v-for="(group, i) in allGroups" :key="group.title" :class="{ active: clinicalTab === i }" @click="clinicalTab = i">{{ group.title }}</button></nav>
      <label v-if="activeKeys.length > 1" class="field-picker">Поле<select v-model="fieldIndex"><option v-for="(key, i) in activeKeys" :key="key" :value="i">{{ fields[key] }}{{ e.fields[key] ? '' : ' · не уточнено' }}</option></select></label>
      <DiagnosisPicker v-if="activeKey === 'diagnosis'" :code="e.fields.diagnosis_code" :disabled="locked" @select="selectDiagnosis"/>
      <ClinicalField :key="activeKey" v-model="e.fields[activeKey]" :name="activeKey" :label="fields[activeKey]" :disabled="locked" :sources="sources(activeKey)" :reviewed="reviewed || e.fields.reviewed_fields?.includes(activeKey)" @update:model-value="changed(activeKey)" @review="reviewField(activeKey)"/>
      <div v-if="activeKey === 'examination'" class="compact-vitals"><label v-for="(label,key) in vitals" :key="key">{{ label }}<input v-model="e.fields[key]" :disabled="locked" placeholder="Не измерено" @input="changed(key)"></label><label>ИМТ<input :value="bodyMassIndex(e.fields)" readonly placeholder="—"></label></div>
    </section>
    <section class="ai-pane panel" aria-label="ИИ-помощник">
      <div class="pane-heading"><h2><Sparkles :size="18"/> ИИ-помощник</h2><button class="secondary regenerate-all" :disabled="locked || !canGenerate || readOnly" @click="run(() => generate())"><RefreshCw :size="15"/>{{ processing ? 'Перегенерация…' : 'Перегенерировать все ответы с учётом правок' }}</button></div>
      <p class="hint ai-label">Предложения ИИ · проверить врачу · не входят в PDF и МИС</p>
      <nav class="workspace-tabs" aria-label="Ответы ИИ"><button :class="{ active: aiTab === 'ai_test_recommendations' }" @click="aiTab = 'ai_test_recommendations'">Обследования</button><button :class="{ active: aiTab === 'ai_diagnosis_variants' }" @click="aiTab = 'ai_diagnosis_variants'">Диагнозы</button><button :class="{ active: aiTab === 'notes' }" @click="aiTab = 'notes'">Уточнить</button></nav>
      <PagedText v-if="aiTab !== 'notes'" :key="aiTab" v-model="e.fields[aiTab]" :label="fields[aiTab]" :disabled="locked" placeholder="Ответы появятся после анализа. Требуется проверка врача." @input="changed(aiTab)"/>
      <PagedText v-else :model-value="aiNotes" label="Уточнения и источники ИИ" disabled placeholder="Нет уточнений"/>
    </section>
  </div>
  <section v-show="workspaceTab === 'audio'" class="panel audio-pane">
    <div class="pane-heading"><h2>Аудио и расшифровка</h2><button class="secondary" @click="audioSettings = true">Запись и микрофон</button></div>
    <nav class="workspace-tabs" aria-label="Данные аудио"><button v-for="(label,key) in {transcript:'Расшифровка',privacy:'Маскирование',archive:'Архив'}" :key="key" :class="{ active: audioTab === key }" @click="audioTab = key">{{ label }}</button></nav>
    <div v-if="audioSource" class="compact-player"><select v-model="selectedRecord" aria-label="Сохранённая запись"><option v-for="r in records.filter(x => x.available)" :key="r.id" :value="r.id">{{ date(r.created_at) }}</option></select><audio ref="player" :src="audioSource" controls preload="metadata"/></div>
    <template v-if="audioTab === 'transcript'">
      <div class="pane-heading"><Pager v-model="segmentPage" :total="e.transcript.length" label="Реплика"/><button class="text-button" :disabled="locked || privacyDirty" @click="addSegment(); segmentPage = e.transcript.length - 1">Добавить текст</button></div>
      <template v-if="currentSegment"><div class="segment-meta"><select v-model="currentSegment.speaker" aria-label="Говорящий" :disabled="locked || privacyDirty" @change="transcriptChanged"><option v-for="sp in speakerOptions" :key="sp" :value="sp">{{ sp }}</option></select><select v-model="e.speaker_roles[currentSegment.speaker]" aria-label="Роль участника" :disabled="locked || privacyDirty" @change="transcriptChanged"><option v-for="(label,role) in roles" :key="role" :value="role">{{ label }}</option></select><button class="text-button" @click="showSource(segmentPage)">{{ formatDuration(currentSegment.start) }}</button><button class="icon-button" :disabled="locked || privacyDirty" aria-label="Удалить текущую реплику" @click="e.transcript.splice(segmentPage,1); e.fields.sources=[]; transcriptChanged()"><Trash2 :size="16"/></button></div><PagedText :key="segmentPage" v-model="currentSegment.text" label="Текст реплики" :disabled="locked || privacyDirty" @input="transcriptChanged"/></template>
      <p v-else class="empty">Расшифровка появится после распознавания записи.</p>
    </template>
    <template v-else-if="audioTab === 'privacy'"><p class="hint">Проверьте маскирование персональных данных. Сначала сохраните правки листа.</p><Pager v-model="segmentPage" :total="e.redacted_transcript.length" label="Маскированная реплика"/><PagedText v-if="maskedSegment" :key="segmentPage" v-model="maskedSegment.text" label="Обезличенный текст" :disabled="locked || dirty" @input="privacyDirty = true"/><div class="inline-actions"><button class="secondary" :disabled="locked || dirty || !e.redacted_transcript.length" @click="run(privacy)">Подтвердить маскирование</button><button class="text-button" :disabled="locked || dirty || privacyDirty || !maskedSegment || !hasConsent(patient)" @click="run(() => queue('mute-audio', {version:e.version,segment_indices:[segmentPage]}))">Заглушить фрагмент</button><button class="text-button" @click="showMaskedAudio = !showMaskedAudio">Копия аудио</button></div><div v-if="showMaskedAudio" class="compact-player"><audio :key="e.version" :src="'/api/v1/encounters/'+e.id+'/masked-audio'" controls/><label class="check"><input v-model="audioReviewed" type="checkbox">Проверено отсутствие персональных данных</label><button v-if="settings.cloud_asr_configured" :disabled="locked || !audioReviewed || !e.privacy_reviewed || !hasConsent(patient)" @click="run(() => queue('cloud-asr',{version:e.version,audio_reviewed:true}))">Уточнить ASR</button></div></template>
    <template v-else><Pager v-model="archivePage" :total="archiveItems.length" label="Документ архива"/><div v-if="archiveItem" class="pane-heading"><span>{{ archiveItem.kind === 'audio' ? 'Аудио' : 'Версия ' + archiveItem.version }} · {{ date(archiveItem.created_at) }}</span><button v-if="archiveItem.kind === 'audio'" class="secondary" :disabled="locked || !archiveItem.available || !canTranscribe" @click="run(() => retryRecording(archiveItem))">Распознать повторно</button></div><PagedText :model-value="archiveText" label="Содержимое архива" disabled placeholder="Архив пока пуст"/></template>
  </section>
  <footer class="visit-footer"><span class="hint">{{ dirty || privacyDirty ? 'Есть несохранённые правки' : 'Нет несохранённых правок' }}</span><button class="secondary" :disabled="locked || privacyDirty || readOnly || (reviewed && !dirty)" @click="run(save)"><Save :size="15"/>Сохранить черновик</button><button class="primary" :disabled="locked || readOnly" @click="reviewOpen = true">{{ reviewed ? 'Результат проверен' : 'Проверить запись' }}</button></footer>

  <div v-if="audioSettings" class="modal-backdrop" @click.self="audioSettings = false" @keydown.esc="audioSettings = false"><section class="modal compact-modal" role="dialog" aria-modal="true" aria-label="Запись и микрофон"><div class="pane-heading"><h2>Запись и микрофон</h2><button class="icon-button" aria-label="Закрыть" @click="audioSettings=false"><X/></button></div><p class="hint">Перед записью попросите участников не называть ФИО, ИИН, адрес и телефон. Исходная запись остаётся в доверенном контуре. Проверьте обезличивание перед внешним API. Требуется согласие пациента.</p><label>Устройство<select v-model="selected" :disabled="recording || busy" @change="rec.saveDevice"><option value="">Системный микрофон</option><option v-for="d in devices" :key="d.deviceId" :value="d.deviceId">{{ d.label || 'Микрофон' }}</option></select></label><button class="text-button" :disabled="recording || busy" @click="run(rec.discover)">Обновить список микрофонов</button><p class="hint">Новая запись: {{ formatDuration(captureLeft) }}. Лимит файла — 80 МБ. Два восходящих тона — начало, нисходящих — окончание, повторяющийся сигнал — обрыв.</p><button v-if="recordAllowed && !recording" class="primary" :disabled="locked || !!audioBlob" @click="run(async () => { await startRecording(); if(recording) audioSettings=false })">Начать запись</button><label v-if="recordAllowed" class="audio-file-label">Загрузить аудио<input type="file" accept=".wav,.mp3,.m4a,.mp4,.webm,.ogg,.flac" :disabled="locked || !!audioBlob" @change="chooseFile"></label><div v-if="audioUrl && !recording" class="uploaded-audio"><audio :src="audioUrl" controls/><button class="primary" :disabled="busy || processing || !canTranscribe || !!e.ended_at" @click="run(() => live ? completeLive(!!recorderError) : upload(audioBlob))">Распознать и заполнить</button><a :href="audioUrl" download="consultation-audio">Скачать запись</a><button class="text-button" :disabled="locked" @click="rec.clearAudio(); captureToken=''">Удалить выбранную запись</button></div><div v-if="live || liveProgress"><p class="hint">Сохранено {{ liveProgress?.received || delivery?.acknowledged || 0 }} · ожидают {{ livePending }}</p><a v-if="live" :href="'/api/v1/encounters/'+e.id+'/live/'+live.id+'/audio'" download>Скачать фрагменты</a><button v-if="!recording" :disabled="busy || processing" @click="run(() => completeLive(true))">Обработать сохранённое</button></div><p v-if="error || liveError || recorderError" class="error">{{ error || liveError || recorderError }}</p></section></div>

  <div v-if="reviewOpen" class="modal-backdrop" @click.self="reviewOpen=false" @keydown.esc="reviewOpen=false"><section class="modal compact-modal" role="dialog" aria-modal="true" aria-label="Проверка записи"><div class="pane-heading"><h2>Проверка записи</h2><button class="icon-button" aria-label="Закрыть" @click="reviewOpen=false"><X/></button></div><div class="form-grid"><label>Вид<select v-model="e.fields.visit_type" :disabled="locked" @change="dirty=true"><option value="primary">Первичная</option><option value="repeat">Повторная</option></select></label><label>Формат<select v-model="e.fields.visit_format" :disabled="locked" @change="dirty=true"><option value="in_person">Очная</option><option value="remote">Онлайн</option></select></label></div><label v-if="e.fields.visit_type === 'repeat'">Предыдущий приём<select v-model="e.previous_encounter_id" :disabled="locked" @change="dirty=true"><option :value="null">Без привязки</option><option v-for="item in previous" :key="item.id" :value="item.id">{{ date(item.started_at || item.created_at) }}</option></select></label><button v-if="e.previous_encounter_id" class="text-button" @click="reviewOpen=false; requestLeave('previous:'+e.previous_encounter_id)">Открыть предыдущий приём</button><div class="review-grid"><button v-for="(group,i) in allGroups" :key="group.title" class="secondary" @click="clinicalTab=i; workspaceTab='consultation'; reviewOpen=false">{{ group.title }} · {{ group.keys.filter(k => e.fields[k]).length }}/{{ group.keys.length }}</button></div><label v-if="!reviewed" class="check"><input v-model="approvalChecked" type="checkbox" :disabled="locked">Я проверил данные приёма, диагноз и назначения.</label><button v-if="!reviewed" class="primary" :disabled="locked || readOnly || !approvalChecked || !!audioBlob" @click="run(async () => { await approve(); reviewOpen=false })">Подтвердить результат</button><button v-if="reviewed" class="secondary" :disabled="locked || !settings.mis_configured" @click="run(() => queue('send-to-mis',{version:e.version}))">Отправить в МИС</button><button v-if="!reviewed" class="text-button" :disabled="locked || readOnly" @click="run(rejectDraft)">Очистить поля и заполнить вручную</button><p v-if="error" class="error">{{ error }}</p></section></div>

  <div v-if="leaveDestination" class="modal-backdrop" @click.self="!busy && cancelLeave()" @keydown.esc="!busy && cancelLeave()" @keydown="trapFocus"><section ref="leaveDialog" class="modal compact-modal" role="dialog" aria-modal="true" aria-labelledby="leave-title"><div class="pane-heading"><h2 id="leave-title">{{ e.ended_at ? 'Сохранить изменения?' : 'Приём ещё идёт' }}</h2></div><p>{{ e.ended_at ? 'Сохраните правки перед выходом.' : 'Вы собираетесь покинуть текущий приём. Сохраните данные и приостановите или завершите приём.' }}</p><p v-if="recording" class="hint">Запись продолжится, пока вы не подтвердите выход.</p><p v-if="error" class="error">{{ error }}</p><div class="leave-actions"><button class="primary" :disabled="busy" @click="cancelLeave">Остаться на приёме</button><button v-if="!e.ended_at" class="secondary" :disabled="busy" @click="run(() => confirmLeave('pause'))">Приостановить и выйти</button><button class="secondary" :disabled="busy" @click="run(() => confirmLeave('interrupt'))">{{ e.ended_at ? 'Сохранить и выйти' : 'Завершить приём и выйти' }}</button></div></section></div>
</section>
</template>
