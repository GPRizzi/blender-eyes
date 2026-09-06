#!/usr/bin/env python3
"""Compare two sets of renders and say what changed.

It answers the question that matters after every edit: "did I improve this,
make it worse, or not touch it at all?". Without it, an agent working on
geometry is guessing.

    diff.py /tmp/views/before /tmp/views/after
    diff.py before after --threshold 0.5

For each view it reports: percentage of changed pixels, average magnitude of
the difference, and a diff image that lights up in red whatever moved — that
is the one you open and look at.
"""
from __future__ import annotations
import sys, os, json, argparse

try:
    import numpy as np
    from PIL import Image
except ImportError:
    sys.exit("Needs numpy and Pillow:  pip3 install numpy pillow")


def load(p):
    im = Image.open(p).convert('RGB')
    return np.asarray(im).astype(np.int16)


def compare_view(a_path, b_path, out_diff, pixel_threshold=8):
    a, b = load(a_path), load(b_path)
    if a.shape != b.shape:
        return {'error': f'different sizes: {a.shape} vs {b.shape} — '
                          'these renders are not comparable, regenerate with the same --side'}

    delta = np.abs(a - b).sum(axis=2)          # per-pixel difference, RGB summed
    changed = delta > pixel_threshold
    pct = float(changed.mean() * 100)
    magnitude = float(delta[changed].mean()) if changed.any() else 0.0

    # Diff image: the original, faded, with whatever changed painted red on top.
    base = (a.mean(axis=2) * 0.35).astype(np.uint8)
    vis = np.stack([base, base, base], axis=2)
    vis[changed] = [255, 40, 40]
    Image.fromarray(vis).save(out_diff)

    # Where the change concentrates: tells you if it is one part or everything.
    ys, xs = np.where(changed)
    region = None
    if len(ys):
        h, w = delta.shape
        region = {
            'box_px': [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())],
            'area_fraction': round(float((xs.max()-xs.min()+1)*(ys.max()-ys.min()+1))/(h*w), 3),
        }

    return {'changed_pct': round(pct, 3),
            'magnitude': round(magnitude, 1),
            'region': region, 'diff': out_diff}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('before'); ap.add_argument('after')
    ap.add_argument('--threshold', type=float, default=0.1,
                    help='%% of pixels above which a view counts as changed (default 0.1)')
    ap.add_argument('--out', default=None, help='folder for the diff images')
    a = ap.parse_args()

    out = a.out or os.path.join(a.after, 'diffs')
    os.makedirs(out, exist_ok=True)

    views = sorted(f[:-4] for f in os.listdir(a.before)
                   if f.endswith('.png') and os.path.exists(os.path.join(a.after, f)))
    if not views:
        sys.exit(f"no views in common between {a.before} e {a.after}")

    results, changed_views = {}, []
    for v in views:
        r = compare_view(os.path.join(a.before, f'{v}.png'),
                            os.path.join(a.after, f'{v}.png'),
                            os.path.join(out, f'{v}-diff.png'))
        results[v] = r
        if 'error' not in r and r['pixel_cambiati_pct'] >= a.threshold:
            changed_views.append(v)

    print(f"=== diff: {os.path.basename(a.before)} -> {os.path.basename(a.after)} ===\n")
    for v, r in results.items():
        if 'error' in r:
            print(f"  {v:12} ERROR: {r['error']}"); continue
        mark = "CHANGED" if r['changed_pct'] >= a.threshold else "same"
        print(f"  {v:12} {r['changed_pct']:6.2f}% pixels   "
              f"magnitude {r['magnitude']:5.1f}   {mark}")

    print()
    if not changed_views:
        print("VERDICT: no visible difference.")
        print("If you expected a change, it was NOT applied. Do not report it as done.")
        outcome = 'no_change'
    else:
        print(f'VERDICT: {len(changed_views)} of {len(results)} views changed: '
              f'{", ".join(changed_views)}')
        print(f"Look at the diff images in {out}/ — red is what moved.")
        print("Actually open them before calling the change correct:")
        print("there is a difference, but not necessarily the one you wanted.")
        outcome = 'changed'

    rp = os.path.join(out, 'diff.json')
    with open(rp, 'w') as f:
        json.dump({'before': a.before, 'after': a.after, 'outcome': outcome,
                   'changed_views': changed_views, 'detail': results}, f, indent=2, ensure_ascii=False)
    print(f"\nreport: {rp}")


if __name__ == '__main__':
    main()
