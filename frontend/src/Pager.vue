<script setup>
import { computed } from 'vue'
const props = defineProps({ modelValue: { default: 0 }, total: { default: 0 }, size: { default: 1 }, label: { default: 'Страница' } })
defineEmits(['update:modelValue'])
const count = computed(() => Math.max(1, Math.ceil(props.total / props.size)))
</script>
<template><nav class="pager" :aria-label="label"><button type="button" :disabled="modelValue <= 0" @click="$emit('update:modelValue', modelValue - 1)" :aria-label="label + ': назад'">←</button><span>{{ label }} {{ Math.min(modelValue + 1, count) }} / {{ count }}</span><button type="button" :disabled="modelValue >= count - 1" @click="$emit('update:modelValue', modelValue + 1)" :aria-label="label + ': далее'">→</button></nav></template>
