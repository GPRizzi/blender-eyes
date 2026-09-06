---
name: blender-vista
description: Dà occhi e metro a chi lavora su modelli 3D Blender senza poterli guardare. Rende da punti di vista fissi e ripetibili, misura la geometria in metri, confronta prima/dopo e dice se una modifica ha davvero fatto quello che doveva. Usala ogni volta che tocchi un .blend, una mesh, una posizione, una scala o un materiale, e prima di dire che una correzione 3D è fatta.
argument-hint: "[rendi|fatti|confronta|ciclo] <file.blend>"
---

# Blender — vedere quello che si sta facendo

Il problema che risolve: lavorando su geometria **non vedi il risultato**, e
finisci per dire "fatto" basandoti su cosa credi sia successo. Su un modello 3D
è il modo più rapido di accumulare disastri silenziosi.

Questa skill dà tre cose: **occhi** (render ripetibili che puoi aprire e
guardare), **un metro** (misure vere in metri su cui asserire), e **una
memoria** (confronto prima/dopo che dice se hai cambiato qualcosa davvero).

Comando: `~/.claude/skills/blender-vista/vista`

---

## Le tre operazioni

### `vista rendi <file.blend>` — guarda

```bash
~/.claude/skills/blender-vista/vista rendi modello.blend
~/.claude/skills/blender-vista/vista rendi modello.blend --solo MainBody --viste fronte,alto,iso
~/.claude/skills/blender-vista/vista rendi modello.blend --etichetta prima
```

Rende in `.vista/` da viste fisse (`fronte, retro, lato, sinistra, alto, sotto,
iso`), camera ortografica, luce fissa. Due render fatti a ore di distanza sono
sovrapponibili pixel su pixel: è questo che rende sensato il confronto.

**Poi APRI I PNG con lo strumento di lettura file.** Renderli e non guardarli
non serve a niente — è l'unico passo che non puoi delegare a un numero. La vista
`iso` è quella che rivela di più la forma d'insieme.

Una scena da 216 oggetti e 3,3 milioni di facce rende in ~13 secondi.

### `vista fatti <file.blend>` — misura

```bash
~/.claude/skills/blender-vista/vista fatti modello.blend --solo MainBody
```

Stampa le anomalie e scrive un JSON con, per ogni oggetto: dimensioni in metri,
centro, origine, scala, rotazione, facce, materiali, vertici sciolti, isole.

Rileva da solo i guai che il render **non** mostra:

| Anomalia | Perché conta |
|---|---|
| vertici sciolti | non si vedono ma falsano ingombro e baricentro: uno solo, lontano, fa risultare un modulo lungo il triplo |
| origine fuori dall'ingombro | ruotando il pezzo, questo parte per la tangente |
| scala non unitaria | va applicata prima di esportare, o all'import le misure saltano |
| geometria non saldata | "separa per pezzi" restituisce schegge invece dei pezzi veri |
| zero facce | oggetto vuoto che sembra esistere |

### `vista confronta <prima> <dopo>` — verifica

```bash
~/.claude/skills/blender-vista/vista confronta .vista/prima .vista/dopo
```

Per ogni vista: percentuale di pixel cambiati, entità della differenza, e
un'immagine che accende **in rosso** ciò che si è mosso.

Il verdetto che conta di più è quello negativo: *"nessuna differenza visibile"*
significa che la tua modifica **non è stata applicata**, e non devi dire che è
fatta. Succede più spesso di quanto sembri — script che gira sul file sbagliato,
modifica non salvata, oggetto nascosto al render.

---

## Il ciclo da seguire quando modifichi un modello

1. `vista rendi <blend> --etichetta prima` e **guarda** le immagini
2. `vista fatti <blend>` — annota le anomalie di partenza
3. fai la modifica
4. `vista rendi <blend> --etichetta dopo`
5. `vista confronta .vista/prima .vista/dopo`
6. **apri l'immagine di differenza** e verifica che il rosso sia dove volevi
7. `vista fatti <blend>` di nuovo: le anomalie che volevi togliere sono sparite?
   ne sono comparse di nuove?

Solo dopo il 7 puoi dire che è fatto. Prima è un'opinione.

## Note pratiche

- Blender: `/Applications/Blender.app/Contents/MacOS/Blender`, sovrascrivibile
  con `$BLENDER`.
- I render vanno in `.vista/` dentro il progetto: aggiungila a `.gitignore`.
- Su file enormi usa `--solo <nome>` per lavorare su un pezzo: rende in
  secondi invece che in minuti.
- `--lato 1400` per guardare un dettaglio; il default 900 basta per la forma.
- Il confronto richiede render della **stessa misura**: se cambi `--lato` fra
  prima e dopo, il confronto te lo dice invece di darti un numero falso.

## Cosa non fa

Non giudica l'estetica e non sa cosa "dovrebbe" sembrare un oggetto. Ti fa
vedere e misurare: il giudizio resta tuo, ma finalmente è un giudizio informato
invece di una congettura.
