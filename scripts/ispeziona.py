# I fatti misurabili di un modello, in JSON.
#
# Guardare un render dice se una cosa "sembra giusta". Questo dice se lo è:
# misure in metri, scala, origini, vertici sciolti, pezzi staccati, materiali.
# Sono le affermazioni su cui un agente può fare un'asserzione vera o falsa
# invece di esprimere un'impressione.
#
#   blender -b modello.blend -P ispeziona.py -- --out /tmp/fatti.json
#   blender -b modello.blend -P ispeziona.py -- --solo MainBody
#
# Nato da un errore vero: un vertice sciolto a diciassette
# metri faceva risultare MainBody lungo venti metri invece di sette. Il render
# non lo mostrava. Un numero sì.

import bpy, sys, os, json
from mathutils import Vector


def arg(nome, dif=None):
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    return a[a.index('--' + nome) + 1] if '--' + nome in a else dif


OUT   = arg('out', '/tmp/fatti-modello.json')
SOLO  = arg('solo')
LIMITE = int(arg('limite', '400'))       # quanti oggetti dettagliare


def pezzi_staccati(me):
    """Quante isole scollegate ha la mesh. Un modulo dovrebbe essere una sola
    cosa: se ne risultano dodici, o è composito o si è rotto qualcosa."""
    if len(me.vertices) > 200000:
        return None                       # troppo grande, non vale il tempo
    adiac = {i: set() for i in range(len(me.vertices))}
    for e in me.edges:
        a, b = e.vertices
        adiac[a].add(b); adiac[b].add(a)
    visti, isole = set(), 0
    for v in adiac:
        if v in visti:
            continue
        isole += 1
        pila = [v]
        while pila:
            n = pila.pop()
            if n in visti:
                continue
            visti.add(n)
            pila.extend(adiac[n] - visti)
    return isole


def vertici_sciolti(me):
    """Vertici che non appartengono a nessuna faccia: invisibili ma contano
    nell'ingombro e nel baricentro."""
    usati = set()
    for p in me.polygons:
        usati.update(p.vertices)
    return len(me.vertices) - len(usati)


def scheda(o):
    me = o.data
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    dim = mx - mn
    d = {
        'nome': o.name,
        'dimensioni_m': [round(v, 4) for v in dim],
        'centro_m': [round(v, 4) for v in (mn + mx) / 2],
        'origine_m': [round(v, 4) for v in o.matrix_world.translation],
        'scala': [round(v, 5) for v in o.scale],
        'rotazione_gradi': [round(__import__('math').degrees(v), 2) for v in o.rotation_euler],
        'vertici': len(me.vertices),
        'facce': len(me.polygons),
        'materiali': [m.name for m in o.data.materials if m],
        'visibile': o.visible_get(),
        'nascosto_nel_render': o.hide_render,
    }
    d['vertici_sciolti'] = vertici_sciolti(me)
    isole = pezzi_staccati(me)
    if isole is not None:
        d['pezzi_staccati'] = isole
    # L'origine è dentro il proprio ingombro? Se no, ruotare il pezzo lo manda
    # a spasso: è la causa numero uno dei "pezzi nel posto sbagliato".
    org = o.matrix_world.translation
    d['origine_fuori_ingombro'] = not (
        mn.x - 1e-4 <= org.x <= mx.x + 1e-4 and
        mn.y - 1e-4 <= org.y <= mx.y + 1e-4 and
        mn.z - 1e-4 <= org.z <= mx.z + 1e-4)
    d['scala_non_unitaria'] = any(abs(s - 1.0) > 1e-3 for s in o.scale)
    return d


mesh = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if SOLO:
    mesh = [o for o in mesh if SOLO.lower() in o.name.lower()]
    if not mesh:
        print(f"ERRORE: nessun oggetto contiene '{SOLO}'"); sys.exit(2)

schede = [scheda(o) for o in mesh[:LIMITE]]

# Ingombro complessivo
tutti = []
for o in mesh:
    tutti += [o.matrix_world @ Vector(c) for c in o.bound_box]
mn = Vector((min(p.x for p in tutti), min(p.y for p in tutti), min(p.z for p in tutti)))
mx = Vector((max(p.x for p in tutti), max(p.y for p in tutti), max(p.z for p in tutti)))

# Le anomalie: la parte che un agente deve leggere per prima.
anomalie = []
for s in schede:
    if s.get('vertici_sciolti', 0) > 0:
        anomalie.append(f"{s['nome']}: {s['vertici_sciolti']} vertici sciolti (falsano ingombro e baricentro)")
    if s.get('origine_fuori_ingombro'):
        anomalie.append(f"{s['nome']}: origine FUORI dal proprio ingombro (ruotandolo va a spasso)")
    if s.get('scala_non_unitaria'):
        anomalie.append(f"{s['nome']}: scala non unitaria {s['scala']} (applicala prima di esportare)")
    iso = s.get('pezzi_staccati')
    if iso:
        # Quando le isole sono quante le facce, la mesh ha i vertici sdoppiati
        # faccia per faccia: non sono "pezzi staccati", è geometria non saldata.
        # La distinzione conta: separare per pezzi prima di saldare restituisce
        # una faccia e mezza per pezzo invece dei moduli veri.
        rap = iso / s['facce'] if s['facce'] else 0
        s['isole_su_facce'] = round(rap, 2)
        if rap >= 0.4:
            anomalie.append(f"{s['nome']}: {iso} isole su {s['facce']} facce "
                            f"(rapporto {rap:.2f}) — geometria NON SALDATA. Salda i "
                            f"vertici coincidenti prima di separare o misurare, "
                            f"altrimenti 'separa per pezzi' restituisce schegge")
            s['vertici_sdoppiati'] = True
        elif iso > 20:
            anomalie.append(f"{s['nome']}: {iso} pezzi davvero staccati")
    if s['facce'] == 0:
        anomalie.append(f"{s['nome']}: ZERO facce (oggetto vuoto)")

fatti = {
    'file': bpy.data.filepath,
    'oggetti_mesh': len(mesh),
    'oggetti_dettagliati': len(schede),
    'facce_totali': sum(len(o.data.polygons) for o in mesh),
    'vertici_totali': sum(len(o.data.vertices) for o in mesh),
    'ingombro_scena_m': {
        'min': [round(v, 3) for v in mn],
        'max': [round(v, 3) for v in mx],
        'dimensioni': [round(v, 3) for v in (mx - mn)],
    },
    'materiali_nel_file': len(bpy.data.materials),
    'anomalie': anomalie,
    'oggetti': schede,
}

os.makedirs(os.path.dirname(OUT) or '.', exist_ok=True)
with open(OUT, 'w') as f:
    json.dump(fatti, f, indent=2, ensure_ascii=False)

print(f"\n=== {os.path.basename(bpy.data.filepath) or 'scena'} ===")
print(f"mesh: {len(mesh)}   facce: {fatti['facce_totali']:,}   materiali: {fatti['materiali_nel_file']}")
d = fatti['ingombro_scena_m']['dimensioni']
print(f"ingombro: {d[0]} x {d[1]} x {d[2]} m")
if anomalie:
    print(f"\nANOMALIE ({len(anomalie)}):")
    for a in anomalie[:25]:
        print("  ⚠ " + a)
    if len(anomalie) > 25:
        print(f"  … e altre {len(anomalie) - 25}")
else:
    print("\nnessuna anomalia rilevata")
print(f"\nfatti completi: {OUT}")
