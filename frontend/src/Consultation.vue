<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ArrowLeft, Mic, Square, Upload, Sparkles, Save, Check, Send, ShieldCheck, FileText, RefreshCw, Plus, Trash2, Headphones } from 'lucide-vue-next'
import { api } from './api'
import { useRecorder } from './recorder'
const props = defineProps(['initial', 'patient', 'settings'])
const emit = defineEmits(['back', 'updated'])
const e = ref(JSON.parse(JSON.stringify(props.initial))), error = ref(''), notice = ref(''), busy = ref(false), dirty = ref(false), tab = ref('transcript')
const rec = useRecorder()
const { devices, selected, recording, seconds, audioUrl, audioBlob, level } = rec
const processing = computed(() => e.value.status === 'processing')
const showMaskedAudio = ref(false), audioReviewed = ref(false), privacyDirty = ref(false)
const locked = computed(() => busy.value || processing.value || recording.value)
const canRecord = computed(() => props.patient.recording_consent && e.value.recording_consent)
const openai = computed(() => props.settings.asr_provider === 'openai')
const canTranscribe = computed(() => props.settings.asr_configured && (!openai.value || props.patient.openai_audio_consent))
const speakerOptions = computed(() => [...new Set(['SPEAKER_00', 'SPEAKER_01', 'SPEAKER_02', ...speakers.value])])
const clock = computed(() => `${Math.floor(seconds.value / 60).toString().padStart(2, '0')}:${(seconds.value % 60).toString().padStart(2, '0')}`)
const fieldNames = { complaints: 'Жалобы', anamnesis: 'Анамнез', examination: 'Объективный статус', diagnosis: 'Диагноз врача', recommendations: 'Рекомендации и назначения' }
const roles = { doctor: 'Врач', patient: 'Пациент', nurse: 'Медсестра', unknown: 'Роль не определена' }
const speakers = computed(() => [...new Set(e.value.transcript.map(s => s.speaker))])
let timer, currentJob = null, destroyed = false
async function run(fn) { error.value = ''; notice.value = ''; busy.value = true; try { await fn() } catch (err) { error.value = err.message } finally { busy.value = false } }
function update(value) { e.value = value; dirty.value = false; privacyDirty.value = false; audioReviewed.value = false; emit('updated', value) }
async function save() {
  update(await api(`/encounters/${e.value.id}`, { method: 'PATCH', body: { version: e.value.version, fields: e.value.fields, transcript: e.value.transcript, speaker_roles: e.value.speaker_roles } }))
  notice.value = 'Изменения сохранены'
}
async function poll() {
  try {
    if (currentJob) {
      const job = await api(`/jobs/${currentJob}`)
      if (job.state === 'failed') error.value = job.error
      if (job.state === 'done' && job.kind === 'transcribe') rec.clearAudio()
      if (['failed', 'done'].includes(job.state)) currentJob = null
    }
    const result = await api(`/encounters/${e.value.id}`)
    if (result.last_job?.state === 'failed') error.value = result.last_job.error
    if (!destroyed) { update(result); if (result.status === 'processing') timer = setTimeout(poll, 2000) }
  } catch (err) { error.value = err.message; if (!destroyed) timer = setTimeout(poll, 5000) }
}
async function queue(path, body) {
  const result = await api(`/encounters/${e.value.id}/${path}`, { method: 'POST', body })
  currentJob = result.job_id; e.value.status = 'processing'; timer = setTimeout(poll, 1500)
}
async function upload(blob) {
  if (!blob) return
  if (dirty.value) await save()
  const data = new FormData(); data.append('file', blob, 'consultation.' + (blob.type.includes('mp4') ? 'mp4' : 'webm'))
  await queue('audio', data)
}
async function generate() {
  if (privacyDirty.value) throw new Error('Подтвердите изменения маскирования перед генерацией')
  if (dirty.value) await save()
  await queue('generate', { version: e.value.version })
}
async function privacy() {
  if (dirty.value) throw new Error('Сначала сохраните расшифровку, затем проверьте её обезличенную версию')
  update(await api(`/encounters/${e.value.id}/privacy-review`, { method: 'POST', body: { version: e.value.version, segments: e.value.redacted_transcript } }))
  notice.value = 'Проверка маскирования подтверждена'
}
async function approve() {
  if (dirty.value) await save()
  update(await api(`/encounters/${e.value.id}/approve`, { method: 'POST', body: { version: e.value.version } }))
  notice.value = 'Лист подтверждён и доступен МИС через API'
}
function back() {
  if (recording.value) { error.value = 'Остановите запись перед выходом'; return }
  if ((dirty.value || privacyDirty.value || audioBlob.value) && !window.confirm('Есть несохранённые изменения или запись. Выйти без сохранения?')) return
  emit('back')
}
function addSegment() { e.value.transcript.push({ speaker: 'SPEAKER_00', start: 0, end: 0, text: '' }); e.value.speaker_roles.SPEAKER_00 ||= 'unknown'; dirty.value = true }
const unload = event => { if (dirty.value) { event.preventDefault(); event.returnValue = '' } }
onMounted(() => { if (processing.value) poll(); window.addEventListener('beforeunload', unload) })
onBeforeUnmount(() => { destroyed = true; clearTimeout(timer); window.removeEventListener('beforeunload', unload) })
</script>

