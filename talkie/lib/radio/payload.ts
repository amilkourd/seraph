// Wire formats on room `crew` (contracts/README.md). Shared by mock.ts and livekit.ts so both speak the same bytes.

export const TOPIC_PTT = "ptt";
/** Participant attribute set while a phone (or Gabriel) is on air. Values are strings: "true" / "false". */
export const ATTR_TALKING = "talking";
/** Gabriel's radio agent identity on `crew` (docs/06-gabriel.md). */
export const SERAPH_IDENTITY = "Seraph";

export interface EotMessage {
  kind: "eot";
  speaker: string;
}

/** `{"kind":"eot","speaker":"Tête"}` as UTF-8, for `publishData(bytes, { reliable: true, topic: "ptt" })`. */
export function encodeEot(speaker: string): Uint8Array {
  const msg: EotMessage = { kind: "eot", speaker };
  return new TextEncoder().encode(JSON.stringify(msg));
}

/** Remote identity → label on screen. Gabriel speaks as Seraph; occupant/caller identities never reach `crew`. */
export function speakerLabel(identity: string): string {
  if (identity === SERAPH_IDENTITY || /^(gabriel|agent)/i.test(identity)) return "Seraph";
  return identity;
}
