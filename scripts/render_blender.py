import argparse
import math
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1 :]
    else:
        argv = []
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--output-dir", default="data/renders")
    parser.add_argument("--views", type=int, default=4)
    parser.add_argument("--resolution", type=int, default=768)
    return parser.parse_args(argv)


def read_jsonl(path: str) -> list[dict]:
    import json

    rows = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def clear_scene(bpy) -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()


def import_asset(bpy, path: str) -> None:
    suffix = Path(path).suffix.lower()
    if suffix == ".glb" or suffix == ".gltf":
        bpy.ops.import_scene.gltf(filepath=path)
    elif suffix == ".obj":
        bpy.ops.wm.obj_import(filepath=path)
    elif suffix == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)
    else:
        raise ValueError(f"Unsupported asset format: {path}")


def normalize_scene(bpy, mathutils) -> None:
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise ValueError("No mesh objects found after import")

    # Bake object transforms into mesh vertices. Objaverse assets often use nested
    # transforms; editing object.location alone can leave the visible mesh off-camera.
    for obj in meshes:
        obj.data.transform(obj.matrix_world)
        obj.matrix_world.identity()

    for obj in meshes:
        obj.select_set(False)

    min_corner = mathutils.Vector((float("inf"), float("inf"), float("inf")))
    max_corner = mathutils.Vector((float("-inf"), float("-inf"), float("-inf")))
    for obj in meshes:
        for vertex in obj.data.vertices:
            co = vertex.co
            min_corner.x = min(min_corner.x, co.x)
            min_corner.y = min(min_corner.y, co.y)
            min_corner.z = min(min_corner.z, co.z)
            max_corner.x = max(max_corner.x, co.x)
            max_corner.y = max(max_corner.y, co.y)
            max_corner.z = max(max_corner.z, co.z)

    center = (min_corner + max_corner) / 2
    size = max(max_corner.x - min_corner.x, max_corner.y - min_corner.y, max_corner.z - min_corner.z)
    scale = 2.2 / size if size > 0 else 1.0
    for obj in meshes:
        for vertex in obj.data.vertices:
            vertex.co = (vertex.co - center) * scale
        obj.data.update()


def scene_bbox_corners(bpy, mathutils):
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise ValueError("No mesh objects found after normalization")

    min_corner = mathutils.Vector((float("inf"), float("inf"), float("inf")))
    max_corner = mathutils.Vector((float("-inf"), float("-inf"), float("-inf")))
    for obj in meshes:
        for vertex in obj.data.vertices:
            co = obj.matrix_world @ vertex.co
            min_corner.x = min(min_corner.x, co.x)
            min_corner.y = min(min_corner.y, co.y)
            min_corner.z = min(min_corner.z, co.z)
            max_corner.x = max(max_corner.x, co.x)
            max_corner.y = max(max_corner.y, co.y)
            max_corner.z = max(max_corner.z, co.z)

    return [
        mathutils.Vector((x, y, z))
        for x in (min_corner.x, max_corner.x)
        for y in (min_corner.y, max_corner.y)
        for z in (min_corner.z, max_corner.z)
    ]


