<script setup>
import { computed } from 'vue'
import { iinDigits, formatIin, normalizePhone, formatPhone } from './patient-input'
defineOptions({ inheritAttrs: false })
const props = defineProps({ modelValue: { type: String, default: '' }, kind: { type: String, default: 'iin' } })
const emit = defineEmits(['update:modelValue'])
const display = computed(() => props.kind === 'phone' ? formatPhone(props.modelValue) : formatIin(props.modelValue))
function input(event) {
  const el = event.target, raw = el.value, cursor = el.selectionStart
  let count = raw.slice(0, cursor).replace(/\D/g, '').length
  const value = props.kind === 'phone' ? normalizePhone(raw) : iinDigits(raw)
  const formatted = props.kind === 'phone' ? formatPhone(value) : formatIin(value)
  if (props.kind === 'phone' && !raw.startsWith('+7') && raw.replace(/\D/g, '').length <= 10) count++
  let position = 0, digits = 0
  while (position < formatted.length && digits < count) { if (/\d/.test(formatted[position])) digits++; position++ }
  el.value = formatted
  el.setSelectionRange(position, position)
  emit('update:modelValue', value)
}
function keydown(event) {
  const el = event.target, backwards = event.key === 'Backspace'
  if ((!backwards && event.key !== 'Delete') || el.selectionStart !== el.selectionEnd) return
  let index = el.selectionStart - (backwards ? 1 : 0)
  if (index < 0 || index >= el.value.length || /\d/.test(el.value[index])) return
  while (index >= 0 && index < el.value.length && !/\d/.test(el.value[index])) index += backwards ? -1 : 1
  if (index < 0 || index >= el.value.length || (props.kind === 'phone' && index < 4)) return
  event.preventDefault()
  el.value = el.value.slice(0, index) + el.value.slice(index + 1)
  el.setSelectionRange(index, index)
  input({ target: el })
}
</script>
<template>
  <input v-bind="$attrs" :type="kind === 'phone' ? 'tel' : 'text'" inputmode="numeric" :value="display" :placeholder="kind === 'phone' ? '+7 (___) ___-__-__' : '______ ______'" :pattern="kind === 'phone' ? '\\+7 \\([0-9]{3}\\) [0-9]{3}-[0-9]{2}-[0-9]{2}' : '[0-9]{6} [0-9]{6}'" @input="input" @keydown="keydown" @blur="$event.target.value = display" @focus="kind === 'phone' && !display && ($event.target.value = '+7 (')">
</template>
