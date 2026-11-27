/** Progress covers prose only; short articles complete as their ending enters view. */
export function readingProgress(top: number, height: number, viewportHeight: number): number {
  if (![top, height, viewportHeight].every(Number.isFinite) || viewportHeight <= 0) return 0
  const offset = Math.min(120, viewportHeight / 2)
  const available = viewportHeight - offset
  const fraction = height > available
    ? (offset - top) / (height - available)
    : (viewportHeight - top - height) / Math.max(1, height)
  return Math.round(Math.min(1, Math.max(0, fraction)) * 100)
}
