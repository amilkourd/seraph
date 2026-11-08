# Vision

## The problem
When firefighters are dispatched, the information that would save the most time already exists, on screens they
can't use from a truck: the building on Maps and Earth, the plan posted at the door, the risks on Géorisques, the
list of occupants in the building manager's software, the 112 calls coming in, the dispatch record. Nobody connects
them in time, and nobody connects them to the people still inside.

**Grenfell Tower, London, 2017: 72 dead.** The public inquiry criticised how what callers told the control room was
handled and passed to the commanders on the ground, the lack of an evacuation plan, and the failure to lift « stay
put » while the stairs were still passable. The information existed. It didn't reach the crew, and the decisions
didn't reach the residents.

## What Seraph does
- **On the way:** reads every source in parallel (Rosetta, computer use), and gives the crew a 20-second briefing on
  the radio while Halo draws the way in on the wrist.
- **With the people inside:** Gabriel calls every occupant and takes the incident's 112 calls, one agent per call,
  in every language, and turns each call into a line for the crew. Commander decisions go back to every caller at
  once.
- **During the attack:** Halo shows the right thing at the right moment (the way in, the way up, who is where, the
  air left), built live by Devin through Silex, and Gabriel says the same thing on the radio.
- **After:** the report fills itself in the legacy software.

## Why computer use is the moat
Fire services, building managers and public sites run software with no API, owned by others. Integrations take
years (the firefighters' and health ministry's victim systems took years to link). Seraph uses every screen as it
is, on day one: **« Seraph transforme n'importe quel écran en API. »** Rosetta's endpoints are that API, and Silex
adds a new one when a new source shows up.

## Partners, used for real
- **H**: Holo navigates real websites and legacy apps and points at doors, stairs and hydrants on screenshots. The
  agent cam is on the big screen the whole time.
- **Gladia**: every call and the crew channel at once, French/English/Spanish with code-switching, fire jargon and
  radio formulas (custom vocabulary and spelling), noisy audio (enhancer), and the caller's emotion: distress, fear or
  pain in the voice moves that call up the list.
- **Devin**: builds the Halo view for this exact moment, and compiles new Rosetta endpoints. Not a coding
  assistant: a tool factory inside the incident.
- **Linkup**: when a question has no endpoint, Linkup finds the official pages (official hosts only) and the H agent
  opens one on screen. Search finds where, computer use reads what.

## What works (patterns from firefighter/emergency projects, 2024–2026)
A real disaster and a hard number up front; participants join in (they get called, they hold the radio); two screens
(field device + commander); a human stays in charge, enforced in code; partner tools used for real. Computer use is
almost absent from these projects: that's our opening. Details and sources: `docs/09-research.md`.

## Lines to use
- « Des minutes de route, zéro seconde d'information. Seraph remplit ce temps. »
- « Le plan existe : sur papier à la porte. Personne ne l'a dans la fumée. »
- « Le commandant décide, Seraph transmet. »
- « Seraph transforme n'importe quel écran en API. »
