# Rende un file .blend da punti di vista fissi e RIPETIBILI.
#
# Il punto non è fare belle immagini: è fare immagini *confrontabili*. Stessa
# camera, stessa luce, stessa inquadratura ogni volta — così la differenza fra
# un render di prima e uno di dopo è dovuta al modello e non al caso.
#
# Serve a un agente che lavora su geometria senza poterla guardare: rende, poi
# apre il PNG e vede davvero cosa ha combinato.
#
#   blender -b modello.blend -P rendi.py -- --cartella /tmp/viste
#   blender -b modello.blend -P rendi.py -- --solo MainBody --viste fronte,alto,iso
#
# Esce anche manifest.json con i parametri di camera: due render fatti a
# distanza di ore sono sovrapponibili pixel su pixel.

import bpy, sys, os, json, math
from mathutils import Vector


def arg(nome, dif=None):
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    return a[a.index('--' + nome) + 1] if '--' + nome in a else dif


FUORI    = arg('cartella', '/tmp/vista-blender')
LATO     = int(arg('lato', '900'))
MARGINE  = float(arg('margine', '0.08'))
SOLO     = arg('solo')                       # rende un oggetto solo (per nome)
COLL     = arg('collezione')                 # oppure un'intera collezione
VISTE    = (arg('viste') or 'fronte,lato,alto,iso').split(',')
SFONDO   = arg('sfondo', 'grigio')           # grigio | trasparente | nero
ETICHETTA = arg('etichetta', '')             # sottocartella, es. "prima"/"dopo"

if ETICHETTA:
    FUORI = os.path.join(FUORI, ETICHETTA)
os.makedirs(FUORI, exist_ok=True)

# nome vista -> direzione DA CUI si guarda, e quale asse sta in alto
DIREZIONI = {
    'fronte':  (Vector(( 0, -1,  0)), 'Z'),
    'retro':   (Vector(( 0,  1,  0)), 'Z'),
    'lato':    (Vector(( 1,  0,  0)), 'Z'),   # da destra
    'sinistra':(Vector((-1,  0,  0)), 'Z'),
    'alto':    (Vector(( 0,  0,  1)), 'Y'),
    'sotto':   (Vector(( 0,  0, -1)), 'Y'),
    'iso':     (Vector(( 1, -1, 0.8)), 'Z'),  # assonometria: rivela la forma
}


def bersagli():
    """Gli oggetti da inquadrare. Senza filtri: tutte le mesh visibili."""
    if SOLO:
        o = bpy.data.objects.get(SOLO)
        if not o:
            cand = [x for x in bpy.data.objects if SOLO.lower() in x.name.lower()]
            if not cand:
                print(f"ERRORE: nessun oggetto chiamato '{SOLO}'")
                print("Disponibili:", ", ".join(o.name for o in bpy.data.objects[:40]))
                sys.exit(2)
            o = cand[0]
            print(f"nota: '{SOLO}' non esatto, uso '{o.name}'")
        return [o]
    if COLL:
        c = bpy.data.collections.get(COLL)
        if not c:
            print(f"ERRORE: nessuna collezione '{COLL}'")
            sys.exit(2)
        return [o for o in c.all_objects if o.type == 'MESH']
    return [o for o in bpy.context.scene.objects
            if o.type == 'MESH' and o.visible_get()]


def ingombro(oggetti):
    """Riquadro di ingombro in coordinate del mondo."""
    pts = []
    for o in oggetti:
        for c in o.bound_box:
            pts.append(o.matrix_world @ Vector(c))
    if not pts:
        print("ERRORE: nessuna geometria da inquadrare"); sys.exit(2)
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx, (mn + mx) / 2, (mx - mn)


def prepara_scena():
    s = bpy.context.scene
    # EEVEE: bastano secondi, e per vedere la forma è più che sufficiente.
    for motore in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
        try:
            s.render.engine = motore; break
        except TypeError:
            continue
    s.render.resolution_x = s.render.resolution_y = LATO
    s.render.resolution_percentage = 100
    s.render.image_settings.file_format = 'PNG'
    s.render.film_transparent = (SFONDO == 'trasparente')

    # Mondo neutro: senza questo un modello senza luci esce nero e l'agente
    # crede di aver rotto la geometria.
    if not s.world:
        s.world = bpy.data.worlds.new("VistaMondo")
    s.world.use_nodes = True
    bg = s.world.node_tree.nodes.get('Background')
    if bg:
        col = {'nero': (0, 0, 0, 1), 'grigio': (0.05, 0.05, 0.06, 1)}.get(SFONDO, (0.05, 0.05, 0.06, 1))
        bg.inputs[0].default_value = col
        bg.inputs[1].default_value = 1.0

    # Un sole fisso: la luce non deve dipendere da com'era salvato il file.
    luce = bpy.data.objects.get('__vista_sole__')
    if not luce:
        d = bpy.data.lights.new('__vista_sole__', type='SUN')
        luce = bpy.data.objects.new('__vista_sole__', d)
        s.collection.objects.link(luce)
    luce.data.energy = 3.0
    luce.rotation_euler = (math.radians(55), 0, math.radians(35))
    return s


