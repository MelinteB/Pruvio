/**
 * A registration return may only target a Pruvs bill invitation on this origin.
 * Normalize away all user-provided query parameters and force a one-time join.
 * Do not keep invitation tokens in localStorage or external URLs.
 */
export function invitedBillDestination(raw) {
  if (typeof raw !== 'string' || raw.length > 512 || raw.includes('\\')) return null;
  const match = /^\/join\/([A-Za-z0-9_-]{1,128})\/?(?:\?[^#]*)?$/.exec(raw);
  return match ? `/join/${match[1]}?autojoin=1` : null;
}
