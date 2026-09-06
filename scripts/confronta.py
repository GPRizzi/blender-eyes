#!/usr/bin/env python3
"""Confronta due serie di render e dice cosa è cambiato.

Serve a rispondere alla domanda che conta dopo ogni modifica: "ho migliorato,
peggiorato, o non ho toccato niente?". Senza questo, un agente che lavora su
geometria tira a indovinare.

    confronta.py /tmp/viste/prima /tmp/viste/dopo
    confronta.py prima dopo --soglia 0.5

Produce, per ogni vista: percentuale di pixel cambiati, entità media della
differenza, e un'immagine di differenza che accende in rosso ciò che si è
mosso — quella si apre e si guarda.
"""
from __future__ import annotations
import sys, os, json, argparse

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("Servono numpy e Pillow:  pip3 install numpy pillow")


def carica(p):
    im = Image.open(p).convert('RGB')
    return np.asarray(im).astype(np.int16)


def confronta_vista(a_path, b_path, out_diff, soglia_pixel=8):
    a, b = carica(a_path), carica(b_path)
    if a.shape != b.shape:
        return {'errore': f'dimensioni diverse: {a.shape} vs {b.shape} — '
                          'i render non sono confrontabili, rigenerali con lo stesso --lato'}

    delta = np.abs(a - b).sum(axis=2)          # differenza per pixel, somma RGB
    cambiati = delta > soglia_pixel
    perc = float(cambiati.mean() * 100)
    intensita = float(delta[cambiati].mean()) if cambiati.any() else 0.0

    # Immagine di differenza: l'originale sbiadito con sopra in rosso ciò che cambia.
    base = (a.mean(axis=2) * 0.35).astype(np.uint8)
    vis = np.stack([base, base, base], axis=2)
    vis[cambiati] = [255, 40, 40]
    Image.fromarray(vis).save(out_diff)

    # Dove si concentra il cambiamento: aiuta a capire se è un pezzo o tutto.
    ys, xs = np.where(cambiati)
    zona = None
    if len(ys):
        h, w = delta.shape
        zona = {
            'riquadro_px': [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
            'frazione_area': round(float((xs.max()-xs.min()+1)*(ys.max()-ys.min()+1))/(h*w), 3),
        }

    return {'pixel_cambiati_pct': round(perc, 3),
            'intensita_media': round(intensita, 1),
            'zona': zona, 'diff': out_diff}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('prima'); ap.add_argument('dopo')
    ap.add_argument('--soglia', type=float, default=0.1,
                    help='%% di pixel oltre il quale si considera "cambiato" (default 0.1)')
    ap.add_argument('--out', default=None, help='cartella per le immagini di differenza')
    a = ap.parse_args()

    out = a.out or os.path.join(a.dopo, 'differenze')
    os.makedirs(out, exist_ok=True)

    viste = sorted(f[:-4] for f in os.listdir(a.prima)
                   if f.endswith('.png') and os.path.exists(os.path.join(a.dopo, f)))
    if not viste:
        sys.exit(f"nessuna vista in comune fra {a.prima} e {a.dopo}")

    ris, cambiate = {}, []
    for v in viste:
        r = confronta_vista(os.path.join(a.prima, f'{v}.png'),
                            os.path.join(a.dopo, f'{v}.png'),
                            os.path.join(out, f'{v}-diff.png'))
        ris[v] = r
        if 'errore' not in r and r['pixel_cambiati_pct'] >= a.soglia:
            cambiate.append(v)

    print(f"=== confronto: {os.path.basename(a.prima)} → {os.path.basename(a.dopo)} ===\n")
    for v, r in ris.items():
        if 'errore' in r:
            print(f"  {v:12} ERRORE: {r['errore']}"); continue
        segno = "CAMBIATO" if r['pixel_cambiati_pct'] >= a.soglia else "uguale"
        print(f"  {v:12} {r['pixel_cambiati_pct']:6.2f}% pixel   "
              f"intensità {r['intensita_media']:5.1f}   {segno}")

    print()
    if not cambiate:
        print("VERDETTO: nessuna differenza visibile.")
        print("Se ti aspettavi un cambiamento, NON è stato applicato: non dire che è fatto.")
        esito = 'nessun_cambiamento'
    else:
        print(f"VERDETTO: cambiate {len(cambiate)} viste su {len(ris)}: {', '.join(cambiate)}")
        print(f"Guarda le immagini di differenza in {out}/ — il rosso è ciò che si è mosso.")
        print("Aprile davvero prima di dire che il cambiamento è quello giusto:")
        print("una differenza c'è, ma non è detto che sia quella voluta.")
        esito = 'cambiato'

    rp = os.path.join(out, 'confronto.json')
    with open(rp, 'w') as f:
        json.dump({'prima': a.prima, 'dopo': a.dopo, 'esito': esito,
                   'viste_cambiate': cambiate, 'dettaglio': ris}, f, indent=2, ensure_ascii=False)
    print(f"\nrapporto: {rp}")


if __name__ == '__main__':
    main()
