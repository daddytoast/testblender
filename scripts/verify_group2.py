# -*- coding: utf-8 -*-
"""
Автоматическая проверка Группы 2 ("NK.2_Профиль"), нанизанной на
реальную ось из Группы 1 (полная цепочка Группа1 -> Группа2).

Запуск:
    blender --background --python scripts/verify_group2.py -- <out_dir>
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from build_group1_axis import build as build_axis
from build_group2_profile import build as build_profile, build_demo_object


def socket_identifier(tree, name, in_out='OUTPUT'):
    for item in tree.interface.items_tree:
        if item.item_type == 'SOCKET' and item.in_out == in_out and item.name == name:
            return item.identifier
    raise KeyError(name)


def set_input(node, tree, name, value):
    ident = socket_identifier(tree, name, 'INPUT')
    node.inputs[ident].default_value = value


def bake_output_as_attribute(obj_mod, tree, name, attr_name, prefix):
    ident = socket_identifier(tree, name, 'OUTPUT')
    key = f"{prefix}{ident}_attribute_name"
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


def run_case(label, g2_params, out_dir):
    axis_tree = build_axis()
    tree = build_profile()
    obj, mod, master, g1, g2 = build_demo_object(tree, axis_tree)

    for k, v in g2_params.items():
        set_input(g2, tree, k, v)

    # Проверочные выходы Группы 2 (Провер_ВСЕ_OK, Колец_всего) не
    # выведены наружу в демо master-дереве (там наружу идёт только
    # VIS_Кольца) — добавляем их в интерфейс master'а, чтобы можно
    # было прочитать значения через evaluated depsgraph, как в
    # verify_group1.py.
    # Запекаем проверочные выходы ВНУТРИ master-дерева: добавляем
    # временный Group Output проверочных сокетов g2 в master.
    if "Провер_ВСЕ_OK" not in [s.name for s in master.interface.items_tree if s.item_type == 'SOCKET' and s.in_out == 'OUTPUT']:
        master.interface.new_socket(name="Провер_ВСЕ_OK", in_out='OUTPUT', socket_type='NodeSocketBool')
        master.interface.new_socket(name="Провер_Отчёт", in_out='OUTPUT', socket_type='NodeSocketString')
        master.interface.new_socket(name="Колец_всего", in_out='OUTPUT', socket_type='NodeSocketInt')
    gout_master = [n for n in master.nodes if n.bl_idname == 'NodeGroupOutput'][0]
    master.links.new(g2.outputs["Провер_ВСЕ_OK"], gout_master.inputs["Провер_ВСЕ_OK"])
    master.links.new(g2.outputs["Провер_Отчёт"], gout_master.inputs["Провер_Отчёт"])
    master.links.new(g2.outputs["Колец_всего"], gout_master.inputs["Колец_всего"])

    bake_output_as_attribute(mod, master, "Провер_ВСЕ_OK", "chk_ok", "")
    bake_output_as_attribute(mod, master, "Колец_всего", "chk_n", "")

    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    obj_eval = obj.evaluated_get(deps)
    me = obj_eval.to_mesh()

    verts = [v.co.copy() for v in me.vertices]
    if verts:
        xs = [v.x for v in verts]; ys = [v.y for v in verts]; zs = [v.z for v in verts]
        bbox = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    else:
        bbox = (0, 0, 0)

    chk_ok = read_attr(me, "chk_ok")
    chk_n = read_attr(me, "chk_n")

    print(f"=== Кейс: {label} ===")
    print(f"  Параметры: {g2_params}")
    print(f"  Вершин VIS (трубки колец): {len(verts)}")
    print(f"  BBox (X,Y,Z) мм: {tuple(round(c,1) for c in bbox)}")
    print(f"  Провер_ВСЕ_OK = {chk_ok}")
    print(f"  Колец_всего = {chk_n}")

    obj_eval.to_mesh_clear()

    # --- рендер ---
    os.makedirs(out_dir, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 700
    scene.render.resolution_y = 900
    scene.render.filepath = os.path.join(out_dir, f"group2_{label}.png")

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

    return {"label": label, "bbox": bbox, "ok": chk_ok, "n": chk_n, "verts": len(verts)}


def main():
    argv = sys.argv
    out_dir = argv[argv.index("--") + 1] if "--" in argv else "/tmp/nk_preview2"

    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 0.001

    results = []
    results.append(run_case("default", {}, out_dir))
    results.append(run_case("crest_max", {
        "Гребень_острота_У_лодыжки": 1.0,
        "Гребень_острота_У_колена": 1.0,
        "Гребень_глубина_мм": 15.0,
    }, out_dir))
    results.append(run_case("calf_max", {
        "Икра_выступ_мм": 30.0,
        "Икра_ширина_доля": 0.15,
    }, out_dir))
    results.append(run_case("thin_leg", {
        "Обхват_Точка1_мм": 150.0,
        "Обхват_Точка2_мм": 250.0,
    }, out_dir))

    print("\n=== ИТОГ ===")
    all_ok = True
    for r in results:
        status = "OK" if r["ok"] else "FAIL/None"
        if not r["ok"]:
            all_ok = False
        print(f"  {r['label']:14s} bbox={tuple(round(c,1) for c in r['bbox'])} "
              f"rings={r['n']} verts={r['verts']} check={status}")
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ" if all_ok else "ЕСТЬ ПРОВАЛЕННЫЕ ПРОВЕРКИ")

    blend_path = os.path.join(out_dir, "group2_profile.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"Сохранено: {blend_path}")


if __name__ == "__main__":
    main()