def setup_camera_light(bpy, mathutils):
    light_data = bpy.data.lights.new("KeyLight", type="AREA")
    light_data.energy = 500
    light_data.size = 5
    light = bpy.data.objects.new("KeyLight", light_data)
    bpy.context.collection.objects.link(light)
    light.location = (0, -3, 4)

    camera_data = bpy.data.cameras.new("Camera")
    camera = bpy.data.objects.new("Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera.data.lens = 55
    return camera


def look_at(obj, target, mathutils) -> None:
    direction = mathutils.Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def fit_camera_to_bbox(bpy, camera, bbox_corners, mathutils, margin: float = 1.12) -> None:
    scene = bpy.context.scene
    fitted_location, _ = camera.camera_fit_coords(scene, bbox_corners)
    target = mathutils.Vector((0, 0, 0))
    fitted_location = mathutils.Vector(fitted_location)

    # Keep the viewing direction from camera_fit_coords, then push back slightly
    # to preserve a stable margin for thin or diagonal assets.
    direction = fitted_location - target
    if direction.length == 0:
        direction = mathutils.Vector((0, -1, 0))
    camera.location = target + direction * margin
    look_at(camera, target, mathutils)


def render_views(bpy, mathutils, uid: str, out_dir: Path, views: int, resolution: int) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "MATERIAL"
    scene.display.shading.background_type = "VIEWPORT"
    scene.display.shading.background_color = (1, 1, 1)
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    scene.render.film_transparent = False

    camera = setup_camera_light(bpy, mathutils)
    radius = 3.2
    elevation = math.radians(18)
    bbox_corners = scene_bbox_corners(bpy, mathutils)

    rgb_dir = out_dir / uid / "rgb"
    normal_dir = out_dir / uid / "normal"
    rgb_dir.mkdir(parents=True, exist_ok=True)
    normal_dir.mkdir(parents=True, exist_ok=True)

    for idx in range(views):
        azimuth = (2 * math.pi * idx) / views
        camera.location = (
            radius * math.sin(azimuth) * math.cos(elevation),
            -radius * math.cos(azimuth) * math.cos(elevation),
            radius * math.sin(elevation),
        )
        look_at(camera, (0, 0, 0), mathutils)
        fit_camera_to_bbox(bpy, camera, bbox_corners, mathutils)
        scene.render.filepath = str(rgb_dir / f"view_{idx:02d}.png")
        scene.view_layers[0].use_pass_normal = False
        bpy.ops.render.render(write_still=True)

    normal_mat = bpy.data.materials.new("Gen3D_Normal_Debug_Material")
    normal_mat.use_nodes = True
    nodes = normal_mat.node_tree.nodes
    nodes.clear()
    geom = nodes.new("ShaderNodeNewGeometry")
    mapping = nodes.new("ShaderNodeVectorMath")
    mapping.operation = "MULTIPLY_ADD"
    mapping.inputs[1].default_value = (0.5, 0.5, 0.5)
    mapping.inputs[2].default_value = (0.5, 0.5, 0.5)
    emission = nodes.new("ShaderNodeEmission")
    output = nodes.new("ShaderNodeOutputMaterial")
    normal_mat.node_tree.links.new(geom.outputs["Normal"], mapping.inputs[0])
    normal_mat.node_tree.links.new(mapping.outputs[0], emission.inputs["Color"])
    normal_mat.node_tree.links.new(emission.outputs["Emission"], output.inputs["Surface"])
    scene.display.shading.color_type = "TEXTURE"

    original_materials = {}
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            original_materials[obj.name] = list(obj.data.materials)
            obj.data.materials.clear()
            obj.data.materials.append(normal_mat)

    for idx in range(views):
        azimuth = (2 * math.pi * idx) / views
        camera.location = (
            radius * math.sin(azimuth) * math.cos(elevation),
            -radius * math.cos(azimuth) * math.cos(elevation),
            radius * math.sin(elevation),
        )
        look_at(camera, (0, 0, 0), mathutils)
        fit_camera_to_bbox(bpy, camera, bbox_corners, mathutils)
        scene.render.filepath = str(normal_dir / f"view_{idx:02d}.png")
        bpy.ops.render.render(write_still=True)

    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and obj.name in original_materials:
            obj.data.materials.clear()
            for mat in original_materials[obj.name]:
                obj.data.materials.append(mat)


def main() -> None:
    import bpy
    import mathutils

    args = parse_args()
    rows = read_jsonl(args.manifest)
    out_dir = Path(args.output_dir)

    for row in rows:
        uid = row["uid"]
        path = row.get("local_path")
        if not path:
            print(f"Skipping {uid}: local_path missing")
            continue
        try:
            clear_scene(bpy)
            import_asset(bpy, path)
            normalize_scene(bpy, mathutils)
            render_views(bpy, mathutils, uid, out_dir, args.views, args.resolution)
            print(f"Rendered {uid}")
        except Exception as exc:
            print(f"Failed {uid}: {exc}")


if __name__ == "__main__":
    main()
