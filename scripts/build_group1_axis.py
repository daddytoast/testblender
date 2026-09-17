# -*- coding: utf-8 -*-
"""
ГРУППА 1 — "NK.1 Ось" (Vertical Axis)
=====================================
Строит пространственную кривую — центральную ось голени от точки A
(дистальная, уровень лодыжки) до точки B (проксимальная, уровень
колена), с учётом:
  - настраиваемой длины сегмента;
  - сагиттального наклона (перед/зад) и фронтального наклона
    (медиально/латерально) верхней точки;
  - положения и величины заднего прогиба оси на уровне максимального
    обхвата икроножной мышцы ("указание икры").

Координатная система проекта (единая для ВСЕХ групп 1-5):
    X — медиально-латеральная ось  (+X = латерально / наружу)
    Y — сагиттальная ось           (+Y = вперёд/передняя поверхность,
                                     -Y = назад/задняя поверхность, где икра)
    Z — вертикальная ось           (+Z = вверх, к колену)
    Начало координат (0,0,0) = точка A, дистальный конец сегмента
    (уровень лодыжки / стыка со стопой).
Единицы: 1 единица Blender = 1 миллиметр (мм). См. docs/00_overview.md.

Запуск (headless):
    blender --background --python scripts/build_group1_axis.py

Скрипт идемпотентен: повторный запуск полностью пересобирает группу
"NK.1_Ось" и демонстрационный объект "NK_Group1_Demo" с нуля.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from nodes_common import (
    new_group, add_input, add_output, add_node, make_frame, link,
    out_sock, in_sock,
)

GROUP_NAME = "NK.1_Ось"


def build():
    tree = new_group(GROUP_NAME)
    # Группа 1: строит вертикальную ось голени (кривую) с наклонами
    # и задним прогибом на уровне икры. См. docs/01_group1_axis.md

    # ------------------------------------------------------------------
    # ИНТЕРФЕЙС ГРУППЫ — входные параметры (диапазоны = средние
    # анатомические значения взрослого человека, м/ж, подлежат уточнению
    # под конкретного пациента).
    # ------------------------------------------------------------------
    # Геометрия на входе НЕ нужна: Группа 1 генерирует кривую "с нуля" и
    # игнорирует исходный меш объекта-носителя модификатора. Это штатный
    # для Geometry Nodes паттерн "генератор" (см. docs/00_overview.md).

    s_len = add_input(
        tree, "Длина_сегмента_мм", "NodeSocketFloat",
        default=350.0, min_value=150.0, max_value=500.0,
        description="Длина оси A→B: от уровня лодыжки до уровня колена, мм. "
                     "Средний анатомический диапазон взрослого 300-400 мм.")

    s_tilt_ap = add_input(
        tree, "Наклон_сагиттальный_град", "NodeSocketFloat",
        default=0.0, min_value=-10.0, max_value=10.0,
        description="Наклон верхней точки B вперёд(+)/назад(-) относительно "
                     "точки A, град. Имитирует сгибание/разгибание в приёмной "
                     "гильзе. Средний диапазон ±5°.")

    s_tilt_ml = add_input(
        tree, "Наклон_фронтальный_град", "NodeSocketFloat",
        default=0.0, min_value=-10.0, max_value=10.0,
        description="Наклон верхней точки B латерально(+)/медиально(-), "
                     "град. Имитирует вальгус/варус установки. "
                     "Средний диапазон ±5°.")

    s_calf_h = add_input(
        tree, "Высота_икры_доля_от_колена", "NodeSocketFloat",
        default=0.30, min_value=0.10, max_value=0.60,
        description="Где расположен максимум обхвата икры, в долях длины "
                     "сегмента, ОТСЧЁТ ОТ КОЛЕНА (точки B) вниз. "
                     "0.30 = икра максимальна на 30% длины ниже колена "
                     "(типично для верхней трети голени).")

    s_calf_bow = add_input(
        tree, "Прогиб_икры_мм", "NodeSocketFloat",
        default=15.0, min_value=0.0, max_value=40.0,
        description="Дополнительное смещение ОСИ назад (-Y) на уровне "
                     "максимума икры, мм. Это прогиб центральной линии, "
                     "НЕ полный профиль мышцы (профиль сечения — Группа 2).")

    s_res = add_input(
        tree, "Разрешение", "NodeSocketInt",
        default=48, min_value=8, max_value=200,
        description="Количество точек итоговой кривой после равномерной "
                     "передискретизации по длине дуги.")

    # ВАЖНО: порядок add_output для Geometry-сокетов имеет значение —
    # Blender показывает в 3D-вьюпорте геометрию ПЕРВОГО выходного
    # сокета типа Geometry. Пока нет настоящей оболочки (Группа 3),
    # первым делаем VIS_Труба, чтобы сразу видеть результат.
    out_vis = add_output(tree, "VIS_Труба", "NodeSocketGeometry",
                          "Временная визуализация (тонкая труба по оси). "
                          "При переходе к Группе 3 перестанет быть первым "
                          "выходом — его место займёт настоящая оболочка.")
    out_curve = add_output(tree, "Ось_кривая", "NodeSocketGeometry",
                            "Главный результат: кривая оси A→C→B для Групп 2-3.")
    out_a = add_output(tree, "Точка_A", "NodeSocketVector",
                        "Дистальная точка (лодыжка), мировые координаты.")
    out_b = add_output(tree, "Точка_B", "NodeSocketVector",
                        "Проксимальная точка (колено), мировые координаты.")
    out_len = add_output(tree, "Факт_длина_дуги_мм", "NodeSocketFloat",
                          "Фактическая длина кривой после ресемплинга.")
    out_ok = add_output(tree, "Провер_ВСЕ_OK", "NodeSocketBool",
                         "Итог всех проверок Группы 1 (см. секцию 8).")
    out_report = add_output(tree, "Провер_Отчёт", "NodeSocketString",
                             "Текстовый отчёт проверок для Spreadsheet.")

    nodes = tree.nodes
    gin = nodes.new("NodeGroupInput")
    gin.name = "1.01 Вход"
    gin.label = "1.01 Входные параметры"
    gin.location = (-200, 400)

    gout = nodes.new("NodeGroupOutput")
    gout.name = "1.99 Выход"
    gout.label = "1.99 Выходные сокеты группы"
    gout.location = (3600, 400)

    def GI(name):
        return gin.outputs[name]

    def GO(name):
        return gout.inputs[name]

    # ------------------------------------------------------------------
    # СЕКЦИЯ 2: расчёт точки B (проксимальная, колено) с учётом наклонов
    # ------------------------------------------------------------------
    n102 = add_node(tree, "ShaderNodeMath", "1.02", "Наклон AP -> рад",
                     150, 500, operation='RADIANS')
    tree.links.new(GI("Наклон_сагиттальный_град"), in_sock(n102, "Value"))

    n103 = add_node(tree, "ShaderNodeMath", "1.03", "Наклон ML -> рад",
                     150, 340, operation='RADIANS')
    tree.links.new(GI("Наклон_фронтальный_град"), in_sock(n103, "Value"))

    n104 = add_node(tree, "ShaderNodeCombineXYZ", "1.04",
                     "Сборка Euler-поворота (X=AP,Y=ML)", 420, 420)
    link(tree, n102, "Value", n104, "X")
    link(tree, n103, "Value", n104, "Y")
    # Z поворота = 0 (без кручения вокруг вертикали) -> оставляем 0 по умолчанию

    n105 = add_node(tree, "ShaderNodeCombineXYZ", "1.05",
                     "Вектор до наклона (0,0,Длина)", 150, 180)
    tree.links.new(GI("Длина_сегмента_мм"), in_sock(n105, "Z"))

    n106 = add_node(tree, "FunctionNodeRotateVector", "1.06",
                     "Точка B (колено, после наклона)", 700, 300)
    link(tree, n105, "Vector", n106, "Vector")
    # Rotation ожидает тип ROTATION, а мы собрали Euler как VECTOR (1.04) ->
    # конвертируем явным узлом 1.04b Euler->Rotation
    n104b = add_node(tree, "FunctionNodeEulerToRotation", "1.04b",
                      "Euler(вектор) -> Rotation", 560, 420)
    link(tree, n104, "Vector", n104b, "Euler")
    link(tree, n104b, "Rotation", n106, "Rotation")

    frame2 = make_frame(
        tree, "2. НАКЛОН ТОЧКИ B (колено)",
        [n102, n103, n104, n104b, n105, n106])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 3: точка A (дистальная) — фиксированное начало координат
    # ------------------------------------------------------------------
    n107 = add_node(tree, "FunctionNodeInputVector", "1.07",
                     "Точка A (лодыжка) = начало координат", 150, -20,
                     vector=(0.0, 0.0, 0.0))
    frame3 = make_frame(tree, "3. ТОЧКА A (лодыжка, начало координат)", [n107])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 4: точка C (Middle) — прогиб оси на уровне икры
    # ------------------------------------------------------------------
    n108 = add_node(tree, "ShaderNodeMath", "1.08",
                     "Доля от лодыжки = 1 - доля от колена",
                     150, -220, operation='SUBTRACT')
    in_sock(n108, "Value").default_value = 1.0
    tree.links.new(GI("Высота_икры_доля_от_колена"), in_sock(n108, "Value_001"))

    n109 = add_node(tree, "ShaderNodeMix", "1.09",
                     "Точка на прямой A-B на высоте икры",
                     1000, 100, data_type='VECTOR')
    link(tree, n107, "Vector", n109, "A_Vector")
    link(tree, n106, "Vector", n109, "B_Vector")
    link(tree, n108, "Value", n109, "Factor_Float")

    n110 = add_node(tree, "ShaderNodeCombineXYZ", "1.10",
                     "Направление 'назад' (-Y)", 420, -180)
    in_sock(n110, "Y").default_value = -1.0

    n111 = add_node(tree, "ShaderNodeVectorMath", "1.11",
                     "Смещение назад = направление * Прогиб_икры_мм",
                     700, -180, operation='SCALE')
    link(tree, n110, "Vector", n111, "Vector")
    tree.links.new(GI("Прогиб_икры_мм"), in_sock(n111, "Scale"))

    n112 = add_node(tree, "ShaderNodeVectorMath", "1.12",
                     "Точка C (Middle) = точка_на_прямой + смещение_назад",
                     1300, -20, operation='ADD')
    link(tree, n109, "Result_Vector", n112, "Vector")
    link(tree, n111, "Vector", n112, "Vector_001")

    frame4 = make_frame(
        tree, "4. ТОЧКА ПРОГИБА ИКРЫ (точка C, middle кривой)",
        [n108, n109, n110, n111, n112])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 5: построение кривой A -> C -> B
    # ------------------------------------------------------------------
    n113 = add_node(tree, "GeometryNodeCurveQuadraticBezier", "1.13",
                     "Кривая: Quadratic Bezier (A -> C -> B)", 1650, 250)
    in_sock(n113, "Resolution").default_value = 64  # внутреннее разрешение перед ресемплингом
    link(tree, n107, "Vector", n113, "Start")
    link(tree, n112, "Vector", n113, "Middle")
    link(tree, n106, "Vector", n113, "End")

    n114 = add_node(tree, "GeometryNodeResampleCurve", "1.14",
                     "Ресемплинг по длине дуги (равномерный шаг)",
                     1950, 250, mode='COUNT')
    link(tree, n113, "Curve", n114, "Curve")
    tree.links.new(GI("Разрешение"), in_sock(n114, "Count"))

    frame5 = make_frame(tree, "5. ПОСТРОЕНИЕ КРИВОЙ A -> C -> B", [n113, n114])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 6: фактическая длина дуги (для проверок и для Группы 2)
    # ------------------------------------------------------------------
    n115 = add_node(tree, "GeometryNodeCurveLength", "1.15",
                     "Фактическая длина дуги кривой", 2250, 500)
    link(tree, n114, "Curve", n115, "Curve")
    frame6 = make_frame(tree, "6. ДЛИНА ДУГИ", [n115])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 7: временная визуализация (труба вдоль оси) — только чтобы
    # ВИДЕТЬ результат в 3D до появления настоящей оболочки (Группа 3).
    # ------------------------------------------------------------------
    n116 = add_node(tree, "GeometryNodeCurvePrimitiveCircle", "1.16",
                     "VIS: профиль-кружок d=10мм", 1950, -20)
    in_sock(n116, "Radius").default_value = 5.0

    n117 = add_node(tree, "GeometryNodeCurveToMesh", "1.17",
                     "VIS: труба вдоль оси (Curve to Mesh)", 2250, 100)
    link(tree, n114, "Curve", n117, "Curve")
    link(tree, n116, "Curve", n117, "Profile Curve")
    in_sock(n117, "Fill Caps").default_value = True

    frame7 = make_frame(
        tree, "7. ВРЕМЕННАЯ ВИЗУАЛИЗАЦИЯ (снять при переходе к Группе 3)",
        [n116, n117])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 8: ПРОВЕРКИ (V1.1 .. V1.9)
    # ------------------------------------------------------------------
    v11 = add_node(tree, "GeometryNodeAttributeDomainSize", "V1.1",
                    "Кол-во точек кривой", 2250, 850, component='CURVE')
    link(tree, n114, "Curve", v11, "Geometry")

    v12 = add_node(tree, "FunctionNodeCompare", "V1.2",
                    "Точки == Разрешение?", 2550, 850,
                    data_type='INT', operation='EQUAL')
    link(tree, v11, "Point Count", v12, "A_INT")
    tree.links.new(GI("Разрешение"), in_sock(v12, "B_INT"))

    v13 = add_node(tree, "GeometryNodeBoundBox", "V1.3",
                    "BBox кривой", 2250, 650)
    link(tree, n114, "Curve", v13, "Geometry")

    v14 = add_node(tree, "ShaderNodeVectorMath", "V1.4",
                    "Размер BBox = Max - Min", 2550, 650,
                    operation='SUBTRACT')
    link(tree, v13, "Max", v14, "Vector")
    link(tree, v13, "Min", v14, "Vector_001")

    v15 = add_node(tree, "ShaderNodeSeparateXYZ", "V1.5",
                    "Разбор размеров BBox", 2850, 650)
    link(tree, v14, "Vector", v15, "Vector")

    v16 = add_node(tree, "FunctionNodeCompare", "V1.6",
                    "Высота BBox <= заданной длины?", 3150, 700,
                    data_type='FLOAT', operation='LESS_EQUAL')
    link(tree, v15, "Z", v16, "A")
    tree.links.new(GI("Длина_сегмента_мм"), in_sock(v16, "B"))

    n118 = add_node(tree, "ShaderNodeMath", "1.18",
                     "Порог 50% от длины (для проверки вырождения)",
                     2850, 480, operation='MULTIPLY')
    tree.links.new(GI("Длина_сегмента_мм"), in_sock(n118, "Value"))
    in_sock(n118, "Value_001").default_value = 0.5

    v17 = add_node(tree, "FunctionNodeCompare", "V1.7",
                    "Высота BBox > 50% длины? (не вырождена)",
                    3150, 480, data_type='FLOAT', operation='GREATER_THAN')
    link(tree, v15, "Z", v17, "A")
    link(tree, n118, "Value", v17, "B")

    v18 = add_node(tree, "FunctionNodeBooleanMath", "V1.8",
                    "И: (точки=OK) И (высота<=длина)", 3400, 800,
                    operation='AND')
    link(tree, v12, "Result", v18, "Boolean")
    link(tree, v16, "Result", v18, "Boolean_001")

    v19 = add_node(tree, "FunctionNodeBooleanMath", "V1.9",
                    "ИТОГ: все проверки Группы 1 пройдены",
                    3650, 700, operation='AND')
    link(tree, v18, "Boolean", v19, "Boolean")
    link(tree, v17, "Result", v19, "Boolean_001")

    frame8 = make_frame(
        tree, "8. ПРОВЕРКИ (V1.1 - V1.9)",
        [v11, v12, v13, v14, v15, v16, n118, v17, v18, v19])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 9: текстовый отчёт + финальный выход
    # ------------------------------------------------------------------
    n119 = add_node(tree, "FunctionNodeValueToString", "1.19",
                     "Высота BBox -> строка (1 знак)", 3150, 250,
                     )
    link(tree, v15, "Z", n119, "Value")
    in_sock(n119, "Decimals").default_value = 1

    n120 = add_node(tree, "FunctionNodeValueToString", "1.20",
                     "Кол-во точек -> строка", 3150, 120)
    # Point Count (INT) -> Value (FLOAT) сокет ValueToString принимает VALUE(float);
    # неявное приведение INT->FLOAT в Blender geo nodes выполняется автоматически при связывании
    link(tree, v11, "Point Count", n120, "Value")
    in_sock(n120, "Decimals").default_value = 0

    n121 = add_node(tree, "GeometryNodeStringJoin", "1.21",
                     "Сборка строки отчёта", 3400, 200)
    in_sock(n121, "Delimiter").default_value = " | "
    # Strings - множественный вход, подключаем оба через один сокет "Strings"
    # (Blender допускает несколько связей в один вход-массив StringJoin)
    tree.links.new(n119.outputs["String"], n121.inputs["Strings"])
    tree.links.new(n120.outputs["String"], n121.inputs["Strings"])

    frame9 = make_frame(tree, "9. ТЕКСТОВЫЙ ОТЧЁТ", [n119, n120, n121])

    # ------------------------------------------------------------------
    # Финальные соединения в Group Output
    # ------------------------------------------------------------------
    tree.links.new(n114.outputs["Curve"], GO("Ось_кривая"))
    tree.links.new(n117.outputs["Mesh"], GO("VIS_Труба"))
    tree.links.new(n107.outputs["Vector"], GO("Точка_A"))
    tree.links.new(n106.outputs["Vector"], GO("Точка_B"))
    tree.links.new(n115.outputs["Length"], GO("Факт_длина_дуги_мм"))
    tree.links.new(v19.outputs["Boolean"], GO("Провер_ВСЕ_OK"))
    tree.links.new(n121.outputs["String"], GO("Провер_Отчёт"))

    return tree


def build_demo_object(tree):
    """Создаёт демонстрационный объект с модификатором Geometry Nodes,
    ссылающимся на группу NK.1_Ось, чтобы результат было видно в 3D
    и можно было программно проверить (см. verify_group1.py)."""
    name = "NK_Group1_Demo"
    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    mesh = bpy.data.meshes.new(name + "_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    mod = obj.modifiers.new("NK_1_Ось", "NODES")
    mod.node_group = tree

    # Финальный видимый выход модификатора = VIS-труба (Группа 1 ещё не
    # содержит настоящей оболочки — она появится в Группе 3).
    # Найдём identifier сокета "VIS_Труба" и "Geometry" в интерфейсе,
    # чтобы явно связать выход модификатора именно с трубой для просмотра.
    return obj, mod


if __name__ == "__main__":
    tree = build()
    obj, mod = build_demo_object(tree)
    print("OK: группа '%s' собрана, узлов: %d" % (GROUP_NAME, len(tree.nodes)))
