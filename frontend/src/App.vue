<script setup>
import { ref, computed, onMounted } from 'vue'
import { Users, Search, Plus, ChevronRight, ArrowLeft, Settings2, ShieldCheck, LogOut, Activity, CalendarDays, ArrowUpRight, X, FileText, Mic, PlugZap } from 'lucide-vue-next'
import Auth from './Auth.vue'
import Consultation from './Consultation.vue'
import Settings from './Settings.vue'
import UmcLogo from './UmcLogo.vue'
import { api } from './api'
const doctor = ref(null), loading = ref(true), page = ref('patients'), patients = ref([]), search = ref(''), patient = ref(null), encounters = ref([]), encounter = ref(null)
const error = ref(''), busy = ref(false), createOpen = ref(false), settings = ref({}), offset = ref(0)
const emptyPatient = () => ({ name: '', iin: '', birth_date: '', phone: '', sex: 'unknown', recording_consent: false, cloud_consent: false, cloud_audio_consent: false, openai_audio_consent: false, external_id: null })
const form = ref(emptyPatient())
const initials = name => (name || '').split(' ').slice(0, 2).map(x => x[0]).join('')
const date = value => new Date(value * 1000).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' })
const today = new Date().toLocaleDateString('ru-RU', { weekday: 'long', day: 'numeric', month: 'long' })
const statuses = { draft: 'Черновик', ready: 'Готов к проверке', processing: 'Обработка', approved: 'Подтверждён', exported: 'Передан в МИС' }
const title = computed(() => page.value === 'settings' ? 'Настройки кабинета' : encounter.value ? 'Приём пациента' : patient.value ? 'Карта пациента' : 'Пациенты')
async function run(fn) { error.value = ''; busy.value = true; try { await fn() } catch (e) { error.value = e.message; if (e.status === 401) doctor.value = null } finally { busy.value = false } }
async function loadPatients(reset = true) {
  if (reset) offset.value = 0
  const list = await api(`/patients?q=${encodeURIComponent(search.value)}&offset=${offset.value}&limit=30`)
  patients.value = reset ? list : [...patients.value, ...list]
}
async function login(value) { doctor.value = value; await run(async () => { settings.value = await api('/settings'); await loadPatients() }) }
async function openPatient(p) { await run(async () => { patient.value = await api(`/patients/${p.id}`); encounters.value = await api(`/patients/${p.id}/encounters`); encounter.value = null }) }
async function newPatient() { await run(async () => { const p = await api('/patients', { method: 'POST', body: form.value }); createOpen.value = false; form.value = emptyPatient(); await loadPatients(); patient.value = p; encounters.value = [] }) }
async function startEncounter() { await run(async () => { encounter.value = await api(`/patients/${patient.value.id}/encounters`, { method: 'POST' }) }) }
async function openEncounter(e) { await run(async () => { encounter.value = await api(`/encounters/${e.id}`) }) }
async function back() { if (encounter.value) { await openPatient(patient.value) } else patient.value = null }
function go(pageName) { if (encounter.value) return; page.value = pageName; patient.value = null }
async function logout() { await run(async () => { await api('/auth/logout', { method: 'POST' }); doctor.value = null; patient.value = null; encounter.value = null; patients.value = [] }) }
async function updateConsent(event, field) { await run(async () => { patient.value = await api(`/patients/${patient.value.id}/consent`, { method: 'PATCH', body: { recording_consent: patient.value.recording_consent, cloud_consent: patient.value.cloud_consent, cloud_audio_consent: patient.value.cloud_audio_consent || false, openai_audio_consent: patient.value.openai_audio_consent || false, [field]: event.target.checked } }) }) }
onMounted(async () => { try { await login(await api('/auth/me')) } catch {} finally { loading.value = false } })
</script>

