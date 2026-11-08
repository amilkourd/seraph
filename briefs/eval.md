# Brief — `eval` session · `eval/` (start ~05:00)

Read first: `CLAUDE.md`, `contracts/fixtures/` (radio, calls), `contracts/api.md` (metrics, replay).

## Goal
The numbers for the last slide and for Q&A, measured, not claimed.
1. **Extraction accuracy:** replay `radio.jsonl` and `calls.jsonl` through Seraph (text, no audio): % of events with
   the right type, % of fields right, catches and gates triggered as expected.
2. **Speech:** record 20 crew lines and 10 call lines on the phones in a noisy room (fr/en/es), run them through
   Gabriel/Gladia: word error rate on the key words (levels, rooms, stairs, numbers), language detection.
3. **Latency:** from Seraph's `metric` events over 3 rehearsals: radio end → spoken answer, call fact → crew line,
   view request → view on Halo (Devin), each Rosetta endpoint live vs cache.
4. **Coverage:** endpoints live at least once (yes/no + time).

Output `eval/results.json` (read by dashboard `/eval`) and `eval/results.md` (a 6-line table for the slide). Never
round in our favour; show n.
