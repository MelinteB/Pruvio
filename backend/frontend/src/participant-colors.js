/** Soft, readable participant accents. Stable within one bill/session. */
export const PARTICIPANT_PALETTE = [
  {soft:'#e4eeff', edge:'#4978cc', text:'#234b94'},
  {soft:'#eee8ff', edge:'#8465bb', text:'#62458f'},
  {soft:'#ddf3ee', edge:'#418d78', text:'#246a58'},
  {soft:'#fff0df', edge:'#bd8750', text:'#866034'},
  {soft:'#ffe9ee', edge:'#c67893', text:'#88435f'},
  {soft:'#e4f4ff', edge:'#568eae', text:'#356783'},
  {soft:'#f1efdb', edge:'#969351', text:'#696932'},
  {soft:'#f1e6f6', edge:'#a779bc', text:'#77488e'},
  {soft:'#e8f1e7', edge:'#71996d', text:'#4e704b'},
  {soft:'#fcece5', edge:'#bb806b', text:'#8e5644'},
];
export function participantColors(participants = []) {
  const sorted = [...participants].filter(p => p?.participant_id != null)
    .sort((a,b)=>Number(a.participant_id)-Number(b.participant_id));
  return Object.fromEntries(sorted.map((p,i)=>[String(p.participant_id), PARTICIPANT_PALETTE[i % PARTICIPANT_PALETTE.length]]));
}
export function participantStyle(colors, id) {
  const c = colors[String(id)] || PARTICIPANT_PALETTE[0];
  return {'--participant-soft':c.soft,'--participant-edge':c.edge,'--participant-text':c.text};
}
/** Percentage-based stripes. Each owner's share appears at its actual proportion.
 * Unallocated quantities use the neutral background. Never infer paid state.
 */
export function itemShareGradient(item, colors) {
  const quantity = Number(item?.quantity);
  if (!Number.isFinite(quantity) || quantity <= 0) return null;
  const parts = (item.assignments || [])
    .map(a=>({qty:Number(a.quantity),color:(colors[String(a.participant_id)]||PARTICIPANT_PALETTE[0]).soft}))
    .filter(a=>Number.isFinite(a.qty) && a.qty>0);
  if (!parts.length) return null;
  const total=parts.reduce((s,a)=>s+a.qty,0);
  const scale=total>quantity?quantity/total:1;
  let start=0;const stops=[];
  for (const part of parts) {
    const end=Math.min(100,start+part.qty*scale/quantity*100);
    stops.push(`${part.color} ${start.toFixed(2)}% ${end.toFixed(2)}%`);
    start=end;
  }
  if(start<99.99) stops.push(`#f6f8fd ${start.toFixed(2)}% 100%`);
  return `linear-gradient(100deg, ${stops.join(', ')})`;
}