<template>
  <button class="text-button back" @click="back"><ArrowLeft :size="16"/>К карте пациента</button>
  <div class="page-heading consultation-heading"><div><span class="eyebrow">КОНСУЛЬТАЦИЯ · {{ e.id.slice(0, 8) }}</span><h1>{{ patient.name }}</h1><p class="muted">{{ patient.birth_date }} · ИИН {{ patient.iin }}</p></div><span class="badge" :class="e.status">{{ { draft: 'Черновик', ready: 'Проверьте результат', processing: 'Обработка', approved: 'Подтверждён', exported: 'Передан в МИС' }[e.status] }}</span></div>
  <div v-if="error" class="alert error" role="alert">{{ error }}</div><div v-if="notice" class="alert success" role="status">{{ notice }}</div>
  <div v-if="!canRecord" class="alert warning"><ShieldCheck :size="20"/>Пациент отказался от записи. Заполните лист консультации вручную — он также будет доступен МИС после подтверждения.</div>
  <section v-else class="recorder-panel"><div class="recorder-title"><div class="mic-orb" :class="{ recording }"><Mic :size="24"/></div><div><h3>{{ recording ? 'Идёт запись разговора' : 'Запись консультации' }}</h3><span class="muted">{{ recording ? 'Микрофон включён · до 60 минут' : (openai ? 'Распознавание в OpenAI · исходная запись' : 'Распознавание на настроенном сервере') }}</span></div></div><div class="record-wave" aria-hidden="true"><i v-for="n in 18" :key="n" :style="{ height: (recording ? 5 + level * (15 + n % 5 * 13) : 4 + n % 4 * 3) + 'px' }"></i></div><span class="record-clock">{{ clock }}</span><button v-if="recording" class="danger" @click="rec.stop"><Square :size="16"/>Остановить</button><button v-else class="primary" :disabled="locked" @click="run(rec.start)"><Mic :size="17"/>{{ audioBlob ? 'Перезаписать' : 'Начать запись' }}</button>
    <div class="microphone-row"><button class="text-button" :disabled="recording" @click="run(rec.discover)"><Headphones :size="15"/>Разрешить микрофон</button><select v-model="selected" aria-label="Источник микрофона" :disabled="recording" @change="rec.saveDevice"><option value="">Системный микрофон</option><option v-for="d in devices" :key="d.deviceId" :value="d.deviceId">{{ d.label || 'Микрофон' }}</option></select><span class="hint">Выбор сохраняется на этом устройстве</span></div>
    <div v-if="audioUrl" class="audio-preview"><audio :src="audioUrl" controls/><button class="secondary" :disabled="locked || !canTranscribe" @click="run(() => upload(audioBlob))"><Upload :size="16"/>Распознать запись</button></div>
  </section>
  <div v-if="canRecord && openai" class="alert warning"><ShieldCheck :size="20"/><div>OpenAI получит исходную запись. Персональные данные маскируются после распознавания.<p v-if="!patient.openai_audio_consent">Для отправки отметьте отдельное согласие пациента на OpenAI в его карте.</p><p v-if="!settings.asr_configured">API-ключ OpenAI ещё не настроен администратором.</p></div></div>
  <div v-if="processing" class="alert processing-alert"><RefreshCw :size="19" class="spin"/>Обработка на сервере. Можно вернуться к карте пациента — задание сохранено в очереди.</div>
  <div class="consultation-grid">
    <section class="panel transcript-panel"><div class="section-title"><h3>Разговор</h3><span class="hint">{{ e.transcript.length }} фрагм.</span></div><div class="tabs compact-tabs"><button :class="{ active: tab === 'transcript' }" @click="tab = 'transcript'">Расшифровка</button><button :class="{ active: tab === 'privacy' }" @click="tab = 'privacy'"><ShieldCheck :size="15"/>Маскирование</button></div>
      <template v-if="tab === 'transcript'">
        <div v-if="speakers.length" class="speaker-roles"><label v-for="s in speakers" :key="s"><span>{{ s.replace('SPEAKER_', 'Говорящий ') }}</span><select v-model="e.speaker_roles[s]" :disabled="locked" @change="dirty = true"><option v-for="(label, role) in roles" :key="role" :value="role">{{ label }}</option></select></label></div>
        <div v-if="!e.transcript.length" class="empty"><Mic :size="35"/><h3>Здесь появится разговор</h3><p>После записи распознаем речь и разделим голоса. Роли определит LLM, а вы сможете их уточнить.</p><button class="text-button" :disabled="locked" @click="addSegment"><Plus :size="15"/>Внести текст вручную</button></div>
        <div class="segments"><article v-for="(s, i) in e.transcript" :key="i" class="segment"><div class="segment-meta"><span class="speaker-dot" :class="e.speaker_roles[s.speaker]"></span><select v-model="s.speaker" aria-label="Говорящий" :disabled="locked" @change="dirty = true"><option v-for="speaker in speakerOptions" :key="speaker" :value="speaker">Говорящий {{ Number(speaker.slice(-2)) + 1 }} · {{ roles[e.speaker_roles[speaker]] || 'Роль не определена' }}</option></select><span>{{ Math.floor(s.start / 60) }}:{{ Math.floor(s.start % 60).toString().padStart(2, '0') }}</span><button class="icon-button" aria-label="Удалить фрагмент" :disabled="locked" @click="e.transcript.splice(i, 1); dirty = true"><Trash2 :size="13"/></button></div><textarea v-model="s.text" aria-label="Текст реплики" :disabled="locked" rows="3" @input="dirty = true"></textarea></article></div>
        <button v-if="e.transcript.length" class="text-button add-segment" :disabled="locked" @click="addSegment"><Plus :size="15"/>Добавить реплику</button>
      </template>
      <template v-else><div class="privacy-note"><ShieldCheck :size="20"/><p>Проверьте имена, адреса, телефоны и другие идентификаторы. Автоматическое маскирование может пропустить данные. Изменения ниже касаются только текста для модели.</p></div><div v-if="dirty" class="alert warning">Сохраните расшифровку перед проверкой маскирования.</div><div v-for="(s, i) in e.redacted_transcript" :key="i" class="segment"><span class="hint">{{ s.speaker }}</span><textarea v-model="s.text" aria-label="Обезличенная реплика" :disabled="locked || dirty" rows="3" @input="privacyDirty = true"></textarea><button v-if="canRecord" class="text-button" :disabled="locked || dirty || privacyDirty" @click="run(() => queue('mute-audio', { version: e.version, segment_indices: [i] }))">Заглушить эту реплику в аудио</button></div><p v-if="!e.redacted_transcript.length" class="empty">Сначала сохраните расшифровку.</p><button class="secondary full" :disabled="locked || dirty || !e.redacted_transcript.length" @click="run(privacy)"><Check :size="16"/>{{ e.privacy_reviewed ? 'Маскирование проверено' : 'Подтвердить маскирование' }}</button></template>
      <div v-if="tab === 'privacy' && canRecord && e.transcript.length" class="masked-audio-box"><p class="hint">В записи заглушены целые реплики с обнаруженными данными. Прослушайте её: маскирование может быть неполным.</p><button class="secondary full" @click="showMaskedAudio = !showMaskedAudio">Прослушать обезличенную запись</button><audio v-if="showMaskedAudio" :key="e.version" :src="'/api/v1/encounters/' + e.id + '/masked-audio'" controls style="width:100%;margin:12px 0"/><label class="check"><input v-model="audioReviewed" type="checkbox">Я прослушал запись и проверил отсутствие персональных данных</label><button class="secondary full" style="margin-top:12px" :disabled="locked || dirty || privacyDirty || !audioReviewed || !e.privacy_reviewed || !patient.cloud_audio_consent || !settings.cloud_asr_configured" @click="run(() => queue('cloud-asr', { version: e.version, audio_reviewed: audioReviewed }))">Уточнить распознавание в облаке</button><p class="hint">Нужны отдельное согласие пациента и настроенный CLOUD_ASR_URL.</p></div><div class="transcript-footer"><button class="primary full" :disabled="locked || !e.transcript.length" @click="run(generate)"><Sparkles :size="17"/>Заполнить лист и заключение ИИ</button><small>{{ settings.llm_is_cloud ? 'Облако · только проверенный обезличенный текст' : 'Обработка на настроенном сервере модели' }}</small></div>
    </section>
    <section class="panel consultation-form"><div class="section-title"><h3><FileText :size="19"/>Лист консультации</h3><span class="hint">{{ dirty ? 'Есть изменения' : 'Сохранено' }}</span></div><div class="document-hint"><Sparkles :size="16"/>AI готовит черновик. Проверьте факты, дозировки и назначения.</div><div class="clinical-fields"><label v-for="(label, key) in fieldNames" :key="key"><span>{{ label }}</span><textarea v-model="e.fields[key]" :disabled="locked" :rows="key === 'anamnesis' ? 5 : 3" :placeholder="'Внесите данные: ' + label.toLowerCase()" @input="dirty = true"></textarea></label>
        <section class="ai-conclusion" aria-labelledby="ai-conclusion-title">
          <h4 id="ai-conclusion-title"><Sparkles :size="17"/>Предварительное заключение ИИ</h4>
          <p id="ai-conclusion-notice" class="ai-conclusion-notice">{{ e.ai_notice?.disclaimer }}</p>
          <label><span>Заключение для проверки врачом</span><textarea v-model="e.fields.ai_conclusion" aria-describedby="ai-conclusion-notice" :disabled="locked" rows="5" placeholder="Появится после заполнения листа с ИИ. Проверьте результат и при необходимости исправьте его." @input="dirty = true"></textarea></label>
          <p class="hint">Пометка сохраняется после проверки врачом и передаётся в МИС вместе с заключением.</p>
        </section>
      </div><div class="document-actions"><button class="secondary" :disabled="locked" @click="run(save)"><Save :size="16"/>Сохранить</button><button class="primary" :disabled="locked" @click="run(approve)"><Check :size="17"/>Проверено врачом</button></div><div v-if="['approved', 'exported'].includes(e.status) && !dirty" class="mis-send"><p><ShieldCheck :size="16"/>Подтверждённый лист доступен по API МИС</p><button class="secondary full" :disabled="locked || !settings.mis_configured" @click="run(() => queue('send-to-mis', { version: e.version }))"><Send :size="16"/>Отправить в МИС</button><small v-if="!settings.mis_configured">Для исходящей отправки укажите MIS_URL в настройках сервера.</small></div></section>
  </div>
</template>
