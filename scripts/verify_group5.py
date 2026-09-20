# -*- coding: utf-8 -*-
"""
Автоматическая проверка Группы 5 ("NK.5_Печать"), нанизанной на
полную цепочку Группа1 -> 2 -> 3 -> 4 -> 5.

Запуск:
    blender --background --python scripts/verify_group5.py -- <out_dir>
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from build_group1_axis import build as build_axis
from build_group2_profile import build as build_profile
from build_group3_shell import build_all_groups as build_shell_all, SAMPLER_NAME
from build_group4_inserts import build_all_groups as build_inserts_all
from build_group5_print import build_all_groups as build_print_all


def socket_identifier(tree, name, in_out='OUTPUT'):
    for item in tree.interface.items_tree:
        if item.item_type == 'SOCKET' and item.in_out == in_out and item.name == name:
            return item.identifier
    raise KeyError(name)


def set_input(node, tree, name, value):
    ident = socket_identifier(tree, name, 'INPUT')
    node.inputs[ident].default_value = value


def bake_output_as_attribute(obj_mod, tree, name, attr_name):
    ident = socket_identifier(tree, name, 'OUTPUT')
    key = f"{ident}_attribute_name"
    if key in obj_mod.keys():
        obj_mod[key] = attr_name
        return attr_name
    return None


def read_attr(mesh, attr_name):
    if attr_name not in mesh.attributes:
        return None
    data = mesh.attributes[attr_name].data
    if len(data) == 0:
        return None
    d0 = data[0]
    for prop in ("value", "vector", "color"):
        if hasattr(d0, prop):
            return getattr(d0, prop)
    return None


def mesh_stats(me):
    verts = [v.co.copy() for v in me.vertices]
    if not verts:
        return {"n": 0, "bbox": (0, 0, 0)}
    xs = [v.x for v in verts]; ys = [v.y for v in verts]; zs = [v.z for v in verts]
    return {"n": len(verts), "bbox": (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))}


def build_full_master():
    axis_tree = build_axis()
    profile_tree = build_profile()
    shell_tree = build_shell_all()
    sampler_tree = bpy.data.node_groups[SAMPLER_NAME]
    inserts_tree = build_inserts_all(sampler_tree=sampler_tree)
    print_tree = build_print_all()

    name = "NK_Group5_Demo"
    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    mesh = bpy.data.meshes.new(name + "_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    mod = obj.modifiers.new("NK_Master", "NODES")
    master = bpy.data.node_groups.new("NK.Master_full5", "GeometryNodeTree")
    master.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    mod.node_group = master

    gout = master.nodes.new("NodeGroupOutput"); gout.location = (1600, 0)
    g1 = master.nodes.new("GeometryNodeGroup"); g1.node_tree = axis_tree; g1.location = (-800, 0)
    g2 = master.nodes.new("GeometryNodeGroup"); g2.node_tree = profile_tree; g2.location = (-400, 0)
    g3 = master.nodes.new("GeometryNodeGroup"); g3.node_tree = shell_tree; g3.location = (0, 0)
    g4 = master.nodes.new("GeometryNodeGroup"); g4.node_tree = inserts_tree; g4.location = (400, 0)
    g5 = master.nodes.new("GeometryNodeGroup"); g5.node_tree = print_tree; g5.location = (800, 0)

    master.links.new(g1.outputs["Ось_кривая"], g2.inputs["Ось_кривая"])
    master.links.new(g1.outputs["Факт_длина_дуги_мм"], g2.inputs["Длина_сегмента_мм"])
    master.links.new(g1.outputs["Сторона_ноги"], g2.inputs["Сторона_ноги"])
    master.links.new(g2.outputs["Профиль_точки"], g3.inputs["Профиль_точки"])
    master.links.new(g2.outputs["Точек_в_кольце"], g3.inputs["Точек_в_кольце"])
    master.links.new(g3.outputs["Перед"], g4.inputs["Перед"])
    master.links.new(g3.outputs["Зад"], g4.inputs["Зад"])
    master.links.new(g1.outputs["Точка_A"], g4.inputs["Точка_A"])
    master.links.new(g1.outputs["Точка_B"], g4.inputs["Точка_B"])
    master.links.new(g2.outputs["Профиль_точки"], g4.inputs["Профиль_точки"])
    master.links.new(g2.outputs["Точек_в_кольце"], g4.inputs["Точек_в_кольце"])
    master.links.new(g2.outputs["Колец_всего"], g4.inputs["Колец_всего"])
    master.links.new(g1.outputs["Факт_длина_дуги_мм"], g4.inputs["Длина_сегмента_мм"])

    master.links.new(g4.outputs["Перед"], g5.inputs["Перед"])
    master.links.new(g4.outputs["Зад"], g5.inputs["Зад"])
    master.links.new(g1.outputs["Точка_A"], g5.inputs["Точка_A"])
    master.links.new(g1.outputs["Точка_B"], g5.inputs["Точка_B"])

    master.links.new(g5.outputs["VIS_Вместе"], gout.inputs["Geometry"])

    if "Провер_ВСЕ_OK" not in [s.name for s in master.interface.items_tree
                                if s.item_type == 'SOCKET' and s.in_out == 'OUTPUT']:
        master.interface.new_socket(name="Провер_ВСЕ_OK", in_out='OUTPUT', socket_type='NodeSocketBool')
        master.interface.new_socket(name="Провер_Отчёт", in_out='OUTPUT', socket_type='NodeSocketString')
        master.interface.new_socket(name="Число_сегментов", in_out='OUTPUT', socket_type='NodeSocketInt')
    master.links.new(g5.outputs["Провер_ВСЕ_OK"], gout.inputs["Провер_ВСЕ_OK"])
    master.links.new(g5.outputs["Провер_Отчёт"], gout.inputs["Провер_Отчёт"])
    master.links.new(g5.outputs["Число_сегментов"], gout.inputs["Число_сегментов"])

    return obj, mod, master, g1, g2, g3, g4, g5, print_tree


def run_case(label, g5_params, out_dir):
    obj, mod, master, g1, g2, g3, g4, g5, print_tree = build_full_master()

    for k, v in g5_params.items():
        set_input(g5, print_tree, k, v)

    bake_output_as_attribute(mod, master, "Провер_ВСЕ_OK", "chk_ok")
    bake_output_as_attribute(mod, master, "Число_сегментов", "chk_n")

    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(deps)
    me = obj_eval.to_mesh()
    stats = mesh_stats(me)
    chk_ok = read_attr(me, "chk_ok")
    chk_n = read_attr(me, "chk_n")
    obj_eval.to_mesh_clear()

    print(f"=== Кейс: {label} ===")
    print(f"  Параметры: {g5_params}")
    print(f"  Вершин VIS_Вместе: {stats['n']}")
    print(f"  BBox (X,Y,Z) мм: {tuple(round(c,1) for c in stats['bbox'])}")
    print(f"  Число_сегментов = {chk_n}")
    print(f"  Провер_ВСЕ_OK = {chk_ok}")

    import bmesh
    gout_master = [n for n in master.nodes if n.bl_idname == 'NodeGroupOutput'][0]
    for outname in ["Перед_Низ", "Перед_Верх", "Зад_Низ", "Зад_Верх"]:
        master.links.new(g5.outputs[outname], gout_master.inputs["Geometry"])
        deps = bpy.context.evaluated_depsgraph_get()
        oe = obj.evaluated_get(deps)
        me2 = oe.to_mesh()
        bm = bmesh.new(); bm.from_mesh(me2)
        boundary = [e for e in bm.edges if len(e.link_faces) != 2]
        vol = bm.calc_volume(signed=True) if len(me2.vertices) > 0 else 0.0
        print(f"  {outname}: verts={len(me2.vertices)} boundary_edges={len(boundary)} "
              f"signed_vol={round(vol,1)}")
        bm.free()
        oe.to_mesh_clear()
    master.links.new(g5.outputs["VIS_Вместе"], gout_master.inputs["Geometry"])

    # render
    os.makedirs(out_dir, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 700
    scene.render.resolution_y = 900
    scene.render.filepath = os.path.join(out_dir, f"group5_{label}.png")

    bbox = stats["bbox"]
    cz = bbox[2] / 2.0 if bbox[2] else 175.0
    cam_data = bpy.data.cameras.new("Cam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = max(bbox[2], 200) * 1.3
    cam = bpy.data.objects.new("Cam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (900, 0, cz)
    cam.rotation_euler = (math.radians(90), 0, math.radians(90))
    scene.camera = cam

    light_data = bpy.data.lights.new("Sun", type='SUN')
    light_data.energy = 3.0
    light = bpy.data.objects.new("Sun", light_data)
    bpy.context.collection.objects.link(light)
    light.rotation_euler = (math.radians(55), 0, math.radians(35))

    bpy.ops.render.render(write_still=True)

    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.cameras.remove(cam_data)
    bpy.data.objects.remove(light, do_unlink=True)
    bpy.data.lights.remove(light_data)

    return {"label": label, "bbox": stats["bbox"], "ok": chk_ok, "n": chk_n, "verts": stats["n"]}


def main():
    argv = sys.argv
    out_dir = argv[argv.index("--") + 1] if "--" in argv else "/tmp/nk_preview5"

    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 0.001

    results = []
    results.append(run_case("default", {}, out_dir))  # 350мм / 256мм printer -> 2 segments
    results.append(run_case("fits_whole", {"Печать_Z_мм": 400.0}, out_dir))  # 1 segment
    results.append(run_case("no_tilt", {"Наклон_шва_град": 0.0}, out_dir))
    results.append(run_case("steep_tilt", {"Наклон_шва_град": 22.0}, out_dir))

    print("\n=== ИТОГ ===")
    all_ok = True
    for r in results:
        status = "OK" if r["ok"] else "FAIL/None"
        if not r["ok"]:
            all_ok = False
        print(f"  {r['label']:12s} bbox={tuple(round(c,1) for c in r['bbox'])} "
              f"segments={r['n']} verts={r['verts']} check={status}")
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ" if all_ok else "ЕСТЬ ПРОВАЛЕННЫЕ ПРОВЕРКИ")

    blend_path = os.path.join(out_dir, "group5_print.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"Сохранено: {blend_path}")


if __name__ == "__main__":
    main()
