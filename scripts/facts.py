# The measurable facts of a model, as JSON.
#
# Looking at a render tells you whether something *seems* right. This tells you
# whether it *is*: sizes in metres, scale, origins, loose vertices, disconnected
# islands, materials. These are claims an agent can assert true or false on,
# instead of forming an impression.
#
#   blender -b model.blend -P facts.py -- --out /tmp/facts.json
#   blender -b model.blend -P facts.py -- --only Engine
#
# Born from a real bug: one loose vertex seventeen metres away made a seven
# metre module measure twenty. The render did not show it. A number did.

import bpy, sys, os, json, math
from mathutils import Vector


def arg(name, default=None):
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    return a[a.index('--' + name) + 1] if '--' + name in a else default


OUT   = arg('out', '/tmp/blender-eyes-facts.json')
ONLY  = arg('only')
LIMIT = int(arg('limit', '400'))


def islands(me):
    """How many disconnected pieces the mesh has. A module should be one thing:
    if it reports twelve, either it is composite or something broke."""
    if len(me.vertices) > 200000:
        return None                      # too big to be worth the time
    adj = {i: set() for i in range(len(me.vertices))}
    for e in me.edges:
        a, b = e.vertices
        adj[a].add(b); adj[b].add(a)
    seen, count = set(), 0
    for v in adj:
        if v in seen:
            continue
        count += 1
        stack = [v]
        while stack:
            n = stack.pop()
            if n in seen:
                continue
            seen.add(n)
            stack.extend(adj[n] - seen)
    return count


def loose_vertices(me):
    """Vertices belonging to no face: invisible, but they still count towards
    the bounding box and the centre of mass."""
    used = set()
    for p in me.polygons:
        used.update(p.vertices)
    return len(me.vertices) - len(used)


def record(o):
    me = o.data
    pts = [o.matrix_world @ Vector(c) for c in o.bound_box]
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    d = {
        'name': o.name,
        'size_m': [round(v, 4) for v in (mx - mn)],
        'centre_m': [round(v, 4) for v in (mn + mx) / 2],
        'origin_m': [round(v, 4) for v in o.matrix_world.translation],
        'scale': [round(v, 5) for v in o.scale],
        'rotation_deg': [round(math.degrees(v), 2) for v in o.rotation_euler],
        'vertices': len(me.vertices),
        'faces': len(me.polygons),
        'materials': [m.name for m in me.materials if m],
        'visible': o.visible_get(),
        'hidden_in_render': o.hide_render,
    }
    d['loose_vertices'] = loose_vertices(me)
    n = islands(me)
    if n is not None:
        d['islands'] = n
    # Is the origin inside its own bounds? If not, rotating the object sends it
    # flying — the number one cause of "the part ended up in the wrong place".
    org = o.matrix_world.translation
    d['origin_outside_bounds'] = not (
        mn.x - 1e-4 <= org.x <= mx.x + 1e-4 and
        mn.y - 1e-4 <= org.y <= mx.y + 1e-4 and
        mn.z - 1e-4 <= org.z <= mx.z + 1e-4)
    d['non_unit_scale'] = any(abs(s - 1.0) > 1e-3 for s in o.scale)
    return d


meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if ONLY:
    meshes = [o for o in meshes if ONLY.lower() in o.name.lower()]
    if not meshes:
        print(f"ERROR: no object contains '{ONLY}'"); sys.exit(2)

records = [record(o) for o in meshes[:LIMIT]]

pts = []
for o in meshes:
    pts += [o.matrix_world @ Vector(c) for c in o.bound_box]
mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))

# The anomalies: the part an agent should read first.
anomalies = []
for r in records:
    if r.get('loose_vertices', 0) > 0:
        anomalies.append(f"{r['name']}: {r['loose_vertices']} loose vertices "
                         f"(they skew bounds and centre of mass)")
    if r.get('origin_outside_bounds'):
        anomalies.append(f"{r['name']}: origin OUTSIDE its own bounds "
                         f"(rotate it and it flies off)")
    if r.get('non_unit_scale'):
        anomalies.append(f"{r['name']}: non-unit scale {r['scale']} "
                         f"(apply it before exporting)")
    n = r.get('islands')
    if n:
        ratio = n / r['faces'] if r['faces'] else 0
        r['islands_per_face'] = round(ratio, 2)
        if ratio >= 0.4:
            anomalies.append(f"{r['name']}: {n} islands across {r['faces']} faces "
                             f"(ratio {ratio:.2f}) — geometry is NOT WELDED. Merge "
                             f"coincident vertices before separating or measuring, "
                             f"or 'separate by parts' returns shards")
        elif n > 20:
            anomalies.append(f"{r['name']}: {n} genuinely disconnected pieces")
    if r['faces'] == 0:
        anomalies.append(f"{r['name']}: ZERO faces (empty object)")

facts = {
    'file': bpy.data.filepath,
    'mesh_objects': len(meshes),
    'detailed': len(records),
    'total_faces': sum(len(o.data.polygons) for o in meshes),
    'total_vertices': sum(len(o.data.vertices) for o in meshes),
    'scene_bounds_m': {'min': [round(v, 3) for v in mn],
                       'max': [round(v, 3) for v in mx],
                       'size': [round(v, 3) for v in (mx - mn)]},
    'materials_in_file': len(bpy.data.materials),
    'anomalies': anomalies,
    'objects': records,
}

os.makedirs(os.path.dirname(OUT) or '.', exist_ok=True)
with open(OUT, 'w') as f:
    json.dump(facts, f, indent=2, ensure_ascii=False)

print(f"\n=== {os.path.basename(bpy.data.filepath) or 'scene'} ===")
print(f"meshes: {len(meshes)}   faces: {facts['total_faces']:,}   "
      f"materials: {facts['materials_in_file']}")
s = facts['scene_bounds_m']['size']
print(f"bounds: {s[0]} x {s[1]} x {s[2]} m")
if anomalies:
    print(f"\nANOMALIES ({len(anomalies)}):")
    for a in anomalies[:25]:
        print("  ! " + a)
    if len(anomalies) > 25:
        print(f"  ... and {len(anomalies) - 25} more")
else:
    print("\nno anomalies found")
print(f"\nfull facts: {OUT}")
