# Render a .blend from viewpoints that are FIXED and REPEATABLE — or from any
# angle you choose.
#
# The goal is not pretty pictures: it is *comparable* pictures. Same camera,
# same light, same framing every time, so a difference between a "before" and
# an "after" render comes from the model and not from chance.
#
# It exists for an agent working on geometry it cannot see: render, then open
# the PNG and actually look at what you did.
#
#   blender -b model.blend -P render.py -- --out /tmp/views
#   blender -b model.blend -P render.py -- --only Engine --views front,top,iso
#
# Free camera — pick your own angle instead of the presets:
#   --angles "45,20 120,60"     azimuth,elevation in degrees (one view each)
#   --from "10,-4,3"            explicit camera position in world coordinates
#   --at "0,0,1.5"              what to look at (default: centre of the bounds)
#   --zoom 0.4                  0.4 = four tenths of the frame, i.e. closer in
#   --perspective --focal 35    perspective instead of orthographic
#
# A manifest.json is written with every camera parameter, so a render made
# hours later lines up pixel for pixel with an earlier one.

import bpy, sys, os, json, math, mathutils
from mathutils import Vector


def arg(name, default=None):
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    return a[a.index('--' + name) + 1] if '--' + name in a else default


def flag(name):
    a = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    return ('--' + name) in a


def vec(s):
    if not s:
        return None
    p = [float(x) for x in s.replace(' ', '').split(',')]
    return Vector(p) if len(p) == 3 else None


OUT      = arg('out', '/tmp/blender-eyes')
SIDE     = int(arg('side', '900'))
MARGIN   = float(arg('margin', '0.08'))
ONLY     = arg('only')                       # single object, by name
COLL     = arg('collection')                 # or a whole collection
_views_raw = arg('views', None)
# Distinguish "not given" (use the presets) from "given empty" (custom angles
# only). A falsy check alone would silently render the presets anyway.
if _views_raw is None:
    _views_raw = 'front,side,top,iso' if not (arg('angles') or arg('from')) else ''
VIEWS    = [v for v in _views_raw.split(',') if v.strip()]
BG       = arg('bg', 'grey')                 # grey | transparent | black
LABEL    = arg('label', '')                  # subfolder, e.g. before / after
ANGLES   = arg('angles')                     # "az,el az,el ..."
FROM     = vec(arg('from'))                  # explicit camera position
AT       = vec(arg('at'))                    # explicit look-at point
ZOOM     = float(arg('zoom', '1.0'))         # <1 = closer, >1 = wider
PERSP    = flag('perspective')
FOCAL    = float(arg('focal', '50'))

if LABEL:
    OUT = os.path.join(OUT, LABEL)
os.makedirs(OUT, exist_ok=True)

# preset name -> direction the camera looks FROM, and which axis points up
PRESETS = {
    'front':  (Vector(( 0, -1,  0)), 'Z'),
    'back':   (Vector(( 0,  1,  0)), 'Z'),
    'side':   (Vector(( 1,  0,  0)), 'Z'),   # from the right
    'left':   (Vector((-1,  0,  0)), 'Z'),
    'top':    (Vector(( 0,  0,  1)), 'Y'),
    'bottom': (Vector(( 0,  0, -1)), 'Y'),
    'iso':    (Vector(( 1, -1, 0.8)), 'Z'),  # isometric: best at revealing shape
}


def from_azimuth_elevation(az_deg, el_deg):
    """Direction vector from azimuth (degrees around Z, 0 = -Y i.e. front)
    and elevation (degrees above the horizon)."""
    az, el = math.radians(az_deg), math.radians(el_deg)
    horiz = math.cos(el)
    return Vector((math.sin(az) * horiz, -math.cos(az) * horiz, math.sin(el)))


def targets():
    """Objects to frame. With no filter: every visible mesh."""
    if ONLY:
        o = bpy.data.objects.get(ONLY)
        if not o:
            found = [x for x in bpy.data.objects if ONLY.lower() in x.name.lower()]
            if not found:
                print(f"ERROR: no object named '{ONLY}'")
                print("Available:", ", ".join(o.name for o in bpy.data.objects[:40]))
                sys.exit(2)
            o = found[0]
            print(f"note: '{ONLY}' not exact, using '{o.name}'")
        return [o]
    if COLL:
        c = bpy.data.collections.get(COLL)
        if not c:
            print(f"ERROR: no collection '{COLL}'"); sys.exit(2)
        return [o for o in c.all_objects if o.type == 'MESH']
    return [o for o in bpy.context.scene.objects
            if o.type == 'MESH' and o.visible_get()]


def bounds(objects):
    """World-space bounding box."""
    pts = []
    for o in objects:
        for c in o.bound_box:
            pts.append(o.matrix_world @ Vector(c))
    if not pts:
        print("ERROR: nothing to frame"); sys.exit(2)
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx, (mn + mx) / 2, (mx - mn)


def setup_scene():
    s = bpy.context.scene
    # EEVEE: seconds per frame, and plenty to judge shape by.
    for engine in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE'):
        try:
            s.render.engine = engine; break
        except TypeError:
            continue
    s.render.resolution_x = s.render.resolution_y = SIDE
    s.render.resolution_percentage = 100
    s.render.image_settings.file_format = 'PNG'
    s.render.film_transparent = (BG == 'transparent')

    # A neutral world. Without it a model with no lights renders black and the
    # agent concludes it broke the geometry.
    if not s.world:
        s.world = bpy.data.worlds.new("EyesWorld")
    s.world.use_nodes = True
    bg = s.world.node_tree.nodes.get('Background')
    if bg:
        bg.inputs[0].default_value = {'black': (0, 0, 0, 1)}.get(BG, (0.05, 0.05, 0.06, 1))
        bg.inputs[1].default_value = 1.0

    # A fixed sun: lighting must not depend on how the file happened to be saved.
    sun = bpy.data.objects.get('__eyes_sun__')
    if not sun:
        d = bpy.data.lights.new('__eyes_sun__', type='SUN')
        sun = bpy.data.objects.new('__eyes_sun__', d)
        s.collection.objects.link(sun)
    sun.data.energy = 3.0
    sun.rotation_euler = (math.radians(55), 0, math.radians(35))
    return s


