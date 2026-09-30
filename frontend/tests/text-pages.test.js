import test from 'node:test'
import assert from 'node:assert/strict'
import { textPages, replaceTextPage } from '../src/text-pages.js'
test('pagination preserves Cyrillic, whitespace and empty paragraphs exactly', () => {
  const text = ('Жалобы и анамнез\n\n  Со слов пациента.\n').repeat(100)
  const pages = textPages(text, 24, 5)
  assert.equal(pages.map(p => text.slice(p.start, p.end)).join(''), text)
  for (const p of pages) assert.ok(p.end - p.start <= 120)
})
test('editing a page never replaces the hidden remainder', () => {
  const text = 'начало середина конец', ranges = textPages(text, 7, 1)
  assert.equal(replaceTextPage(text, ranges[1], 'правка'), text.slice(0, 7) + 'правка' + text.slice(14))
  assert.deepEqual(textPages(''), [{ start: 0, end: 0 }])
})
