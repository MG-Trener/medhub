<script setup>
import PagedText from './PagedText.vue'
defineProps(['modelValue', 'label', 'name', 'sources', 'reviewed', 'disabled', 'rows', 'regeneratable', 'aiLocked'])
defineEmits(['update:modelValue', 'source', 'review', 'regenerate', 'lock'])
</script>
<template>
  <div class="clinical-field">
    <div class="clinical-field-title"><label :for="'field-' + name">{{ label }}</label><span class="field-state" :class="{ verified: reviewed }">{{ reviewed ? 'Проверено врачом' : modelValue ? (sources?.length ? 'Из диалога · проверить' : 'Без ссылки · проверить') : 'Не уточнено' }}</span></div>
    <PagedText :id="'field-' + name" :model-value="modelValue" :label="label" :disabled="disabled" @update:model-value="$emit('update:modelValue', $event)"/>
    <div class="field-links"><button v-if="modelValue" class="text-button" type="button" :disabled="disabled" :aria-pressed="!!reviewed" @click="$emit('review')">{{ reviewed ? 'Проверено врачом' : 'Проверить поле' }}</button><button class="text-button" type="button" :disabled="disabled" :aria-pressed="!!aiLocked" @click="$emit('lock')">{{ aiLocked ? 'Защищено от ИИ · разрешить дополнения' : 'Защитить от дополнений ИИ' }}</button><button v-for="index in sources" :key="index" class="text-button" @click="$emit('source', index)">Реплика {{ index + 1 }}</button></div>
  </div>
</template>
