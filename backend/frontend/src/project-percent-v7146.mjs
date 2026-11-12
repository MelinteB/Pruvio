/** Allocation percentages as integer basis points (0.01%). Pure utility; no I/O. */
export function distributeRemainder(ids, editedId, typedValue) {
  if (!Array.isArray(ids) || !ids.includes(editedId) || new Set(ids).size !== ids.length) throw new Error('Invalid participant selection');
  const text = String(typedValue ?? '').trim();
  // An incomplete number is allowed while typing, but cannot be saved.
  if (text === '' || !/^(?:\d{1,3})(?:\.\d{0,2})?$/.test(text)) return null;
  const parsed = Number(text);
  if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100) return null;
  const explicit = Math.round(parsed * 100);
  if (ids.length === 1) return {[editedId]: '100.00'};
  const rest = ids.filter(id => id !== editedId);
  const remain = 10000 - explicit;
  const base = Math.floor(remain / rest.length);
  const spill = remain - base * rest.length;
  const allocations = {[editedId]: text};
  rest.forEach((id,i) => {allocations[id] = ((base + (i < spill ? 1 : 0))/100).toFixed(2);});
  return allocations;
}
export function percentagesComplete(ids, getValue) {
  if (!ids.length) return false;
  let total = 0;
  for (const id of ids) {
    const value = String(getValue(id)).trim();
    if (!/^\d+(?:\.\d{1,2})?$/.test(value)) return false;
    const number = Number(value);
    if (!Number.isFinite(number) || number < 0 || number > 100) return false;
    total += Math.round(number * 100);
  }
  return total === 10000;
}
