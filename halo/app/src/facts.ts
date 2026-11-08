// The vue de secours' lines: for each moment, the few facts that matter, as short imperative lines (Amil's rules:
// one line each, plain words, no sources on screen). Read from the state only; nothing is decided here.
import { State } from './seraph';

export type Line = { text: string; tone?: 'ink' | 'warn' | 'fire' | 'life' | 'water' | 'dim'; big?: boolean };

const STATUS: Record<string, string> = { clear: 'dégagé', smoke: 'fumée', blocked: 'bloqué', unknown: '?' };

function levelLabel(s: State, n?: number) {
  const l = (s?.building?.levels ?? []).find((x: any) => x.level === n);
  return l ? l.label : n === undefined ? '' : `N${n}`;
}
const hhmm = (iso: string) => { const d = new Date(iso); return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`; };

export function factsFor(moment: string, s: State | null): Line[] {
  if (!s) return [{ text: 'En attente de Seraph', tone: 'dim' }];
  const b = s.building ?? {}, hz: any[] = b.hazards ?? [], routes: any[] = s.routes ?? [];
  const smokyStairs = (b.stairs ?? []).filter((x: any) => x.status !== 'clear');
  const fire = hz.find(h => h.kind === 'fire');
  switch (moment) {
    case 'approach': {
      const best = b.approach?.best_entrance_id;
      const stair = (routes.find(r => r.purpose === 'approach')?.via ?? []).find((n: string) => n.startsWith('stair:'))?.split(':')[1];
      const pei = (b.hydrants ?? [])[0];
      return [
        best && { text: `Entrez par ${best}`, big: true },
        stair && { text: `Montez esc. ${stair}` },
        ...smokyStairs.map((x: any) => ({ text: `Esc. ${x.id} ${STATUS[x.status] ?? x.status}`, tone: 'warn' })),
        pei?.distance_m && { text: `PEI ${pei.distance_m} m`, tone: 'water' },
      ].filter(Boolean) as Line[];
    }
    case 'inside_route': {
      const r = routes.find(x => x.purpose === 'to_victim') ?? routes.find(x => x.purpose === 'evacuation');
      const evac = r?.purpose === 'evacuation';
      const room = r && (evac ? r.from : r.to)?.startsWith('room:') ? (evac ? r.from : r.to).split(':')[1] : null;
      const stair = r?.via?.find((n: string) => n.startsWith('stair:'))?.split(':')[1];
      return [
        room && { text: `${evac ? 'Évacuez' : 'Allez en'} ${room}`, big: true, tone: evac ? 'ink' : 'life' },
        stair && { text: `Par esc. ${stair}` },
        hz.find(h => h.kind === 'smoke' && h.where?.room === 'corridor') && { text: 'Fumée circulation', tone: 'warn' },
        fire && { text: `Feu ${fire.where?.room ?? levelLabel(s, fire.where?.level)}`, tone: 'fire' },
      ].filter(Boolean) as Line[];
    }
    case 'occupants': {
      const occ: any[] = (s.occupants ?? []).filter((o: any) => o.status !== 'safe_outside');
      const n = occ.reduce((k, o) => k + (o.people_count || 1), 0);
      return [
        { text: `${n} dedans`, big: true, tone: 'life' },
        ...occ.filter(o => o.status === 'needs_help' || o.status === 'trapped').map(o => ({ text: `${o.room} ${o.mobility_issue ? 'PMR' : 'à sortir'}`, tone: 'fire' as const })),
        ...occ.filter(o => o.heading_to && smokyStairs.some((x: any) => o.heading_to === `stair:${x.id}`)).map(o => ({ text: `${o.room} → esc. ${o.heading_to.split(':')[1]}`, tone: 'warn' as const })),
        ...occ.filter(o => o.status === 'no_answer' || o.status === 'unknown').map(o => ({ text: `${o.room} ?`, tone: 'dim' as const })),
      ].slice(0, 4);
    }
    case 'team_engaged': {
      const t = (s.crew?.teams ?? []).find((x: any) => x.status === 'engaged' || x.status === 'exiting');
      if (!t) return [{ text: 'Aucun binôme engagé', tone: 'dim' }];
      return [
        { text: `${t.id} · ${levelLabel(s, t.location?.level)}`, big: true },
        t.exit_by && { text: `Sortie ${hhmm(t.exit_by)}` },
        t.pressure_bar_start && { text: `${t.pressure_bar_start} bar au départ`, tone: 'dim' },
      ].filter(Boolean) as Line[];
    }
    case 'dispatch':
      return [
        fire && { text: `Feu ${levelLabel(s, fire.where?.level)}`, big: true, tone: 'fire' },
        s.incident?.address && { text: String(s.incident.address).split(',')[0] },
        s.incident?.address && { text: String(s.incident.address).split(',').slice(1).join(',').trim() },
      ].filter(Boolean) as Line[];
    case 'report':
      return [{ text: 'Rapport en cours', big: true }];
    default:
      return [{ text: 'Demande du COS', big: true }];
  }
}
