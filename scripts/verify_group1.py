# -*- coding: utf-8 -*-
"""
Автоматическая проверка Группы 1 ("NK.1_Ось").

Что делает:
  1. Собирает группу заново (build_group1_axis.build()).
  2. Создаёт демо-объект с модификатором.
  3. Прогоняет несколько наборов параметров (умолчания, наклоны, крайние
     значения) через evaluated_depsgraph_get() и печатает факт. результаты:
     высоту BBox, длину дуги, число точек, и содержимое узлов-проверок
     V1.1-V1.9 (через именованные атрибуты, куда их "запекает" модификатор).
  4. Рендерит превью (Workbench solid) в PNG для каждого набора, чтобы
     визуально подтвердить форму оси (наклон/прогиб).
  5. Сохраняет итоговый .blend файл.

Запуск:
    blender --background --python scripts/verify_group1.py -- <out_dir>
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from build_group1_axis import build, build_demo_object, GROUP_NAME


def socket_identifier(tree, name, in_out='OUTPUT'):
    for item in tree.interface.items_tree:
        if item.item_type == 'SOCKET' and item.in_out == in_out and item.name == name:
            return item.identifier
    raise KeyError(name)


def set_input(obj_mod, tree, name, value):
    ident = socket_identifier(tree, name, 'INPUT')
    obj_mod[ident] = value


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


def run_case(label, params, out_dir):
    tree = build()
    obj, mod = build_demo_object(tree)

    for k, v in params.items():
        set_input(mod, tree, k, v)

    # Запекаем проверочные выходы как именованные атрибуты, чтобы прочитать
    # их значения из евалюированного меша (иначе они "невидимы" в Python).
    bake_output_as_attribute(mod, tree, "Провер_ВСЕ_OK", "chk_all_ok")
    bake_output_as_attribute(mod, tree, "Факт_длина_дуги_мм", "chk_len")

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

    chk_ok = read_attr(me, "chk_all_ok")
    chk_len = read_attr(me, "chk_len")

    print(f"=== Кейс: {label} ===")
    print(f"  Параметры: {params}")
    print(f"  Вершин VIS-трубы: {len(verts)}")
    print(f"  BBox (X,Y,Z) мм: {tuple(round(c,1) for c in bbox)}")
    print(f"  Провер_ВСЕ_OK (атрибут) = {chk_ok}")
    print(f"  Факт_длина_дуги_мм (атрибут) = {chk_len}")

    obj_eval.to_mesh_clear()

    # --- Рендер превью ---
    os.makedirs(out_dir, exist_ok=True)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = 700
    scene.render.resolution_y = 900
    scene.render.filepath = os.path.join(out_dir, f"group1_{label}.png")

    # Камера и свет, смотрящая спереди (по -Y) на объект, ось Z вверх
    # Геометрия хранится как "1 юнит Blender = 1 мм" (сырые числа, без
    # масштабирования координат) -> камеру считаем тоже в мм.
    cz = bbox[2] / 2.0 if bbox[2] else 175.0
    cam_data = bpy.data.cameras.new("PreviewCam")
    cam_data.type = 'ORTHO'
    cam_data.ortho_scale = max(bbox[2], 200) * 1.25
    cam = bpy.data.objects.new("PreviewCam", cam_data)
    bpy.context.collection.objects.link(cam)
    cam.location = (0, -900.0, cz)
    cam.rotation_euler = (math.radians(90), 0, 0)
    scene.camera = cam

    light_data = bpy.data.lights.new("PreviewSun", type='SUN')
    light_data.energy = 3.0
    light = bpy.data.objects.new("PreviewSun", light_data)
    bpy.context.collection.objects.link(light)
    light.rotation_euler = (math.radians(55), 0, math.radians(35))

    bpy.ops.render.render(write_still=True)

    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.cameras.remove(cam_data)
    bpy.data.objects.remove(light, do_unlink=True)
    bpy.data.lights.remove(light_data)

    return {"label": label, "bbox": bbox, "ok": chk_ok, "len": chk_len, "n": len(verts)}


def main():
    argv = sys.argv
    out_dir = argv[argv.index("--") + 1] if "--" in argv else "/tmp/nk_preview"

    # 1 unit Blender = 1 mm -> ставим Unit Scale = 0.001, чтобы линейка/
    # экспорт STL показывали корректные миллиметры (см. docs/00_overview.md)
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 0.001

    results = []
    results.append(run_case("default", {}, out_dir))
    results.append(run_case("tilt", {
        "Наклон_сагиттальный_град": 8.0,
        "Наклон_фронтальный_град": -6.0,
    }, out_dir))
    results.append(run_case("calfbow_max", {
        "Прогиб_икры_мм": 40.0,
        "Высота_икры_мм_от_колена": 105.0,
    }, out_dir))
    results.append(run_case("extreme_length", {
        "Длина_сегмента_мм": 500.0,
        "Разрешение": 96,
    }, out_dir))
    results.append(run_case("lateral_bow_left", {
        "Боковой_прогиб_мм": 20.0,
        "Сторона_ноги": -1.0,
    }, out_dir))
    results.append(run_case("calf_height_clamp", {
        "Высота_икры_мм_от_колена": 250.0,  # больше длины по умолчанию -> должно зажаться, не сломаться
    }, out_dir))

    print("\n=== ИТОГ ===")
    all_ok = True
    for r in results:
        status = "OK" if r["ok"] else "FAIL/None"
        if not r["ok"]:
            all_ok = False
        print(f"  {r['label']:16s} bbox={tuple(round(c,1) for c in r['bbox'])} "
              f"len={r['len']} n={r['n']} check={status}")
    print("ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ" if all_ok else "ЕСТЬ ПРОВАЛЕННЫЕ ПРОВЕРКИ")

    blend_path = os.path.join(out_dir, "group1_axis.blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"Сохранено: {blend_path}")


if __name__ == "__main__":
    main()
