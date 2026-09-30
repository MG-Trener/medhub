// Offsets preserve whitespace and the original text when editing a page.
export function textPages(text = '', columns = 40, rows = 6) {
  const pages = []; let start = 0, line = 0, col = 0
  columns = Math.max(1, columns); rows = Math.max(1, rows)
  for (let i = 0; i < text.length; i++) {
    if (text[i] === '\n') { line++; col = 0 }
    else if (++col >= columns) { line++; col = 0 }
    if (line >= rows) { pages.push({ start, end: i + 1 }); start = i + 1; line = 0; col = 0 }
  }
  if (start < text.length || !pages.length) pages.push({ start, end: text.length })
  return pages
}
export function replaceTextPage(text, range, replacement) {
  return text.slice(0, range.start) + replacement + text.slice(range.end)
}
