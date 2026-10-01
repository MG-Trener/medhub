<script setup>
import { ref, onMounted } from 'vue'
import { api } from './api'
const props=defineProps(['encounter'])
const emit=defineEmits(['imported'])
const records=ref([]), invitation=ref(''), busy=ref(false), error=ref(''), selected=ref(null)
const script=ref('')
async function run(fn){busy.value=true;error.value='';try{await fn()}catch(e){error.value=e.message}finally{busy.value=false}}
async function load(){records.value=await api('/intakes')}
async function invite(){
  let questions=[]
  if(script.value.trim()) questions=script.value.split('\n').filter(x=>x.trim()).map((line,i)=>{const [ru,kk]=line.split('|').map(x=>x.trim());if(!ru||!kk)throw new Error('Для каждого вопроса укажите русский | казахский текст');return {id:'custom_'+i,ru,kk}})
  invitation.value=(await api('/intake-invitations',{method:'POST',body:{questions}})).url
}
async function importSelected(){
  const result=await api(`/intakes/${selected.value.id}/import`,{method:'POST',body:{version:props.encounter.version,encounter_id:props.encounter.id}})
  emit('imported',result);await load();selected.value=null
}
onMounted(()=>run(load))
</script>
<template>
  <section class="panel intake-inbox"><h2>Анкеты до приёма</h2><p class="hint">Пациент заполняет анамнез дома. Приглашение одноразовое, действует 7 дней. Сопоставьте пациента с медкартой перед переносом.</p><div v-if="error" class="alert error" role="alert">{{ error }}</div><details><summary>Сценарий врача (необязательно)</summary><label>Один вопрос на строку: русский | казахский<textarea v-model="script" rows="5" maxlength="15000" placeholder="Пусто — стандартный сценарий анамнеза"/></label></details><div class="inline-actions"><button class="secondary" :disabled="busy" @click="run(invite)">Создать приглашение</button><button class="text-button" :disabled="busy" @click="run(load)">Обновить</button></div><label v-if="invitation">Скопируйте ссылку для пациента<input :value="invitation" readonly @focus="$event.target.select()"></label><button v-for="item in records" :key="item.id" class="secondary" @click="selected=item">{{ item.patient_profile.name }} · {{ item.patient_profile.age }} лет · {{ item.state === 'imported' ? 'Перенесено' : 'Ожидает врача' }} {{ item.data.urgent ? '· Неотложные симптомы' : '' }}</button><div v-if="selected"><h3>{{ selected.patient_profile.name }}</h3><p class="hint">Личность не подтверждена. Сведения со слов пациента.</p><div v-for="q in selected.data.questions" :key="q.id"><strong>{{ q.ru }}</strong><p class="intake-answer">{{ selected.data.answers[q.id] || 'Не уточнено' }}</p></div><p v-for="key in selected.data.followups" :key="key" class="intake-answer">{{ key }}: {{ selected.data.answers[key] || 'Не уточнено' }}</p><label v-if="encounter" class="check"><input type="checkbox" :disabled="busy" @change="selected.confirmed=$event.target.checked">Подтверждаю, что анкета относится к пациенту текущего приёма</label><button v-if="encounter && selected.state==='submitted'" class="primary" :disabled="busy || !selected.confirmed" @click="run(importSelected)">Перенести анамнез в лист</button><p v-else-if="!encounter" class="hint">Откройте приём соответствующего пациента для переноса.</p></div></section>
</template>
<style scoped>.intake-inbox{padding:22px;display:grid;gap:14px}.intake-answer{white-space:pre-wrap}.intake-inbox textarea{width:100%;font:inherit}</style>
