<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import Pager from './Pager.vue'
import { textPages, replaceTextPage } from './text-pages'
const props = defineProps({ modelValue: { default: '' }, label: String, id: String, disabled: Boolean, placeholder: String })
const emit = defineEmits(['update:modelValue', 'input'])
const box = ref(null), page = ref(0), columns = ref(25), rows = ref(4)
const text = computed(() => String(props.modelValue || ''))
const ranges = computed(() => textPages(text.value, columns.value, rows.value))
const range = computed(() => ranges.value[Math.min(page.value, ranges.value.length - 1)])
const shown = computed(() => text.value.slice(range.value.start, range.value.end))
watch(() => ranges.value.length, n => { page.value = Math.min(page.value, n - 1) })
let observer
function measure() {
  if (!box.value || !box.value.clientWidth || !box.value.clientHeight) return
  const style = getComputedStyle(box.value)
  // Conservative maximum glyph width, with word breaking, also fits Cyrillic.
  columns.value = Math.max(8, Math.floor((box.value.clientWidth - 24) / parseFloat(style.fontSize)))
  rows.value = Math.max(1, Math.floor((box.value.clientHeight - 24) / parseFloat(style.lineHeight)) - 1)
}
async function edit(event) {
  const selection = range.value.start + event.target.selectionStart
  const result = replaceTextPage(text.value, range.value, event.target.value)
  emit('update:modelValue', result); emit('input')
  await nextTick()
  const index = ranges.value.findIndex(r => selection <= r.end)
  page.value = Math.max(0, index)
  await nextTick()
  box.value?.setSelectionRange(Math.max(0, selection - range.value.start), Math.max(0, selection - range.value.start))
}
onMounted(() => { observer = new ResizeObserver(measure); observer.observe(box.value); measure() })
onBeforeUnmount(() => observer?.disconnect())
</script>
<template><div class="paged-text"><textarea ref="box" :id="id" :aria-label="label" :value="shown" :disabled="disabled" :placeholder="placeholder || 'Не уточнено — заполните вручную'" spellcheck="false" @input="edit"></textarea><Pager v-model="page" :total="ranges.length" :label="label ? 'Текст: ' + label : 'Текст'"/></div></template>
