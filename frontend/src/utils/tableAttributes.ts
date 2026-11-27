/** Bound merged cells before ProseMirror allocates its table map. */
export function tableSpan(value: unknown): number {
  const text = String(value ?? '')
  return /^[1-9]\d?$/.test(text) && Number(text) <= 50 ? Number(text) : 1
}
