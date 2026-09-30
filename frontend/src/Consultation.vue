<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ArrowLeft, Mic, Square, Upload, Sparkles, Save, Check, Send, ShieldCheck, RefreshCw, Plus, Trash2, Headphones, Pause, Play, History } from 'lucide-vue-next'
import { api } from './api'
import { useRecorder } from './recorder'
import DiagnosisPicker from './DiagnosisPicker.vue'
import ClinicalField from './ClinicalField.vue'
const props = defineProps(['initial', 'patient', 'settings', 'doctor'])
const emit = defineEmits(['back', 'updated'])
const e = ref(JSON.parse(JSON.stringify(props.initial))), error = ref(''), notice = ref(''), busy = ref(false), dirty = ref(false), tab = ref('transcript')
const rec = useRecorder()
const { devices, selected, recording, paused, recorderError, seconds, audioUrl, audioBlob, level } = rec
const processing = computed(() => e.value.status === 'processing')
const locked = computed(() => busy.value || processing.value || recording.value)
const canRecord = computed(() => props.patient.recording_consent && e.value.recording_consent)
const canTranscribe = computed(() => props.settings.asr_configured && (props.settings.asr_provider !== 'openai' || props.patient.openai_audio_consent))
const records = ref([]), revisions = ref([]), prior = ref(null), selectedRecord = ref(''), player = ref(null), sourceIndex = ref(-1), stage = ref(''), approvalChecked = ref(false)
const privacyDirty = ref(false), audioReviewed = ref(false), showMaskedAudio = ref(false)
const roles = { doctor: 'Врач', patient: 'Пациент', nurse: 'Медсестра', unknown: 'Роль не определена' }
const fields = { complaints:'Жалобы', anamnesis:'Анамнез заболевания', life_history:'Анамнез жизни', allergies:'Аллергии и реакции', medications:'Принимаемые лекарства', chronic_conditions:'Хронические заболевания', family_history:'Наследственность', operations:'Операции и перенесённые заболевания', habits:'Привычки и факторы риска', examination:'Объективные данные', investigations:'Исследования и результаты', diagnosis:'Диагноз врача', recommendations:'Назначения и рекомендации', follow_up:'План наблюдения', ai_conclusion:'Предварительное заключение ИИ' }
const vitals = { temperature:'Температура, °C', blood_pressure:'АД, мм рт. ст.', pulse:'Пульс, уд/мин', respiratory_rate:'ЧДД, в минуту', spo2:'SpO₂, %', height:'Рост, см', weight:'Вес, кг' }
const groups = [{title:'Жалобы', keys:['complaints']},{title:'Анамнез', keys:['anamnesis','life_history','allergies','medications','chronic_conditions','family_history','operations','habits']},{title:'Объективные данные',keys:['examination']},{title:'Исследования',keys:['investigations']},{title:'Диагноз',keys:['diagnosis']},{title:'Назначения и наблюдение',keys:['recommendations','follow_up']}]
const speakers = computed(() => [...new Set(e.value.transcript.map(s => s.speaker))])
const speakerOptions = computed(() => [...new Set(['SPEAKER_00','SPEAKER_01','SPEAKER_02',...speakers.value])])
const clock = computed(() => `${Math.floor(seconds.value / 60).toString().padStart(2,'0')}:${(seconds.value % 60).toString().padStart(2,'0')}`)
const audioSource = computed(() => selectedRecord.value ? `/api/v1/encounters/${e.value.id}/recordings/${selectedRecord.value}/audio` : '')
const age = computed(() => { const birth = new Date(props.patient.birth_date); const today = new Date(); return today.getFullYear()-birth.getFullYear()-(today < new Date(today.getFullYear(),birth.getMonth(),birth.getDate()) ? 1 : 0) })
const date = value => new Date(value * 1000).toLocaleString('ru-RU')
let timer, currentJob = props.initial.last_job?.state === 'running' || props.initial.last_job?.state === 'queued' ? props.initial.last_job.id : null, destroyed = false
async function run(fn) { error.value=''; notice.value=''; busy.value=true; try { await fn() } catch(err) { error.value=err.message } finally { busy.value=false } }
function update(value) { e.value=value; dirty.value=false; privacyDirty.value=false; audioReviewed.value=false; approvalChecked.value=false; emit('updated', value) }
function changed(key) { if(key==='diagnosis') e.value.fields.diagnosis_code=''; dirty.value=true; approvalChecked.value=false; e.value.fields.reviewed_fields = (e.value.fields.reviewed_fields || []).filter(x => x !== key); e.value.fields.sources = (e.value.fields.sources || []).filter(x => x.field !== key) }
function reviewField(key) { const list=e.value.fields.reviewed_fields || []; e.value.fields.reviewed_fields=list.includes(key) ? list.filter(x => x!==key) : [...list,key]; dirty.value=true }
function sources(key) { return e.value.fields.sources?.find(x => x.field === key)?.segments || [] }
async function refreshArchive() {
  const [audio, history] = await Promise.all([api(`/encounters/${e.value.id}/recordings`),api(`/encounters/${e.value.id}/history`)])
  records.value=audio; revisions.value=history
  if (!selectedRecord.value || !audio.some(x => x.id === selectedRecord.value)) selectedRecord.value=audio.find(x => x.available)?.id || ''
}
async function save() {
  update(await api(`/encounters/${e.value.id}`,{method:'PATCH',body:{version:e.value.version,fields:e.value.fields,transcript:e.value.transcript,speaker_roles:e.value.speaker_roles}}))
  await refreshArchive(); notice.value='Черновик сохранён'
}
async function poll() {
  try {
    if(currentJob) {
      const job=await api(`/jobs/${currentJob}`); stage.value=job.stage || job.kind
      if(job.error) error.value=job.error
      if(['done','failed'].includes(job.state)) {
        if(job.state==='done' && job.kind==='transcribe') { rec.clearAudio(); selectedRecord.value='' }
        currentJob=null; await refreshArchive()
      }
    }
    const result=await api(`/encounters/${e.value.id}`)
    if(result.last_job?.error) error.value=result.last_job.error
    if(!destroyed) { update(result); if(result.status==='processing') timer=setTimeout(poll,2000); else { await refreshArchive(); notice.value='Обработка завершена. Проверьте расшифровку и лист консультации.' } }
  } catch(err) { error.value=err.message; if(!destroyed) timer=setTimeout(poll,5000) }
}
async function queue(path,body) { const result=await api(`/encounters/${e.value.id}/${path}`,{method:'POST',body}); currentJob=result.job_id; e.value.status='processing'; stage.value='queued'; timer=setTimeout(poll,1000) }
async function upload(blob) {
  if(!blob || !blob.size) throw new Error('Запись пуста')
  if(!canTranscribe.value) throw new Error('Проверьте настройки ASR и согласие на OpenAI в карте пациента')
  if(dirty.value) await save()
  const data=new FormData(); data.append('file',blob,blob.name || 'consultation.' + (blob.type.includes('mp4') ? 'mp4' : 'webm')); data.append('analyze','true')
  await queue('audio',data)
}
async function finish() { const blob=await rec.stop(); await upload(blob) }
function chooseFile(event) {
  const file=event.target.files?.[0]; if(!file) return
  if(file.size>80*1024*1024) { error.value='Максимальный размер файла — 80 МБ'; event.target.value=''; return }
  const extensions={mp3:'audio/mpeg',wav:'audio/wav',m4a:'audio/mp4',mp4:'audio/mp4',webm:'audio/webm',ogg:'audio/ogg',flac:'audio/flac'}
  const mime=extensions[file.name.split('.').pop().toLowerCase()]
  if(!mime) { error.value='Выберите WAV, MP3, M4A, MP4, WebM, OGG или FLAC'; return }
  rec.setAudio(new Blob([file],{type:mime})); notice.value=`Загружено: ${file.name}. Нажмите «Распознать и заполнить».`; event.target.value=''
}
async function generate() { if(privacyDirty.value) throw new Error('Подтвердите изменения маскирования'); if(dirty.value) await save(); await queue('generate',{version:e.value.version}) }
async function privacy() { if(dirty.value) await save(); update(await api(`/encounters/${e.value.id}/privacy-review`,{method:'POST',body:{version:e.value.version,segments:e.value.redacted_transcript}})); notice.value='Маскирование проверено' }
async function approve() { if(!approvalChecked.value) throw new Error('Подтвердите проверку результата'); if(dirty.value) await save(); update(await api(`/encounters/${e.value.id}/approve`,{method:'POST',body:{version:e.value.version}})); await refreshArchive(); notice.value='Результат утверждён и доступен МИС через API' }
async function rejectDraft() { if(!window.confirm('Очистить поля черновика? Аудио, расшифровка и предыдущая версия сохранятся.')) return; for(const key of Object.keys(e.value.fields)) { if(['visit_type','visit_format'].includes(key)) continue; e.value.fields[key]=Array.isArray(e.value.fields[key]) ? [] : '' } dirty.value=true; await save() }
function selectDiagnosis(item) { changed('diagnosis'); e.value.fields.diagnosis_code=item.code; e.value.fields.diagnosis=item.name }
function showSource(index) { tab.value='transcript'; sourceIndex.value=index; if(records.value[0]?.available) selectedRecord.value=records.value[0].id; setTimeout(() => { document.getElementById('segment-'+index)?.scrollIntoView({behavior:'smooth',block:'center'}); if(player.value && Number.isFinite(e.value.transcript[index]?.start)) player.value.currentTime=e.value.transcript[index].start },0) }
function transcriptChanged() { dirty.value=true; approvalChecked.value=false; e.value.fields.reviewed_fields=[] }
function addSegment() { e.value.transcript.push({speaker:'SPEAKER_00',start:0,end:0,text:''}); e.value.speaker_roles.SPEAKER_00 ||= 'unknown'; dirty.value=true }
function back() { if(recording.value) { error.value='Завершите запись перед выходом';return } if((dirty.value || privacyDirty.value || audioBlob.value) && !window.confirm('Есть несохранённые изменения или запись. Выйти?'))return; emit('back') }
const unload=event=>{if(dirty.value || privacyDirty.value){event.preventDefault();event.returnValue=''}}
onMounted(async()=>{ try { await refreshArchive(); const list=await api(`/patients/${props.patient.id}/encounters`); prior.value=list.find(x=>x.id!==e.value.id && ['approved','exported'].includes(x.status)); if(processing.value)poll() } catch(err) { error.value=err.message } window.addEventListener('beforeunload',unload) })
onBeforeUnmount(()=>{destroyed=true;clearTimeout(timer);window.removeEventListener('beforeunload',unload)})
</script>
<template>
  <button class="text-button back" @click="back"><ArrowLeft :size="16"/>К карте пациента</button>
  <div class="page-heading consultation-heading"><div><span class="eyebrow">ANAMIO · ЛИСТ КОНСУЛЬТАЦИИ</span><h1>{{ e.fields.visit_format === 'remote' ? 'Онлайн-консультация' : 'Очная консультация' }}</h1><p class="muted">Черновик ИИ проверяет и утверждает врач</p></div><span class="badge" :class="e.status">{{ {draft:'Черновик',ready:'Требует проверки',processing:'Обработка',approved:'Утверждён',exported:'Передан в МИС'}[e.status] }}</span></div>
  <section class="patient-strip"><strong>{{ patient.name }}</strong><span>{{ age }} лет</span><span>ИИН: ••••••••{{ patient.iin?.slice(-4) }}</span><span>{{ date(e.created_at) }}</span><span>Врач: {{ doctor?.name || 'Лечащий врач' }}</span></section>
  <div class="consent-strip"><ShieldCheck :size="18"/><strong>Согласия:</strong><span :class="canRecord ? 'consent-ok' : 'consent-no'">{{ canRecord ? 'Запись разрешена' : 'Без записи · ручной приём' }}</span><span v-if="settings.asr_provider==='openai'" :class="patient.openai_audio_consent ? 'consent-ok' : 'consent-no'">OpenAI: {{ patient.openai_audio_consent ? 'согласие получено' : 'нет согласия' }}</span><span :class="patient.cloud_consent ? 'consent-ok' : 'consent-no'">Облачный анализ: {{ patient.cloud_consent ? 'разрешён' : 'не разрешён' }}</span></div>
  <div v-if="error || recorderError" class="alert error" role="alert">{{ error || recorderError }}</div><div v-if="notice" class="alert success" role="status">{{ notice }}</div>
  <div v-if="processing" class="alert processing-alert"><RefreshCw :size="19" class="spin"/>{{ {queued:'Запись в очереди',transcribing:'Распознаём речь и разделяем голоса',generating:'Заполняем поля и готовим заключение',generate:'Готовим заключение'}[stage] || 'Обрабатываем приём' }}. Можно вернуться к карте пациента.</div>
  <div class="consultation-workspace">
    <aside class="consultation-left">
      <section class="panel recording-card"><h3><Mic :size="19"/>Аудиозапись приёма</h3>
        <template v-if="canRecord"><div class="recording-meter"><span class="record-clock">{{ clock }}</span><span v-if="recording" class="recording-status">{{ paused ? 'Пауза' : 'Идёт запись' }}</span><div class="record-wave" aria-hidden="true"><i v-for="n in 24" :key="n" :style="{height:(recording && !paused ? 5+level*(15+n%5*13) : 4+n%4*3)+'px'}"></i></div></div>
          <div class="record-buttons"><template v-if="recording"><button class="secondary" :disabled="busy" @click="rec.pause"><component :is="paused ? Play : Pause" :size="16"/>{{ paused ? 'Продолжить' : 'Пауза' }}</button><button class="primary" :disabled="busy" @click="run(finish)"><Square :size="16"/>Закончить диалог приёма</button></template><button v-else class="primary full" :disabled="locked" @click="run(rec.start)"><Mic :size="17"/>{{ audioBlob ? 'Перезаписать' : 'Начать запись' }}</button></div>
          <label>Источник микрофона<select v-model="selected" :disabled="recording" @change="rec.saveDevice"><option value="">Системный микрофон</option><option v-for="d in devices" :key="d.deviceId" :value="d.deviceId">{{ d.label || 'Микрофон' }}</option></select></label><button class="text-button" :disabled="recording" @click="run(rec.discover)"><Headphones :size="15"/>Разрешить микрофон и обновить список</button>
          <label class="audio-file-label"><Upload :size="18"/>Загрузить запись приёма<input type="file" accept=".wav,.mp3,.m4a,.mp4,.webm,.ogg,.flac" :disabled="locked" aria-label="Загрузить запись приёма" @change="chooseFile"></label><p class="hint">WAV, MP3, M4A, MP4, WebM, OGG, FLAC · до 80 МБ. Выбор микрофона сохраняется.</p>
          <div v-if="audioUrl" class="uploaded-audio"><audio :src="audioUrl" controls/><button class="primary full" :disabled="locked || !canTranscribe" @click="run(()=>upload(audioBlob))">Распознать и заполнить</button></div>
          <p v-if="settings.asr_provider==='openai'" class="hint">OpenAI получает исходное аудио по отдельному согласию. Текст маскируется перед анализом; врач проверяет результат маскирования.</p><p v-if="!canTranscribe" class="alert warning">Нужны настройка ASR и согласие пациента на OpenAI.</p>
        </template><p v-else class="hint">Пациент не согласился на запись. Заполните лист вручную и утвердите его обычным способом.</p>
      </section>
      <section class="panel transcript-panel"><div class="section-title"><h3>Разговор</h3><span class="hint">{{ e.transcript.length }} реплик</span></div><div class="tabs compact-tabs"><button :class="{active:tab==='transcript'}" @click="tab='transcript'">Расшифровка</button><button :class="{active:tab==='privacy'}" @click="tab='privacy'">Маскирование</button><button :class="{active:tab==='archive'}" @click="tab='archive'">Архив</button></div>
        <div v-if="audioSource" class="archive-player"><label>Запись приёма<select v-model="selectedRecord"><option v-for="r in records.filter(x=>x.available)" :key="r.id" :value="r.id">{{ date(r.created_at) }}</option></select></label><audio ref="player" :src="audioSource" controls preload="metadata"/></div>
        <template v-if="tab==='transcript'"><div v-if="speakers.length" class="speaker-roles"><label v-for="s in speakers" :key="s"><span>Говорящий {{ Number(s.slice(-2))+1 }}</span><select v-model="e.speaker_roles[s]" :disabled="locked" @change="transcriptChanged"><option v-for="(label,role) in roles" :key="role" :value="role">{{ label }}</option></select></label></div>
          <div v-if="!e.transcript.length" class="empty"><Mic :size="30"/><p>Запишите диалог или загрузите аудио. После обработки здесь появятся реплики и роли.</p></div>
          <div class="segments"><article v-for="(s,i) in e.transcript" :id="'segment-'+i" :key="i" class="segment" :class="{'source-highlight':sourceIndex===i}"><div class="segment-meta"><span class="speaker-dot" :class="e.speaker_roles[s.speaker]"></span><select v-model="s.speaker" aria-label="Говорящий" :disabled="locked" @change="transcriptChanged"><option v-for="sp in speakerOptions" :key="sp" :value="sp">{{ roles[e.speaker_roles[sp]] || 'Говорящий' }} · {{ Number(sp.slice(-2))+1 }}</option></select><button class="text-button" @click="showSource(i)">{{ Math.floor(s.start/60) }}:{{ Math.floor(s.start%60).toString().padStart(2,'0') }}</button><button class="icon-button" aria-label="Удалить реплику" :disabled="locked" @click="e.transcript.splice(i,1);e.fields.sources=[];dirty=true"><Trash2 :size="13"/></button></div><textarea v-model="s.text" aria-label="Текст реплики" :disabled="locked" rows="3" @input="transcriptChanged"></textarea></article></div><button class="text-button add-segment" :disabled="locked" @click="addSegment"><Plus :size="15"/>Добавить реплику вручную</button></template>
        <template v-else-if="tab==='privacy'"><p class="privacy-note">Проверьте имена, ИИН, телефоны и адреса. Автоматическое маскирование может пропустить сведения.</p><div v-for="(s,i) in e.redacted_transcript" :key="i" class="segment"><textarea v-model="s.text" aria-label="Обезличенная реплика" :disabled="locked || dirty" rows="3" @input="privacyDirty=true"></textarea><button v-if="canRecord" class="text-button" :disabled="locked || dirty || privacyDirty" @click="run(()=>queue('mute-audio',{version:e.version,segment_indices:[i]}))">Заглушить реплику в копии аудио</button></div><button class="secondary full" :disabled="locked || !e.redacted_transcript.length" @click="run(privacy)">Подтвердить маскирование</button><div v-if="canRecord && records.length" class="masked-audio-box"><button class="text-button" @click="showMaskedAudio=!showMaskedAudio">Прослушать маскированную копию</button><audio v-if="showMaskedAudio" :key="e.version" :src="'/api/v1/encounters/'+e.id+'/masked-audio'" controls/><template v-if="settings.cloud_asr_configured"><label class="check"><input v-model="audioReviewed" type="checkbox">Проверено отсутствие персональных данных в аудио</label><button class="secondary" :disabled="locked || !audioReviewed || !e.privacy_reviewed || !patient.cloud_audio_consent" @click="run(()=>queue('cloud-asr',{version:e.version,audio_reviewed:true}))">Уточнить распознавание</button></template></div></template>
        <template v-else><div class="archive-list"><p class="hint">Исходные записи, версии расшифровок и заключений хранятся зашифрованно.</p><details v-for="r in records" :key="r.id"><summary>Аудио · {{ date(r.created_at) }} · {{ r.available ? 'Сохранено' : 'Недоступно' }}</summary><p v-for="(s,i) in r.transcript" :key="i"><b>{{ roles[r.speaker_roles[s.speaker]] || s.speaker }}:</b> {{ s.text }}</p></details><details v-for="revision in revisions" :key="revision.id"><summary>Версия {{ revision.version }} · {{ date(revision.created_at) }} · {{ {approve:'Утверждение',edit:'Правка',generate:'Заключение ИИ',transcribe:'Распознавание',before_edit:'До правки',before_generate:'До генерации',before_transcribe:'До распознавания'}[revision.action] || revision.action }}</summary><template v-for="(label,key) in fields" :key="key"><p v-if="revision.snapshot.fields[key]"><b>{{ label }}:</b> {{ revision.snapshot.fields[key] }}</p></template></details></div></template>
        <div class="transcript-footer"><button class="secondary full" :disabled="locked || !e.transcript.length || !settings.llm_configured" @click="run(generate)"><Sparkles :size="17"/>Повторить анализ и заполнение</button></div>
      </section>
      <section class="panel clinical-context"><h3>Из предыдущего приёма</h3><template v-if="prior"><p class="hint">Утверждено {{ date(prior.reviewed_at) }} · источник: Anamio</p><p><b>Аллергии:</b> {{ prior.fields.allergies || 'Не уточнено' }}</p><p><b>Лекарства:</b> {{ prior.fields.medications || 'Не уточнено' }}</p><p><b>Хронические заболевания:</b> {{ prior.fields.chronic_conditions || 'Не уточнено' }}</p></template><p v-else class="hint">Предыдущих утверждённых записей нет. Сверка с внешней картой МИС не подключена.</p></section>
    </aside>
    <section class="panel consultation-document"><div class="document-heading"><h3>Консультация специалиста</h3><div class="visit-selectors"><label>Вид<select v-model="e.fields.visit_type" :disabled="locked" @change="dirty=true"><option value="primary">Первичная</option><option value="repeat">Повторная</option></select></label><label>Формат<select v-model="e.fields.visit_format" :disabled="locked" @change="dirty=true"><option value="in_person">Очная</option><option value="remote">Онлайн</option></select></label></div></div>
      <div class="document-hint"><ShieldCheck :size="16"/>Пустое поле означает «не уточнено». ИИ не подтверждает диагноз и назначения.</div>
      <section v-for="(group,index) in groups" :key="group.title" class="clinical-section"><h3><span>{{ String(index+1).padStart(2,'0') }}</span>{{ group.title }}</h3>
        <DiagnosisPicker v-if="group.title==='Диагноз'" :code="e.fields.diagnosis_code" :disabled="locked" :suggestions="e.fields.diagnosis_suggestions" @select="selectDiagnosis"/>
        <div :class="{'clinical-two-columns':group.title==='Анамнез'}"><ClinicalField v-for="key in group.keys" :key="key" v-model="e.fields[key]" :name="key" :label="fields[key]" :disabled="locked" :sources="sources(key)" :reviewed="e.fields.reviewed_fields?.includes(key)" @update:model-value="changed(key)" @source="showSource" @review="reviewField(key)"/></div>
        <div v-if="group.title==='Объективные данные'" class="vitals-grid"><label v-for="(label,key) in vitals" :key="key">{{ label }}<input v-model="e.fields[key]" :disabled="locked" placeholder="Не измерено" @input="changed(key)"><button v-if="sources(key).length" class="text-button" @click="showSource(sources(key)[0])">Источник ↗</button></label></div>
      </section>
      <section class="clinical-section ai-conclusion"><h3><Sparkles :size="18"/>Предварительное заключение ИИ</h3><p class="ai-conclusion-notice">{{ e.ai_notice?.disclaimer }}</p><ClinicalField v-model="e.fields.ai_conclusion" name="ai_conclusion" label="Заключение для проверки" :sources="sources('ai_conclusion')" :disabled="locked" :reviewed="e.fields.reviewed_fields?.includes('ai_conclusion')" @update:model-value="changed('ai_conclusion')" @source="showSource" @review="reviewField('ai_conclusion')"/></section>
      <section class="clinical-section"><h3>Перед утверждением</h3><ul class="review-checklist"><li v-for="key in ['complaints','anamnesis','allergies','medications','examination','follow_up']" :key="key"><span :class="e.fields[key] ? 'consent-ok' : 'consent-no'">{{ e.fields[key] ? 'Есть сведения' : 'Уточнить' }}</span>{{ fields[key] }}</li></ul><ul v-if="e.fields.warnings?.length" class="ai-questions"><li v-for="warning in e.fields.warnings" :key="warning">{{ warning }}</li></ul><p class="hint">Проверка полноты документа; не клинический протокол и не гарантия отсутствия ошибок.</p><label class="check"><input v-model="approvalChecked" type="checkbox" :disabled="locked">Я проверил расшифровку, диагноз, назначения и заключение. Подтверждаю результат приёма.</label></section>
      <div class="document-actions sticky-actions"><button class="secondary" :disabled="locked" @click="run(save)"><Save :size="16"/>Сохранить черновик</button><button class="primary" :disabled="locked || !approvalChecked" @click="run(approve)"><Check :size="17"/>Утвердить результат приёма</button></div><button class="text-button reject-draft" :disabled="locked" @click="run(rejectDraft)">Отклонить черновик ИИ и заполнить вручную</button>
      <div v-if="['approved','exported'].includes(e.status) && !dirty" class="mis-send"><p><ShieldCheck :size="16"/>Утверждённый результат доступен МИС через API</p><button class="secondary full" :disabled="locked || !settings.mis_configured" @click="run(()=>queue('send-to-mis',{version:e.version}))"><Send :size="16"/>Отправить в МИС</button><small v-if="!settings.mis_configured">Исходящее подключение МИС не настроено. API чтения уже доступен.</small></div>
    </section>
  </div>
</template>
