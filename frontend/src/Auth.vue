<script setup>
import MaskedInput from './MaskedInput.vue'
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { ArrowRight, Fingerprint, QrCode, ShieldCheck, Stethoscope, KeyRound } from 'lucide-vue-next'
import { api } from './api'
import { signNonce } from './eds'
import UmcLogo from './UmcLogo.vue'
const emit = defineEmits(['login'])
const register = ref(false), busy = ref(false), error = ref(''), options = ref({}), qr = ref(null)
const form = ref({ name: '', iin: '', email: '', password: '', code: '' })
let pollTimer
onMounted(async () => { try { options.value = await api('/auth/options') } catch (e) { error.value = e.message } })
onBeforeUnmount(() => clearTimeout(pollTimer))
async function submit() {
  error.value = ''; busy.value = true
  try { emit('login', await api('/auth/' + (register.value ? 'register' : 'login'), { method: 'POST', body: register.value ? form.value : { email: form.value.email, password: form.value.password } })) }
  catch (e) { error.value = e.message } finally { busy.value = false }
}
async function identity(method) {
  error.value = ''; busy.value = true; qr.value = null; clearTimeout(pollTimer)
  try {
    if (register.value && !/^[0-9]{12}$/.test(form.value.iin)) throw new Error('Введите ИИН: 12 цифр. Он должен совпадать с ИИН владельца ЭЦП.')
    const session = await api(`/auth/identity/${method}/start`, { method: 'POST', body: { purpose: register.value ? 'register' : 'login', code: form.value.code, iin: register.value ? form.value.iin : '' } })
    if (method === 'eds') {
      const signature = await signNonce(session.nonce)
      await api(`/auth/identity/${session.id}/signature`, { method: 'POST', body: { signature } })
      emit('login', await api(`/auth/identity/${session.id}/finish`, { method: 'POST' }))
    } else { qr.value = session; pollTimer = setTimeout(poll, 3000) }
  } catch (e) { error.value = e.message } finally { busy.value = false }
}
async function poll() {
  if (!qr.value) return
  try {
    const s = await api(`/auth/identity/${qr.value.id}`)
    if (s.state === 'signed') {
      emit('login', await api(`/auth/identity/${qr.value.id}/finish`, { method: 'POST' })); qr.value = null
    } else if (Date.now() / 1000 >= s.expires_at) { qr.value = null; error.value = 'QR истёк. Создайте новый.' }
    else pollTimer = setTimeout(poll, 3000)
  } catch (e) { error.value = e.message; qr.value = null }
}
</script>

<template>
  <div class="auth-layout">
    <section class="auth-story">
      <a class="platform-brand" href="/"><UmcLogo :caption="false"/><strong>Smart Consult</strong><span>Консультация с AI / ИИ-ассистентом</span></a>
      <div class="story-copy"><span class="eyebrow light">БОЛЬШЕ ВНИМАНИЯ ПАЦИЕНТУ</span><h1>Вы ведёте приём.<br><span>Мы помогаем<br>с записями.</span></h1><p>AI-ассистент превращает разговор в структурированный лист консультации. Решение всегда остаётся за врачом.</p></div>
      <div class="story-note"><div class="note-top"><Stethoscope :size="22"/><span>Ваш помощник на приёме</span><span class="small-dot"></span></div><div class="note-lines"><i></i><i></i><i></i></div><div class="note-bottom"><ShieldCheck :size="17"/> С согласия пациента. Под контролем врача.</div></div>
      <footer>Smart Consult · кабинет врача <span>Создано в рамках хакатона medhub</span></footer>
    </section>
    <section class="auth-form">
      <div class="auth-form-inner">
        <a class="platform-brand auth-mobile-brand" href="/"><UmcLogo :caption="false"/><strong>Smart Consult</strong><span>Консультация с AI / ИИ-ассистентом</span></a>
        <span class="eyebrow">ЛИЧНЫЙ КАБИНЕТ ВРАЧА</span><h2>{{ register ? 'Начнём знакомство' : 'Рады видеть вас' }}</h2><p class="muted">{{ register ? 'Создайте учётную запись врача' : 'Войдите, чтобы продолжить работу с пациентами' }}</p>
        <div class="tabs"><button :class="{ active: !register }" @click="register = false">Вход</button><button :class="{ active: register }" @click="register = true">Регистрация</button></div>
        <div v-if="error" class="alert error" role="alert">{{ error }}</div>
        <form @submit.prevent="submit" class="stack">
          <label v-if="register">ФИО врача<input v-model="form.name" required minlength="2" autocomplete="name" placeholder="Как к вам обращаться"></label>
          <label v-if="register">ИИН врача<MaskedInput v-model="form.iin" required autocomplete="off" aria-describedby="iin-help"/></label>
          <p v-if="register" id="iin-help" class="hint">Для входа через ЭЦП или eGov Mobile ИИН в проверенной подписи должен совпадать с ИИН учётной записи.</p>
          <label>Электронная почта<input v-model="form.email" type="email" required autocomplete="username" placeholder="doctor@clinic.kz"></label>
          <label>Пароль<input v-model="form.password" type="password" required :minlength="register ? 12 : 1" :autocomplete="register ? 'new-password' : 'current-password'" placeholder="Введите пароль"></label>
          <label v-if="register && !options.demo_mode">Код приглашения<input v-model="form.code" autocomplete="off" placeholder="Код от администратора клиники"></label>
          <p v-if="register" class="hint">Не менее 12 символов. Регистрация по ЭЦП также доступна ниже.</p>
          <button class="primary full" :disabled="busy">{{ busy ? 'Подождите…' : register ? 'Создать кабинет' : 'Войти в кабинет' }}<ArrowRight :size="18"/></button>
        </form>
        <div class="divider">или {{ register ? 'зарегистрируйтесь' : 'войдите' }} по ЭЦП</div>
        <div class="identity-buttons"><button :disabled="busy || !options.sigex_enabled" @click="identity('eds')"><Fingerprint :size="22"/><span>ЭЦП / NCALayer<small>Проверка через SIGEX</small></span></button><button :disabled="busy || !options.sigex_enabled" @click="identity('qr')"><QrCode :size="22"/><span>eGov Mobile<small>QR через SIGEX</small></span></button></div>
        <div v-if="qr" class="qr-box"><img :src="qr.qr_image" alt="QR для подписания в eGov Mobile"><p>Откройте eGov Mobile и отсканируйте QR</p><a :href="qr.launch_url">Открыть eGov на этом устройстве</a></div>
        <p class="auth-security"><KeyRound :size="15"/> Подпись проверяется на сервере SIGEX</p>
        <p v-if="options.demo_mode" class="demo-note">Локальная демонстрация · используйте вымышленные данные</p>
      </div>
    </section>
  </div>
</template>
