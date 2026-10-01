<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from './api'
import { useRecorder } from './recorder'

const account = ref(null), options = ref({}), intakes = ref([]), current = ref(null), registering = ref(false)
const busy = ref(false), error = ref(''), notice = ref(''), language = ref('ru'), answer = ref(''), active = ref(0)
const emergency = ref(false), microphoneConsent = ref(false), cloudConsent = ref(false)
const auth = ref({email:'', password:'', name:'', age:18, sex:'unknown', consent:false})
const invitation = ref(new URLSearchParams(location.hash.slice(1)).get('invite') || '')
const rec = useRecorder(), {recording, seconds, audioBlob, recorderError} = rec
let stopTimer
const text = (ru, kk) => language.value === 'kk' ? kk : language.value === 'mixed' ? `${ru} / ${kk}` : ru
const followupCatalog = {
  pain_location:['Где именно болит? Отдаёт ли боль?', 'Нақты қай жеріңіз ауырады? Ауырсыну тарай ма?'],
  pain_scale:['Оцените боль от 0 до 10. Постоянная или приступами?', 'Ауырсынуды 0-ден 10-ға дейін бағалаңыз. Тұрақты ма, әлде ұстама ма?'],
  fever:['Какую температуру измерили и когда?', 'Дене қызуын қашан өлшедіңіз? Қанша болды?'],
  breathing:['Есть ли затруднение дыхания или боль в груди сейчас?', 'Қазір тыныс алу қиындауы немесе кеуде ауыруы бар ма?'],
  digestive:['Есть ли тошнота, рвота или изменение стула?', 'Жүрек айну, құсу немесе нәжістің өзгеруі бар ма?'],
  pregnancy:['Если относится к вам: возможна ли беременность?', 'Сізге қатысты болса: жүктілік болуы мүмкін бе?'],
  sexual_history:['Если связано с жалобой: изменения в половой жизни или риск инфекций? Можно пропустить.', 'Шағымға қатысты болса: жыныстық өмірдегі өзгерістер не инфекция қаупі бар ма? Өткізіп жіберуге болады.'],
  medication_reaction:['Как изменились симптомы после лекарств?', 'Дәрі қабылдағаннан кейін белгілер қалай өзгерді?']
}
const questions = computed(() => [...(current.value?.data.questions || []), ...(current.value?.data.followups || []).map(id => ({id, ru:followupCatalog[id]?.[0] || id, kk:followupCatalog[id]?.[1] || id}))])
const question = computed(() => questions.value[active.value])
const complete = computed(() => questions.value.every(q => current.value?.data.answers[q.id]?.trim()))
const readonly = computed(() => current.value?.state !== 'draft')
function speakQuestion() {
  if(!question.value || !window.speechSynthesis) return
  const code=language.value==='kk'?'kk':'ru'
  // Только локальные системные голоса: браузерные облачные голоса не используются.
  const voice=window.speechSynthesis.getVoices().find(v=>v.localService && v.lang.toLowerCase().startsWith(code))
  if(!voice){notice.value=text('Локальный голос для этого языка не установлен. Вопрос доступен текстом.','Осы тілдің жергілікті дауысы орнатылмаған. Сұрақ мәтінмен қолжетімді.');return}
  speechSynthesis.cancel()
  const utterance=new SpeechSynthesisUtterance(language.value==='kk'?question.value.kk:question.value.ru)
  utterance.voice=voice;utterance.lang=voice.lang;speechSynthesis.speak(utterance)
}
async function run(fn) { busy.value=true; error.value=''; notice.value=''; try { await fn() } catch(e) { error.value=e.message } finally { busy.value=false } }
function select(value) { current.value=value; language.value=value.data.language; active.value=0; answer.value=value.data.answers[questions.value[0]?.id] || ''; emergency.value=!!value.data.urgent }
async function load() { intakes.value=await api('/portal/intakes'); if(current.value) select(intakes.value.find(i=>i.id===current.value.id)||current.value) }
async function authenticate() {
  const body=registering.value ? {...auth.value, age:Number(auth.value.age), language:language.value} : {email:auth.value.email, password:auth.value.password}
  account.value=await api('/portal/auth/'+(registering.value?'register':'login'), {method:'POST', body})
  auth.value.password=''; await load()
}
async function start() {
  select(await api('/portal/intakes', {method:'POST', body:{invitation:invitation.value, recording_consent:microphoneConsent.value, cloud_consent:cloudConsent.value}}))
  invitation.value=''; history.replaceState(null,'',location.pathname); await load()
}
function goto(index) { if(question.value && !readonly.value) current.value.data.answers[question.value.id]=answer.value; active.value=index; answer.value=current.value.data.answers[question.value?.id] || '' }
async function save() {
  if(question.value) current.value.data.answers[question.value.id]=answer.value
  const index=active.value
  current.value=await api('/portal/intakes/'+current.value.id, {method:'PATCH', body:{version:current.value.version, answers:current.value.data.answers, language:language.value, urgent:emergency.value}})
  active.value=index; notice.value=text('Ответ сохранён','Жауап сақталды')
}
async function next() { await save(); if(emergency.value) return; if(active.value<questions.value.length-1) goto(active.value+1); else if(current.value.data.followup_status!=='done') await clarify() }
async function clarify() {
  await save()
  const count=questions.value.length
  current.value=await api('/portal/intakes/'+current.value.id+'/followups', {method:'POST',body:{version:current.value.version}})
  if(questions.value.length>count) goto(count)
  else notice.value=text('Уточнения завершены. Можно отправить врачу.','Нақтылау аяқталды. Дәрігерге жіберуге болады.')
}
async function submit() { await save(); current.value=await api('/portal/intakes/'+current.value.id+'/submit', {method:'POST', body:{version:current.value.version}}); await load(); notice.value=text('Отправлено врачу. Анкета не заменяет консультацию.','Дәрігерге жіберілді. Сауалнама кеңесті алмастырмайды.') }
async function stopVoice() {
  clearTimeout(stopTimer); await rec.stop()
  if(!audioBlob.value) return
  const data=new FormData(); data.append('file', audioBlob.value,'answer.webm'); data.append('version',current.value.version)
  const result=await api('/portal/intakes/'+current.value.id+'/voice',{method:'POST',body:data})
  answer.value+=(answer.value?' ':'')+result.text; rec.clearAudio(); await save()
}
async function startVoice() { await rec.start(); stopTimer=setTimeout(()=>run(stopVoice),25000) }
async function revoke() { current.value=await api('/portal/intakes/'+current.value.id+'/revoke',{method:'POST',body:{version:current.value.version}}); notice.value=text('Голос и внешняя обработка отключены','Дауыс және сыртқы өңдеу өшірілді') }
onMounted(()=>run(async()=>{options.value=await api('/portal/options'); try { account.value=await api('/portal/auth/me'); language.value=account.value.language; await load() } catch(e) { if(e.status!==401 && options.value.enabled) throw e } }))
onBeforeUnmount(()=>{clearTimeout(stopTimer);window.speechSynthesis?.cancel()})
</script>