<template>
  <div v-if="loading" class="initial-loading">Anamio<span>Загружаем кабинет…</span></div>
  <Auth v-else-if="!doctor" @login="login"/>
  <div v-else class="app-shell">
    <aside class="sidebar">
      <a class="brand" href="/"><span class="brand-icon">a<span>+</span></span>Anamio<span class="brand-dot">.</span></a>
      <div class="workspace-label">ПРОСТРАНСТВО ВРАЧА</div>
      <nav><button :class="{ active: page === 'patients' }" :disabled="!!encounter" @click="go('patients')"><Users :size="19"/>Пациенты<ChevronRight class="nav-arrow" :size="15"/></button><button :class="{ active: page === 'settings' }" :disabled="!!encounter" @click="go('settings')"><Settings2 :size="19"/>Настройки</button></nav>
      <div class="sidebar-help"><div class="mini-symbol"><Activity :size="22"/></div><h4>Внимание — пациенту</h4><p>Рутинные записи поможет подготовить AI-ассистент.</p><span>ВЫ ПРОВЕРЯЕТЕ И РЕШАЕТЕ</span></div>
      <UmcLogo compact class="sidebar-umc"/>
      <div class="sidebar-bottom"><ShieldCheck :size="16"/><span>Защищённое пространство</span></div>
      <div class="doctor-card"><div class="avatar">{{ initials(doctor.name) }}</div><div><strong>{{ doctor.name }}</strong><span>Личный кабинет врача</span></div><button class="icon-button" aria-label="Выйти" :disabled="!!encounter" @click="logout"><LogOut :size="17"/></button></div>
    </aside>
    <div class="main-shell">
      <header class="topbar"><div class="breadcrumb">Кабинет врача <ChevronRight :size="14"/><strong>{{ title }}</strong></div><div class="topbar-right"><span class="connection"><i></i>Рабочее пространство</span><span class="avatar small">{{ initials(doctor.name) }}</span></div></header>
      <main>
        <div v-if="error" class="alert error" role="alert">{{ error }}<button class="icon-button" aria-label="Закрыть сообщение" @click="error = ''"><X :size="16"/></button></div>
        <Settings v-if="page === 'settings'" :settings="settings"/>
        <Consultation v-else-if="encounter" :initial="encounter" :patient="patient" :settings="settings" :doctor="doctor" @back="back" @updated="encounter = $event"/>
        <template v-else-if="patient">
          <button class="text-button back" @click="back"><ArrowLeft :size="16"/>Все пациенты</button>
          <div class="page-heading"><div><span class="eyebrow">КАРТА ПАЦИЕНТА</span><h1>{{ patient.name }}</h1><p class="muted">ID {{ patient.id.slice(0, 8) }} · ИИН {{ patient.iin }}</p></div><button class="primary" :disabled="busy" @click="startEncounter"><Plus :size="18"/>Начать приём</button></div>
          <div class="patient-summary"><div><span>Дата рождения</span><strong>{{ patient.birth_date }}</strong></div><div><span>Телефон</span><strong>{{ patient.phone || 'Не указан' }}</strong></div><div><span>Пол</span><strong>{{ { female: 'Женский', male: 'Мужской', unknown: 'Не указан' }[patient.sex] }}</strong></div><div><span>Внешний ID МИС</span><strong>{{ patient.external_id || 'Не указан' }}</strong></div></div>
          <section class="panel consent-panel"><ShieldCheck :size="25"/><div><h3>Согласия пациента</h3><p class="muted">Фиксируйте решение пациента до начала приёма. Без согласия доступно ручное заполнение.</p><label class="check"><input type="checkbox" :checked="patient.recording_consent" :disabled="busy" @change="updateConsent($event, 'recording_consent')">Пациент согласен на запись и распознавание разговора</label><label class="check"><input type="checkbox" :checked="patient.cloud_consent" :disabled="busy" @change="updateConsent($event, 'cloud_consent')">Разрешена обработка обезличенного текста облачной моделью</label><label class="check"><input type="checkbox" :checked="patient.cloud_audio_consent" :disabled="busy" @change="updateConsent($event, 'cloud_audio_consent')">Разрешена отправка проверенной обезличенной записи облачному ASR</label><label class="check"><input type="checkbox" :checked="patient.openai_audio_consent" :disabled="busy" @change="updateConsent($event, 'openai_audio_consent')">Пациент согласен на передачу исходной записи разговора в OpenAI, включая возможные персональные и медицинские данные</label><p class="hint">В режиме OpenAI маскирование выполняется после отправки записи и распознавания.</p></div></section>
          <section class="panel"><div class="section-title"><h3>История приёмов <span class="count">{{ encounters.length }}</span></h3><FileText :size="20"/></div><div v-if="!encounters.length" class="empty compact"><CalendarDays :size="36"/><h3>Первый приём ещё впереди</h3><p>Начните приём, чтобы создать лист консультации.</p></div><button v-for="e in encounters" :key="e.id" class="encounter-row" @click="openEncounter(e)"><div class="document-icon"><FileText :size="21"/></div><div><strong>Консультация врача</strong><span>{{ date(e.created_at) }} · {{ e.id.slice(0, 8) }}</span></div><span class="badge" :class="e.status">{{ statuses[e.status] }}</span><ChevronRight :size="18"/></button></section>
        </template>
        <template v-else>
          <div class="page-heading"><div><span class="eyebrow">{{ today }}</span><h1>Пациенты</h1><p class="muted">Всё для приёма — в одном пространстве.</p></div><button class="primary" @click="createOpen = true"><Plus :size="18"/>Добавить пациента</button></div>
          <section class="welcome-banner"><div><span class="eyebrow">УМНЫЙ ПОМОЩНИК НА ПРИЁМЕ</span><h2>Меньше записей.<br>Больше живого разговора.</h2><p>Запишите консультацию — ассистент подготовит черновик,<br class="desktop-only"> а вы проверите детали и подтвердите результат.</p><div class="banner-steps"><span><Mic :size="15"/>Разговор</span><ChevronRight :size="13"/><span><Activity :size="15"/>Расшифровка</span><ChevronRight :size="13"/><span><FileText :size="15"/>Лист консультации</span></div></div><div class="banner-art" aria-hidden="true"><div class="orbit orbit-one"></div><div class="orbit orbit-two"></div><div class="art-sheet"><div class="art-title"><span>m+</span><i></i></div><div class="art-wave"><b v-for="(height, n) in [13,24,38,21,47,60,32,52,27,43,19,31,13]" :key="n" :style="{ height: height + 'px' }"></b></div><div class="art-line"></div><div class="art-line short"></div><div class="art-check"><ShieldCheck :size="22"/>Под вашим контролем</div></div></div></section>
          <section class="panel patient-list"><div class="section-title"><h3>Список пациентов <span class="count">{{ patients.length }}</span></h3><span class="hint">Ваши пациенты и история консультаций</span></div><form class="search-row" @submit.prevent="run(() => loadPatients())"><div class="search-field"><Search :size="19"/><input v-model="search" placeholder="Поиск по ФИО или полному ИИН" aria-label="Поиск пациента"><button v-if="search" type="button" class="icon-button" aria-label="Очистить поиск" @click="search = ''; run(() => loadPatients())"><X :size="16"/></button></div><button class="secondary" :disabled="busy">Найти пациента</button></form>
            <div class="table-wrap"><table v-if="patients.length"><thead><tr><th>ПАЦИЕНТ</th><th>ИИН</th><th>ДАТА РОЖДЕНИЯ</th><th>ЗАПИСЬ РАЗГОВОРА</th><th></th></tr></thead><tbody><tr v-for="p in patients" :key="p.id"><td><button class="patient-name" @click="openPatient(p)"><span class="avatar">{{ initials(p.name) }}</span><span><strong>{{ p.name }}</strong><small>ID {{ p.id.slice(0, 8) }}</small></span></button></td><td class="mono">{{ p.iin }}</td><td>{{ p.birth_date }}</td><td><span class="badge" :class="p.recording_consent ? 'approved' : 'neutral'"><i></i>{{ p.recording_consent ? 'Согласие получено' : 'Без записи' }}</span></td><td><button class="icon-button" aria-label="Открыть карту пациента" @click="openPatient(p)"><ArrowUpRight :size="19"/></button></td></tr></tbody></table></div>
            <div v-if="!patients.length" class="empty"><Users :size="38"/><h3>{{ search ? 'Пациент не найден' : 'Здесь появятся ваши пациенты' }}</h3><p>{{ search ? 'Проверьте ФИО или ИИН. Если пациент новый, создайте карточку.' : 'Создайте первую карточку, чтобы начать консультацию.' }}</p><button class="secondary" @click="createOpen = true"><Plus :size="16"/>Добавить пациента</button></div>
            <div v-if="patients.length && patients.length % 30 === 0" class="table-footer"><button class="text-button" @click="offset += 30; run(() => loadPatients(false))">Показать ещё</button></div>
          </section><div class="page-footnote"><ShieldCheck :size="15"/>Данные доступны только в вашем кабинете и по выданному вами ключу МИС.</div>
        </template>
      </main>
    </div>
    <div v-if="createOpen" class="modal-backdrop" @click.self="createOpen = false"><section class="modal" role="dialog" aria-modal="true" aria-labelledby="patient-modal-title"><div class="section-title"><div><span class="eyebrow">НОВАЯ КАРТОЧКА</span><h2 id="patient-modal-title">Добавить пациента</h2></div><button class="icon-button" aria-label="Закрыть" @click="createOpen = false"><X/></button></div><div v-if="error" class="alert error">{{ error }}</div><form class="stack" @submit.prevent="newPatient"><label>ФИО<input v-model="form.name" required minlength="2" placeholder="Фамилия Имя Отчество" autofocus></label><div class="form-grid"><label>ИИН<input v-model="form.iin" required pattern="[0-9]{12}" maxlength="12" inputmode="numeric" placeholder="12 цифр"></label><label>Дата рождения<input v-model="form.birth_date" required type="date" :max="new Date().toISOString().slice(0,10)"></label><label>Телефон<input v-model="form.phone" type="tel" placeholder="+7"></label><label>Пол<select v-model="form.sex"><option value="unknown">Не указан</option><option value="female">Женский</option><option value="male">Мужской</option></select></label></div><label>Идентификатор в МИС <span class="hint">необязательно</span><input v-model="form.external_id" placeholder="Внешний ID пациента"></label><div class="consent-box"><ShieldCheck :size="20"/><h4>Согласия пациента</h4><label class="check"><input v-model="form.recording_consent" type="checkbox">Согласен на запись и распознавание разговора</label><label class="check"><input v-model="form.cloud_consent" type="checkbox">Согласен на передачу обезличенного текста облачной LLM</label><label class="check"><input v-model="form.cloud_audio_consent" type="checkbox">Согласен на передачу проверенного обезличенного аудио облачному ASR</label><label class="check"><input v-model="form.openai_audio_consent" type="checkbox">Согласен на передачу исходной записи в OpenAI, включая возможные персональные и медицинские данные</label><p class="hint">В режиме OpenAI маскирование выполняется после отправки записи и распознавания.</p><p class="hint">Если пациент отказался от записи, врач заполнит лист вручную.</p></div><button class="primary full" :disabled="busy">Создать карточку<ArrowUpRight :size="18"/></button></form></section></div>
  </div>
</template>
