**Bâtiment d'exercice** — Bâtiment fictif — maquette IFC d'exercice

| | |
|---|---|
| `stair:A` | Escalier A (nord), levels 0, 1, 2, 3, 4, 5 |
| `stair:B` | Escalier B (sud), levels 0, 1, 2, 3, 4, 5 |
| Lift | `room:0.ASC`, `room:1.ASC`, `room:2.ASC`, `room:3.ASC`, `room:4.ASC`, `room:5.ASC` (one per level, not a route) |
| `entrance:E1` | Entrée principale boulevard — level 0, front, opens on `stair:B` |
| `entrance:E2` | Porte latérale rue — level 0, left, opens on `stair:A` |

**RDC** (level 0, 0.0 m, IFC storey RDC)
- Common circulation: `corridor:0`
- Locaux `U0.1` (door P-0.10): 0.10 Hall d'accueil
- Locaux `U0.2` (door P-0.14): 0.14 Salle polyvalente
- Fire-rated doors: EI 30 (escalier A (RDC), escalier B (RDC))
- Materials: facade Pierre de taille; slab Béton armé REI 60; wall Béton armé REI 60; wall Plaque de plâtre sur ossature métallique

**R+1** (level 1, 3.0 m, IFC storey R+1)
- Common circulation: `corridor:1`
- Locaux `U1.1` (door P-1.10): 1.10 Plateau
- Locaux `U1.2` (door P-1.14): 1.14 Plateau
- Fire-rated doors: EI 30 (escalier A (R+1), escalier B (R+1))
- Materials: facade Pierre de taille; slab Béton armé REI 60; wall Béton armé REI 60; wall Plaque de plâtre sur ossature métallique

**R+2** (level 2, 6.0 m, IFC storey R+2)
- Common circulation: `corridor:2`
- Locaux `U2.1` (door P-2.01): 2.01 Bureau
- Locaux `U2.2` (door P-2.02): 2.02 Bureau
- Locaux `U2.3` (door P-2.14): 2.14 Plateau
- Fire-rated doors: EI 30 (escalier A (R+2), escalier B (R+2))
- Materials: facade Pierre de taille; slab Béton armé REI 60; wall Béton armé REI 60; wall Plaque de plâtre sur ossature métallique

**R+3** (level 3, 9.0 m, IFC storey R+3)
- Common circulation: `corridor:3`
- Locaux `U3.1` (door P-3.10): 3.10 Plateau
- Locaux `U3.2` (door P-3.12): 3.12 Réunion
- Logement `U3.3` (door P-3.14): 3.14 Cuisine
- Locaux `U3.4` (door P-3.T): 3.T Local technique
- Technical / risk rooms: 3.T Local technique
- Fire-rated doors: EI 30 (escalier A (R+3), escalier B (R+3), 3.T Local technique)
- Materials: facade Pierre de taille; slab Béton armé REI 60; wall Bloc béton EI 60 (room 3.T); wall Béton armé REI 60; wall Plaque de plâtre sur ossature métallique

**R+4** (level 4, 12.0 m, IFC storey R+4)
- Common circulation: `corridor:4`
- Locaux `U4.1` (door P-4.02): 4.02 Plateau
- Locaux `U4.2` (door P-4.05): 4.05 Réunion
- Locaux `U4.3` (door P-4.14): 4.14 Plateau
- Fire-rated doors: EI 30 (escalier A (R+4), escalier B (R+4))
- Materials: facade Pierre de taille; slab Béton armé REI 60; wall Béton armé REI 60; wall Plaque de plâtre sur ossature métallique

**R+5** (level 5, 15.0 m, IFC storey R+5)
- Common circulation: `corridor:5`
- Locaux `U5.1` (door P-5.01): 5.01 Plateau
- Locaux `U5.2` (door P-5.14): 5.14 Plateau
- Fire-rated doors: EI 30 (escalier A (R+5), escalier B (R+5))
- Materials: facade Pierre de taille; slab Béton armé REI 60; wall Béton armé REI 60; wall Plaque de plâtre sur ossature métallique