def place_camera(scene, centre, dim, direction, up_axis, position=None):
    cam = bpy.data.objects.get('__eyes_cam__')
    if not cam:
        d = bpy.data.cameras.new('__eyes_cam__')
        cam = bpy.data.objects.new('__eyes_cam__', d)
        scene.collection.objects.link(cam)
    scene.camera = cam

    radius = max(dim.x, dim.y, dim.z) or 1.0
    d = direction.normalized()
    cam.location = position if position is not None else centre + d * (radius * 3 + 10)
    look = (centre - cam.location).normalized()

    up_v = Vector((0, 0, 1)) if up_axis == 'Z' else Vector((0, 1, 0))
    if abs(look.dot(up_v)) > 0.999:            # straight down or straight up
        up_v = Vector((0, 1, 0)) if up_axis == 'Z' else Vector((0, 0, 1))
    right = look.cross(up_v).normalized()
    true_up = right.cross(look).normalized()

    # Real extent on the camera plane: project the 8 corners of the bounding box
    # onto the right/up axes. Sizing by the longest edge instead would clip the
    # corners of any compact model in an isometric view.
    half = dim / 2
    corners = [Vector((sx * half.x, sy * half.y, sz * half.z))
               for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
    width = max(abs(c.dot(right)) for c in corners) * 2
    height = max(abs(c.dot(true_up)) for c in corners) * 2
    extent = max(width, height, 1e-6) * (1 + MARGIN * 2) * ZOOM

    if PERSP:
        cam.data.type = 'PERSP'
        cam.data.lens = FOCAL
        if position is None:
            # Back off far enough that the whole extent fits the field of view.
            fov = 2 * math.atan(cam.data.sensor_width / (2 * FOCAL))
            dist = (extent / 2) / math.tan(fov / 2)
            cam.location = centre + d * dist
            look = (centre - cam.location).normalized()
            right = look.cross(up_v).normalized()
            true_up = right.cross(look).normalized()
    else:
        cam.data.type = 'ORTHO'
        cam.data.ortho_scale = extent

    cam.data.clip_start = 0.001
    cam.data.clip_end = radius * 20 + (cam.location - centre).length * 2 + 1000

    m = mathutils.Matrix((
        (right.x, true_up.x, -look.x, 0),
        (right.y, true_up.y, -look.y, 0),
        (right.z, true_up.z, -look.z, 0),
        (0, 0, 0, 1),
    ))
    cam.rotation_euler = m.to_euler()
    return cam, extent


def main():
    objs = targets()
    mn, mx, centre, dim = bounds(objs)
    if AT is not None:
        centre = AT
    scene = setup_scene()

    if ONLY or COLL:
        keep = {o.name for o in objs}
        for o in bpy.context.scene.objects:
            if o.type == 'MESH' and o.name not in keep:
                o.hide_render = True

    # Build the list of shots: presets, then any custom angles, then an
    # explicit camera position if one was given.
    shots = []
    for v in VIEWS:
        v = v.strip()
        if v in PRESETS:
            shots.append((v, PRESETS[v][0], PRESETS[v][1], None))
        elif v:
            print(f"unknown view, skipping: {v}")
    if ANGLES:
        for pair in ANGLES.split():
            try:
                az, el = [float(x) for x in pair.split(',')]
            except ValueError:
                print(f"bad angle '{pair}', expected az,el"); continue
            shots.append((f"az{az:g}-el{el:g}", from_azimuth_elevation(az, el), 'Z', None))
    if FROM is not None:
        shots.append(('custom', (centre - FROM).normalized() * -1, 'Z', FROM))
    if not shots:
        print("ERROR: no views requested"); sys.exit(2)

    manifest = {
        'file': bpy.data.filepath,
        'target': ONLY or COLL or 'whole scene',
        'objects': len(objs),
        'faces': sum(len(o.data.polygons) for o in objs if o.type == 'MESH'),
        'bounds_m': {'min': list(mn), 'max': list(mx),
                     'size': list(dim), 'centre': list(centre)},
        'side_px': SIDE, 'bg': BG, 'projection': 'perspective' if PERSP else 'orthographic',
        'views': {},
    }

    for name, direction, up, pos in shots:
        cam, extent = place_camera(scene, centre, dim, direction, up, pos)
        path = os.path.join(OUT, f"{name}.png")
        scene.render.filepath = path
        bpy.ops.render.render(write_still=True)
        manifest['views'][name] = {
            'file': path,
            'metres_across': extent if not PERSP else None,
            'camera_pos': list(cam.location),
            'camera_rot': list(cam.rotation_euler),
            'looks_at': list(centre),
        }
        span = f"{extent:.2f} m across" if not PERSP else f"{FOCAL:g}mm lens"
        print(f"rendered: {path}  ({span})")

    mp = os.path.join(OUT, 'manifest.json')
    with open(mp, 'w') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"\nmanifest: {mp}")
    print(f"objects framed: {manifest['objects']}   faces: {manifest['faces']}")
    print(f"real size: {dim.x:.2f} x {dim.y:.2f} x {dim.z:.2f} m")


main()
