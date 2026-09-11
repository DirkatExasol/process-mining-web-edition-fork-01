// Pretty-print the server-generated SQL for display only (the executed query is
// unchanged). It breaks before the major clause keywords and indents sub-SELECTs by
// parenthesis depth, so a long semi-join / nested subquery no longer sits on one row.
//
// IMPORTANT — horizontal spacing is preserved exactly. Every gap between two tokens is
// reproduced from whether the *source* had whitespace there (`sp`), so a required space
// (e.g. in "PROJECT_ID = 'x'") is never lost and two tokens are never merged. String
// literals are protected before tokenising, so spaces/commas/parens inside them are
// untouched. Function-call parens (COUNT(*), OVER (…)) and BETWEEN x AND y stay inline —
// only real sub-SELECT parens introduce a new indented block.

interface Tok {
  v: string
  /** True when whitespace preceded this token in the source. */
  sp: boolean
}

const KW_BREAK = new Set(['SELECT', 'FROM', 'WHERE', 'HAVING', 'LIMIT', 'AND', 'OR', 'ON', 'JOIN', 'UNION'])
// A JOIN preceded by one of these is the second word of a compound join, so the break
// already happened before the qualifier — don't break again.
const JOIN_QUALIFIERS = new Set(['LEFT', 'RIGHT', 'INNER', 'CROSS', 'FULL'])
// Two-word clause openers — break before the first word when the second follows.
const KW_PAIR = new Map([
  ['GROUP', 'BY'],
  ['ORDER', 'BY'],
  ['LEFT', 'JOIN'],
  ['RIGHT', 'JOIN'],
  ['INNER', 'JOIN'],
  ['CROSS', 'JOIN'],
  ['FULL', 'JOIN'],
])

// Private-use sentinels wrapping a literal's index — survive tokenisation as one word
// and can never collide with a real number (LIMIT 5) on restore.
const LIT_OPEN = ''
const LIT_CLOSE = ''

function tokenize(sql: string): Tok[] {
  const toks: Tok[] = []
  let word = ''
  let wordSp = false
  let pendingSpace = false
  const flush = () => {
    if (word) {
      toks.push({ v: word, sp: wordSp })
      word = ''
    }
  }
  for (const c of sql) {
    if (c === ' ' || c === '\t' || c === '\n' || c === '\r') {
      flush()
      pendingSpace = true
      continue
    }
    if (c === '(' || c === ')' || c === ',') {
      flush()
      toks.push({ v: c, sp: pendingSpace })
      pendingSpace = false
      continue
    }
    if (!word) {
      wordSp = pendingSpace
      pendingSpace = false
    }
    word += c
  }
  flush()
  return toks
}

export function formatSql(sql: string): string {
  // 1) Protect string literals ('' escapes included) so their contents are inert.
  const lits: string[] = []
  const protectedSql = sql.replace(/'(?:''|[^'])*'/g, (m) => {
    lits.push(m)
    return `${LIT_OPEN}${lits.length - 1}${LIT_CLOSE}`
  })

  const toks = tokenize(protectedSql)
  if (!toks.length) return ''

  const lines: string[] = []
  let cur = ''
  let indent = 0
  const stack: ('sub' | 'expr')[] = []
  let betweenPending = false // suppress the AND inside "BETWEEN x AND y"

  const newline = () => {
    lines.push(cur.replace(/[ \t]+$/, ''))
    cur = '  '.repeat(indent)
  }
  const emit = (v: string, sp: boolean) => {
    if (cur.trim() !== '' && sp) cur += ' '
    cur += v
  }

  for (let k = 0; k < toks.length; k++) {
    const tk = toks[k]
    const U = tk.v.toUpperCase()
    const next = toks[k + 1]
    const inExpr = stack.length > 0 && stack[stack.length - 1] === 'expr'

    if (tk.v === '(') {
      const isSub = next != null && next.v.toUpperCase() === 'SELECT'
      emit('(', tk.sp)
      stack.push(isSub ? 'sub' : 'expr')
      if (isSub) {
        indent++
        newline()
      }
      continue
    }
    if (tk.v === ')') {
      const kind = stack.pop()
      if (kind === 'sub') {
        indent = Math.max(0, indent - 1)
        if (cur.trim() !== '') newline()
      }
      emit(')', false)
      continue
    }

    if (U === 'BETWEEN') betweenPending = true

    let isBreak = false
    if (!inExpr) {
      const prev = toks[k - 1]
      if (U === 'AND' && betweenPending) {
        betweenPending = false // this AND belongs to BETWEEN — keep it inline
      } else if (U === 'JOIN' && prev && JOIN_QUALIFIERS.has(prev.v.toUpperCase())) {
        // second word of "LEFT JOIN" etc. — the break already happened before it
      } else if (KW_BREAK.has(U)) {
        isBreak = true
      } else if (KW_PAIR.get(U) && next && next.v.toUpperCase() === KW_PAIR.get(U)) {
        isBreak = true
      }
    }

    if (isBreak && cur.trim() !== '') newline()
    emit(tk.v, tk.sp)
  }
  newline()

  // 2) Restore the protected literals.
  const restore = new RegExp(`${LIT_OPEN}(\\d+)${LIT_CLOSE}`, 'g')
  return lines.join('\n').replace(restore, (_, d) => lits[Number(d)])
}
