**Immeuble d'habitation (maquette TU Wien)** — Maquette IFC réelle (TU Wien, CC BY 4.0) — adresse d'exercice
Source: `RealWorldTestModel-EscapeRouteAnalysis-ZDB-v2.ifc` (TU Wien, Research Unit Digital Building Process — CC BY 4.0).

| | |
|---|---|
| `stair:A` | Escalier A, levels -1, 0, 1, 2, 3 |
| Lift | `room:-1.02`, `room:0.03`, `room:1.02`, `room:2.02`, `room:3.01` (one per level, not a route) |
| `entrance:E1` | Porte d'entrée, hall de l'escalier — level 0, front, opens on `corridor:0` |
| `entrance:E2` | Porte de garage, rampe (sous-sol) — level -1, left, opens on `room:-1.03` |
| Second route | Un seul escalier, encloisonné et mis en surpression ; second moyen de sauvetage par la façade (balcons, terrasses) avec les échelles des pompiers. |

**R-1** (level -1, -3.3 m, IFC storey UG1)
- Common circulation: `corridor:-1`
- Locaux `U-1.1` (door P-1-2): -1.01 Caves
- Locaux `U-1.2` (door P-1-5): -1.03 Rampe d'accès, -1.05 Place de parking, -1.07 Place de parking, -1.09 Place de parking, -1.10 Place de parking, -1.11 Garage, -1.12 Place de parking, -1.13 Place de parking, -1.14 Place de parking, -1.15 Place de parking
- Locaux `U-1.3` (door P-1-1): -1.04 Local poussettes
- Locaux `U-1.4` (door P-1-6): -1.06 Local électrique, -1.08 Local technique
- Technical / risk rooms: -1.06 Local électrique, -1.08 Local technique, -1.11 Garage
- Fire-rated doors: EI2 30-C-Sm (-1.04 Local poussettes, -1.01 Caves, -1.06 Local électrique ×2, -1.11 Garage)
- Materials: facade Béton armé (dalle du garage) REI 90; facade Béton armé (mur) REI 90; facade Béton armé (mur du garage) REI 90; slab Béton armé (dalle); wall Aluminium; wall Béton armé (mur) REI 90

**RDC** (level 0, -0.22 m, IFC storey EG)
- Common circulation: `corridor:0`
- Logement `U0.1` (door P0-18): 0.02 Chambre, 0.04 Salle de bain, 0.06 Entrée, 0.07 Buanderie, 0.09 Séjour-cuisine; outdoor 0.01, 0.14
- Logement `U0.2` (door P0-17): 0.08 Salle de bain, 0.10 Buanderie, 0.11 Salle de bain, 0.12 WC, 0.13 Entrée, 0.15 Chambre, 0.16 Circulation, 0.17 Chambre, 0.18 Chambre, 0.19 Séjour-cuisine; outdoor 0.20
- Technical / risk rooms: 0.05 Local poubelles
- Fire-rated doors: EI2 30-C-Sm (0.13 Entrée, 0.06 Entrée); EI 30 (Porte-fenêtre 0.20 Terrasse ×7, Porte-fenêtre 0.14 Terrasse, Porte-fenêtre 0.01 Terrasse); EI2 30-C (E1)
- Materials: facade Aluminium; facade Béton armé (mur) REI 90; slab Béton armé (dalle); slab Béton armé (dalle du garage); wall Béton armé (mur); wall Béton armé (mur) REI 90

**R+1** (level 1, 2.74 m, IFC storey OG1)
- Common circulation: `corridor:1`
- Logement `U1.1` (door P1-48): 1.01 Chambre, 1.03 Salle de bain, 1.04 Entrée, 1.06 Buanderie, 1.08 Séjour-cuisine; outdoor 1.05
- Logement `U1.2` (door P1-49): 1.07 Salle de bain, 1.09 Buanderie, 1.10 Salle de bain, 1.11 Chambre, 1.12 WC, 1.13 Entrée, 1.14 Circulation, 1.15 Chambre, 1.16 Chambre, 1.17 Séjour-cuisine; outdoor 1.18
- Ladder rescue points: `ladder:1.05`, `ladder:1.18`
- Fire-rated doors: EI 30 (Porte-fenêtre 1.05 Balcon, Porte-fenêtre 1.18 Balcon ×2); EI2 30-C-Sm (1.04 Entrée, 1.13 Entrée)
- Materials: slab Béton armé (dalle); wall Béton armé (mur) REI 90

**R+2** (level 2, 5.7 m, IFC storey DG1)
- Common circulation: `corridor:2`
- Logement `U2.1` (door P2-67): 2.01 Chambre, 2.03 Salle de bain, 2.04 Entrée, 2.06 Buanderie, 2.08 Séjour-cuisine; outdoor 2.05
- Logement `U2.2` (door P2-59): 2.07 Salle de bain, 2.09 Buanderie, 2.10 Salle de bain, 2.11 WC, 2.12 Entrée, 2.13 Chambre, 2.14 Circulation, 2.15 Chambre, 2.16 Séjour-cuisine; outdoor 2.17
- Ladder rescue points: `ladder:2.05`, `ladder:2.17`
- Fire-rated doors: EI 30 (Porte-fenêtre 2.05 Balcon, Porte-fenêtre 2.17 Balcon); EI2 30-C-Sm (2.12 Entrée, 2.04 Entrée)
- Materials: roof Béton armé (toiture) REI 90; roof Béton armé (dalle) REI 90; slab Béton armé (dalle); wall Béton armé (mur) REI 90

**R+3** (level 3, 8.66 m, IFC storey DG2)
- Common circulation: `corridor:3`
- Logement `U3.1` (door P3-72): 3.02 Chambre, 3.03 Circulation, 3.05 WC, 3.06 Salle de bain, 3.10 Séjour-cuisine, 3.12 Chambre, 3.T Buanderie; outdoor 3.04, 3.07, 3.08
- Ladder rescue points: `ladder:3.04`, `ladder:3.08`, `ladder:3.07`
- Fire-rated doors: EI2 30-C-Sm (3.03 Circulation); EI 30 (Porte-fenêtre 3.08 Terrasse, Porte-fenêtre 3.07 Terrasse, Porte-fenêtre 3.04 Terrasse)
- Materials: roof Béton armé (toiture) REI 90; roof Béton armé (dalle) REI 90; wall Béton armé (mur) REI 90
