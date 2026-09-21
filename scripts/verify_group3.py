# -*- coding: utf-8 -*-
"""
Автоматическая проверка Группы 3 ("NK.3_Оболочка"), нанизанной на
полную цепочку Группа1 -> Группа2 -> Группа3.

Запуск:
    blender --background --python scripts/verify_group3.py -- <out_dir>
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from build_group1_axis import build as build_axis
from build_group2_profile import build as build_profile
from build_group3_shell import build_all_groups, build_demo_object


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


def run_case(label, shell_params, out_dir):
    axis_tree = build_axis()
    profile_tree = build_profile()
    shell_tree = build_all_groups()
    obj, mod, master, g1, g2, g3 = build_demo_object(axis_tree, profile_tree, shell_tree)

    for k, v in shell_params.items():
        set_input(g3, shell_tree, k, v)

    if "Провер_ВСЕ_OK" not in [s.name for s in master.interface.items_tree
                                if s.item_type == 'SOCKET' and s.in_out == 'OUTPUT']:
        master.interface.new_socket(name="Провер_ВСЕ_OK", in_out='OUTPUT', socket_type='NodeSocketBool')
        master.interface.new_socket(name="Провер_Отчёт", in_out='OUTPUT', socket_type='NodeSocketString')
        master.interface.new_socket(name="Колец_после_подрезки", in_out='OUTPUT', socket_type='NodeSocketInt')
    gout_master = [n for n in master.nodes if n.bl_idname == 'NodeGroupOutput'][0]
    master.links.new(g3.outputs["Провер_ВСЕ_OK"], gout_master.inputs["Провер_ВСЕ_OK"])
    master.links.new(g3.outputs["Провер_Отчёт"], gout_master.inputs["Провер_Отчёт"])
    master.links.new(g3.outputs["Колец_после_подрезки"], gout_master.inputs["Колец_после_подрезки"])

    bake_output_as_attribute(mod, master, "Провер_ВСЕ_OK", "chk_ok")
    bake_output_as_attribute(mod, master, "Колец_после_подрезки", "chk_n")

    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(deps)
    me = obj_eval.to_mesh()

    stats = mesh_stats(me)
    chk_ok = read_attr(me, "chk_ok")
    chk_n = read_attr(me, "chk_n")

    print(f"=== Кейс: {label} ===")
    print(f"  Параметры: {shell_params}")
    print(f"  Вершин VIS_Вместе: {stats['n']}")
    print(f"  BBox (X,Y,Z) мм: {tuple(round(c,1) for c in stats['bbox'])}")
    print(f"  Провер_ВСЕ_OK = {chk_ok}")
    print(f"  Колец_после_подрезки = {chk_n}")

    obj_eval.to_mesh_clear()

    # --- отдельно читаем Перед и Зад по отдельности (замкнутость каждой половины) ---
    master.links.new(g3.outputs["Перед"], gout_master.inputs["Geometry"])
    deps = bpy.context.evaluated_depsgraph_get()
    oe = obj.evaluated_get(deps)
    me_front = oe.to_mesh()
    front_stats = mesh_stats(me_front)
    oe.to_mesh_clear()

    master.links.new(g3.outputs["Зад"], gout_master.inputs["Geometry"])
    deps = bpy.context.evaluated_depsgraph_get()
    oe = obj.evaluated_get(deps)
    me_back = oe.to_mesh()
    back_stats = mesh_stats(me_back)
    oe.to_mesh_clear()
    print(f"  Перед: {front_stats['n']} вершин, bbox={tuple(round(c,1) for c in front_stats['bbox'])}")
    print(f"  Зад:   {back_stats['n']} вершин, bbox={tuple(round(c,1) for c in back_stats['bbox'])}")

    master.links.new(g3.outputs["VIS_Вместе"], gout_master.inputs["Geometry"])

    # --- рендер ---
    os.makedirs(out_dir, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 700
    scene.render.resolution_y = 900
    scene.render.filepath = os.path.join(out_dir, f"group3_{label}.png")
    scene.display.shading.light = 'STUDIO'
    scene.display.shading.color_type = 'MATERIAL'

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

    return {
        "label": label, "bbox": stats["bbox"], "ok": chk_ok, "n": chk_n,
        "verts": stats["n"], "front_n": front_stats["n"], "back_n": back_stats["n"],
    }


def main():
    argv = sys.argv
    out_dir = argv[argv.index("--") + 1] if "--" in argv else "/tmp/nk_preview3"

    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 0.001

    results = []
    results.append(run_case("default", {}, out_dir))
    results.append(run_case("trimmed", {
        "Подрезка_снизу_доля": 0.15,
        "Подрезка_сверху_доля": 0.10,
    }, out_dir))
    results.append(run_case("thick_wall", {
        "Толщина_стенки_мм": 4.0,
    }, out_dir))
    results.append(run_case("thin_wall", {
        "Толщина_стенки_мм": 1.2,
    }, out_dir))
    results.append(run_case("flare_max", {
        "Расширение_верхней_мм": 15.0,
        "Расширение_протяжённость_доля": 0.3,
    }, out_dir))
    results.append(run_case("joint_max", {
        "Фальц_глубина_мм": 3.0,
        "Фальц_ширина_мм": 6.0,
        "Фальц_утопление_мм": 1.0,
    }, out_dir))
    results.append(run_case("joint_off", {
        "Фальц_глубина_мм": 0.0,
        "Фальц_утопление_мм": 0.0,
    }, out_dir))
    results.append(run_case("joint_skew", {
        "Фальц_скос_град": 5.0,
    }, out_dir))
    results.append(run_case("joint_thin_ring", {
        # Меньше точек в кольце (крупнее шаг мм/колонка) - проверяем,
        # что мм-калибровка и защиты от самопересечения не ломаются
        # на грубой сетке.
        "Толщина_стенки_мм": 1.2,
        "Фальц_глубина_мм": 1.0,
        "Фальц_ширина_мм": 1.0,
    }, out_dir))

    print("\n=== ИТОГ ===")
    all_ok = True
    for r in results:
        status = "OK" if r["ok"] else "FAIL/None"
        if not r["ok"]:
            all_ok = False
        print(f"  {r['label']:12s} bbox={tuple(round(c,1) for c in r['bbox'])} "
              f"rings={r['n']} verts={r['verts']} front={r['front_n']} back={r['back_n']} "
              f"check={status}")
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ" if all_ok else "ЕСТЬ ПРОВАЛЕННЫЕ ПРОВЕРКИ")

    blend_path = os.path.join(out_dir, "group3_shell.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"Сохранено: {blend_path}")


if __name__ == "__main__":
    main()
