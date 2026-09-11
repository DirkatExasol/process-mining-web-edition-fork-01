/** Insert a step name into an action script's AVAILABILITY clause.
 *
 *  Lets the Action Designer offer a step picker so the exact node name (including
 *  the awkward Greek "Σ" of aggregate steps) never has to be typed by hand. Adds the
 *  step to the AVAILABILITY list, replacing a lone "ALL NODES", and is a no-op if the
 *  step is already listed. The AVAILABILITY block is rewritten as the keyword line
 *  plus one tab-indented value line; other clauses are left untouched. */

const CLAUSES = ['AVAILABILITY', 'SHOW', 'FROM', 'SORT', 'WHERE']

const firstWord = (line: string): string => line.trim().split(/\s+/, 1)[0]?.toUpperCase() ?? ''

/** Same tolerance as actionMatchesNode: fold sigma glyphs, case and whitespace. */
function norm(s: string): string {
  return s
    .normalize('NFKC')
    .replace(/[∑σς]/g, 'Σ')
    .replace(/\s+/g, ' ')
    .trim()
    .toLowerCase()
}

export function insertAvailabilityStep(script: string, step: string): string {
  const clean = step.trim()
  if (!clean) return script
  const lines = script.split(/\r?\n/)

  // Locate the AVAILABILITY keyword line and the extent of its value block.
  const kw = lines.findIndex((l) => firstWord(l) === 'AVAILABILITY')
  if (kw === -1) {
    // No AVAILABILITY clause yet — prepend one.
    return `AVAILABILITY\n\t${clean}\n${script}`
  }
  let end = kw + 1
  while (end < lines.length && !(CLAUSES as string[]).includes(firstWord(lines[end]))) end++

  // Gather the current value: any text after the keyword, then the block lines.
  const inline = lines[kw].trim().slice('AVAILABILITY'.length).trim()
  const blockText = [inline, ...lines.slice(kw + 1, end).map((l) => l.trim())]
    .filter(Boolean)
    .join(' ')
  const existing = blockText
    .split(',')
    .map((s) => s.trim())
    .filter((s) => s && norm(s) !== norm('ALL NODES'))

  if (existing.some((s) => norm(s) === norm(clean))) return script // already listed

  const names = [...existing, clean].join(', ')
  const rebuilt = [`AVAILABILITY`, `\t${names}`]
  return [...lines.slice(0, kw), ...rebuilt, ...lines.slice(end)].join('\n')
}