<template>
  <main class="portal-shell">
    <header class="portal-heading"><div><a href="/">Smart Consult</a><h1>{{ text('Кабинет пациента','Пациент кабинеті') }}</h1></div><select v-model="language" aria-label="Язык / Тіл" :disabled="busy || recording"><option value="ru">Русский</option><option value="kk">Қазақша</option><option value="mixed">RU + Қазақша</option></select></header>
    <p class="hint">{{ text('Заранее расскажите врачу о самочувствии. Это сбор анамнеза, а не диагноз. Не указывайте ФИО, ИИН, адрес и телефон в ответах.','Дәрігерге жағдайыңызды алдын ала айтыңыз. Бұл диагноз емес, анамнез жинау. Жауапта аты-жөніңізді, ЖСН, мекенжай не телефонды айтпаңыз.') }}</p>
    <div v-if="error || recorderError" class="alert error" role="alert">{{ error || recorderError }}</div><div v-if="notice" class="alert success" role="status">{{ notice }}</div>
    <section v-if="!options.enabled" class="panel"><p>{{ text('Кабинет пациента ещё не подключён клиникой.','Пациент кабинетін клиника әлі қосқан жоқ.') }}</p></section>
    <section v-else-if="!account" class="panel"><form class="stack" @submit.prevent="run(authenticate)"><h2>{{ registering ? text('Регистрация','Тіркелу') : text('Вход','Кіру') }}</h2><label>Email<input v-model="auth.email" required type="email" autocomplete="username" maxlength="150"></label><label>{{ text('Пароль','Құпиясөз') }}<input v-model="auth.password" required type="password" :minlength="registering?12:1" maxlength="128" :autocomplete="registering?'new-password':'current-password'"></label><template v-if="registering"><label>{{ text('Имя (остаётся внутри MedHub)','Аты (MedHub ішінде сақталады)') }}<input v-model="auth.name" required minlength="2" maxlength="150" autocomplete="name"></label><label>{{ text('Возраст (для взрослых)','Жасы (ересектер үшін)') }}<input v-model="auth.age" required type="number" min="18" max="120"></label><label>{{ text('Пол','Жынысы') }}<select v-model="auth.sex"><option value="unknown">{{ text('Не указан','Көрсетілмеген') }}</option><option value="female">{{ text('Женский','Әйел') }}</option><option value="male">{{ text('Мужской','Ер') }}</option></select></label><p class="hint">{{ text('Имя, email и ответы хранятся зашифрованно. Выбранный врач получит отправленную анкету. Учётная запись не подтверждает личность и не открывает медицинскую карту.','Аты, email және жауаптар шифрланған түрде сақталады. Таңдалған дәрігер жіберілген сауалнаманы алады. Тіркелгі жеке басты растамайды және медициналық картаны ашпайды.') }}</p><label class="check"><input v-model="auth.consent" type="checkbox" required>{{ text('Согласен на хранение анкеты и передачу выбранному врачу','Сауалнаманы сақтауға және таңдалған дәрігерге беруге келісемін') }}</label></template><button class="primary" :disabled="busy">{{ text('Продолжить','Жалғастыру') }}</button><button type="button" class="text-button" @click="registering=!registering">{{ registering ? text('Уже есть аккаунт','Тіркелгім бар') : text('Зарегистрироваться','Тіркелу') }}</button></form></section>
    <template v-else>
      <div class="inline-actions"><span>{{ account.name }}</span><button class="text-button" :disabled="busy || recording" @click="run(async()=>{await api('/portal/auth/logout',{method:'POST'});account=null;current=null})">{{ text('Выйти','Шығу') }}</button></div>
      <section v-if="!current" class="panel stack"><h2>{{ text('Начать анкету по приглашению врача','Дәрігер шақыруы бойынша сауалнама бастау') }}</h2><label>{{ text('Код приглашения из ссылки врача','Дәрігер сілтемесіндегі шақыру коды') }}<input v-model="invitation" maxlength="100" autocomplete="off"></label><label class="check"><input v-model="microphoneConsent" type="checkbox">{{ text('Разрешаю локальную обработку голосовых ответов. Запись удаляется после распознавания.','Дауыстық жауаптарды жергілікті өңдеуге рұқсат беремін. Жазба танылғаннан кейін жойылады.') }}</label><label class="check"><input v-model="cloudConsent" type="checkbox">{{ text('Разрешаю обработку обезличенного анамнеза внешней AI-моделью. Автоматическое обезличивание может ошибаться.','Иесіздендірілген анамнезді сыртқы AI моделіне өңдеуге рұқсат беремін. Автоматты иесіздендіру қателесуі мүмкін.') }}</label><button class="primary" :disabled="busy || !invitation" @click="run(start)">{{ text('Начать','Бастау') }}</button><button v-for="item in intakes" :key="item.id" class="secondary" @click="select(item)">{{ new Date(item.created_at*1000).toLocaleString() }} · {{ item.state }}</button></section>
      <section v-else class="panel stack">
        <button class="text-button" :disabled="busy || recording" @click="run(async()=>{if(!readonly)await save();current=null;await load()})">← {{ text('Мои анкеты','Менің сауалнамаларым') }}</button>
        <div class="portal-emergency"><strong>{{ text('Если состояние резко ухудшилось, не ждите ответа программы: 103 или 112.','Жағдайыңыз күрт нашарласа, бағдарламаның жауабын күтпеңіз: 103 немесе 112.') }}</strong><label class="check"><input v-model="emergency" type="checkbox" :disabled="readonly || busy || recording" @change="run(save)">{{ text('Сейчас сильная боль в груди, тяжело дышать, сильное кровотечение или другое неотложное состояние','Қазір кеудеде қатты ауырсыну, тыныс алу қиындауы, қатты қан кету немесе басқа шұғыл жағдай бар') }}</label></div>
        <p v-if="emergency" role="alert">{{ text('Анкетирование остановлено. Позвоните 103/112. Программа не вызывает скорую и не уведомляет врача автоматически.','Сауалнама тоқтатылды. 103/112 нөміріне қоңырау шалыңыз. Бағдарлама жедел жәрдем шақырмайды және дәрігерге автоматты хабар бермейді.') }}</p>
        <template v-else-if="question"><div class="inline-actions"><button :disabled="busy || recording || active===0" @click="goto(active-1)">←</button><span>{{ active+1 }} / {{ questions.length }}</span><button :disabled="busy || recording || active===questions.length-1" @click="goto(active+1)">→</button></div><h2>{{ text(question.ru,question.kk) }}</h2><button class="text-button" :disabled="recording" @click="speakQuestion">{{ text('Прочитать вопрос локальным голосом','Сұрақты жергілікті дауыспен оқу') }}</button><textarea v-model="answer" rows="5" maxlength="5000" :disabled="readonly || busy || recording" :aria-label="text('Ответ','Жауап')"/><div v-if="!readonly" class="inline-actions"><button class="secondary" :disabled="busy || recording" @click="run(async()=>{answer='пропустить / өткізіп жіберу';await next()})">{{ text('Пропустить','Өткізіп жіберу') }}</button><button class="primary" :disabled="busy || recording || !answer.trim()" @click="run(next)">{{ text('Сохранить и далее','Сақтап, әрі қарай') }}</button><button v-if="current.data.recording_consent" class="secondary" :disabled="busy" @click="run(recording?stopVoice:startVoice)">{{ recording ? text('Завершить ответ','Жауапты аяқтау') : text('Ответить голосом','Дауыспен жауап беру') }} {{ recording?seconds+' с':'' }}</button></div></template>
        <div class="inline-actions"><button v-if="!readonly" class="primary" :disabled="busy || recording || (!complete && !emergency)" @click="run(submit)">{{ text('Отправить врачу','Дәрігерге жіберу') }}</button><span v-else>{{ text('Анкета отправлена врачу','Сауалнама дәрігерге жіберілді') }}</span><button :disabled="busy || recording" class="text-button" @click="run(revoke)">{{ text('Отозвать согласие на голос и API','Дауыс пен API келісімін қайтарып алу') }}</button></div>
      </section>
    </template>
  </main>
</template>

<style scoped>
.portal-shell{max-width:860px;margin:30px auto;padding:0 20px 50px}.portal-heading{display:flex;justify-content:space-between;align-items:center;gap:20px}.portal-heading select{max-width:180px}.portal-shell .panel{padding:24px;margin:20px 0}.portal-shell textarea{width:100%;font:inherit;padding:14px;border:1px solid #ccc;border-radius:10px;resize:vertical}.portal-emergency{background:#fff4e6;padding:16px;border-radius:10px}.portal-shell .inline-actions{flex-wrap:wrap}.portal-shell .check{align-items:flex-start}.portal-shell h2{font-size:21px}
</style>