def piazza_camera(scena, centro, dim, direzione, su):
    cam = bpy.data.objects.get('__vista_cam__')
    if not cam:
        d = bpy.data.cameras.new('__vista_cam__')
        cam = bpy.data.objects.new('__vista_cam__', d)
        scena.collection.objects.link(cam)
    scena.camera = cam

    # Ortografica: niente prospettiva significa che due render sono
    # confrontabili e che le proporzioni si leggono davvero.
    cam.data.type = 'ORTHO'
    raggio = max(dim.x, dim.y, dim.z)
    if raggio <= 0:
        raggio = 1.0

    d = direzione.normalized()
    cam.location = centro + d * (raggio * 3 + 10)

    # Orienta la camera verso il centro, con l'asse indicato in alto.
    su_v = Vector((0, 0, 1)) if su == 'Z' else Vector((0, 1, 0))
    guarda = -d
    if abs(guarda.dot(su_v)) > 0.999:            # vista dall'alto/sotto
        su_v = Vector((0, 1, 0)) if su == 'Z' else Vector((0, 0, 1))
    destra = guarda.cross(su_v).normalized()
    vero_su = destra.cross(guarda).normalized()
    # Estensione reale sul piano della camera: proietto gli 8 angoli
    # dell'ingombro sugli assi destra/su. Senza questo, la vista isometrica
    # taglia gli angoli di qualunque modello compatto.
    mezzo = dim / 2
    angoli = [Vector((sx * mezzo.x, sy * mezzo.y, sz * mezzo.z))
              for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    larg = max(abs(a.dot(destra)) for a in angoli) * 2
    alt  = max(abs(a.dot(vero_su)) for a in angoli) * 2
    cam.data.ortho_scale = max(larg, alt, 1e-6) * (1 + MARGINE * 2)
    cam.data.clip_start = 0.001
    cam.data.clip_end = raggio * 20 + 1000

    import mathutils
    m = mathutils.Matrix((
        (destra.x, vero_su.x, -guarda.x, 0),
        (destra.y, vero_su.y, -guarda.y, 0),
        (destra.z, vero_su.z, -guarda.z, 0),
        (0, 0, 0, 1),
    ))
    cam.rotation_euler = m.to_euler()
    return cam


def main():
    ogg = bersagli()
    mn, mx, centro, dim = ingombro(ogg)
    scena = prepara_scena()

    if SOLO or COLL:
        tenuti = {o.name for o in ogg}
        for o in bpy.context.scene.objects:
            if o.type == 'MESH' and o.name not in tenuti:
                o.hide_render = True

    manifesto = {
        'file': bpy.data.filepath,
        'bersaglio': SOLO or COLL or 'intera scena',
        'oggetti': len(ogg),
        'facce': sum(len(o.data.polygons) for o in ogg if o.type == 'MESH'),
        'ingombro_m': {'min': list(mn), 'max': list(mx),
                       'dimensioni': list(dim), 'centro': list(centro)},
        'lato_px': LATO, 'sfondo': SFONDO, 'viste': {},
    }

    for v in VISTE:
        v = v.strip()
        if v not in DIREZIONI:
            print(f"vista sconosciuta, salto: {v}"); continue
        direzione, su = DIREZIONI[v]
        cam = piazza_camera(scena, centro, dim, direzione, su)
        out = os.path.join(FUORI, f"{v}.png")
        scena.render.filepath = out
        bpy.ops.render.render(write_still=True)
        manifesto['viste'][v] = {
            'file': out,
            'metri_coperti': cam.data.ortho_scale,
            'camera_pos': list(cam.location),
            'camera_rot': list(cam.rotation_euler),
        }
        print(f"reso: {out}  ({cam.data.ortho_scale:.2f} m da bordo a bordo)")

    mp = os.path.join(FUORI, 'manifest.json')
    with open(mp, 'w') as f:
        json.dump(manifesto, f, indent=2, ensure_ascii=False)
    print(f"\nmanifesto: {mp}")
    print(f"oggetti inquadrati: {manifesto['oggetti']}  facce: {manifesto['facce']}")
    print(f"ingombro reale: {dim.x:.2f} x {dim.y:.2f} x {dim.z:.2f} m")


main()
