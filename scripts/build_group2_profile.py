# -*- coding: utf-8 -*-
"""
ГРУППА 2 — "NK.2_Профиль" (Variable Cross-Section Profile)
============================================================
Строит СЕМЕЙСТВО поперечных сечений голени вдоль оси (кривой из
Группы 1): для каждой точки оси — своё "кольцо" точек, форма и размер
которого зависят от высоты T (0 = лодыжка, 1 = колено):

  - общий размер кольца интерполируется между 2 заданными обхватами
    (измерены в 2 точках высоты — как реально снимает мерки протезист);
  - спереди (гребень большеберцовой кости) — сечение "подрезается" по
    бокам от гребня, что визуально читается как переход от округлого
    (у колена) к острому гребню (у лодыжки);
  - сзади (икроножная мышца) — кольцо получает выступ, максимальный на
    заданной высоте икры, с плавным затуханием вверх/вниз.

КЛЮЧЕВАЯ ТЕХНИКА (без циклов/Repeat Zone, чисто на полях):
  1. На точках оси "запекаем" (Store Named Attribute) их параметр
     высоты T, индекс и позицию.
  2. Одну "болванку" кольца (окружность радиуса 1, Mesh Circle) с
     запечённым направлением (dir = Position) инстансируем на все
     точки оси (Instance on Points).
  3. Realize Instances разворачивает N инстансов в плоское облако
     точек N*M — и, что важно, атрибуты, запечённые на точках оси
     (T, индекс, центр), автоматически "спускаются" на все M точек
     своего кольца. Проверено отдельным тестом перед сборкой.
  4. Дальше это обычная работа с полями: читаем T и dir через
     Named Attribute, считаем нужный радиус R(dir, T) обычной
     арифметикой, и переставляем точки на новую позицию.

Единицы и система координат — те же, что в Группе 1
(docs/00_overview.md): 1 юнит = 1 мм; X-мед/лат, Y-перед/зад,
Z-вверх; curve из Группы 1 параметризована от t=0 (лодыжка) до t=1
(колено).

Запуск:
    blender --background --python scripts/build_group2_profile.py
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

GROUP_NAME = "NK.2_Профиль"
TWO_PI = 2.0 * math.pi


def named_attr(tree, num, label, x, y, attr_name, data_type):
    n = add_node(tree, "GeometryNodeInputNamedAttribute", num, label, x, y,
                 data_type=data_type)
    in_sock(n, "Name").default_value = attr_name
    return n


def build():
    tree = new_group(GROUP_NAME)

    # ------------------------------------------------------------------
    # ИНТЕРФЕЙС
    # ------------------------------------------------------------------
    add_input(tree, "Ось_кривая", "NodeSocketGeometry",
               description="Кривая оси из Группы 1 (NK.1_Ось, выход 'Ось_кривая'), "
                            "уже равномерно передискретизированная.")

    s_len = add_input(tree, "Длина_сегмента_мм", "NodeSocketFloat",
                       default=350.0, min_value=150.0, max_value=500.0,
                       description="То же значение, что в Группе 1 (Длина_сегмента_мм или "
                                    "выход 'Факт_длина_дуги_мм') — нужно, чтобы перевести "
                                    "измерения 'мм от колена' в долю длины оси.")

    s_side = add_input(tree, "Сторона_ноги", "NodeSocketFloat",
                        default=1.0, min_value=-1.0, max_value=1.0,
                        description="1 = правая нога, -1 = левая — из Группы 1 (выход "
                                     "'Сторона_ноги'). Зеркалит смещение гребня.")

    s_c1 = add_input(tree, "Обхват_Точка1_мм", "NodeSocketFloat",
                      default=220.0, min_value=150.0, max_value=350.0,
                      description="Обхват (длина окружности) в одной из контрольных точек "
                                   "(типично над лодыжками), мм. Порядок Точка1/Точка2 не "
                                   "важен — группа сама определяет, какая точка выше.")
    s_c1f = add_input(tree, "Точка1_мм_от_колена", "NodeSocketFloat",
                       default=308.0, min_value=0.0, max_value=480.0,
                       description="Высота точки обхвата 1 — мм от колена вниз (замер лентой). "
                                    "308мм ≈ у лодыжек при длине сегмента 350мм.")
    s_c2 = add_input(tree, "Обхват_Точка2_мм", "NodeSocketFloat",
                      default=340.0, min_value=250.0, max_value=450.0,
                      description="Обхват в другой контрольной точке (типично зона "
                                   "максимума икры), мм.")
    s_c2f = add_input(tree, "Точка2_мм_от_колена", "NodeSocketFloat",
                       default=105.0, min_value=0.0, max_value=480.0,
                       description="Высота точки обхвата 2 — мм от колена вниз. "
                                    "105мм ≈ зона максимума икры при длине 350мм.")

    s_calf_h = add_input(tree, "Высота_икры_мм_от_колена", "NodeSocketFloat",
                          default=105.0, min_value=40.0, max_value=250.0,
                          description="Центр выступа икры — мм от колена вниз. "
                                       "Держите тем же значением, что в Группе 1.")
    s_calf_bulge = add_input(tree, "Икра_выступ_мм", "NodeSocketFloat",
                              default=12.0, min_value=0.0, max_value=30.0,
                              description="Максимальная добавка радиуса сзади на высоте икры, мм.")
    s_calf_w = add_input(tree, "Икра_ширина_доля", "NodeSocketFloat",
                          default=0.25, min_value=0.10, max_value=0.50,
                          description="Полуширина затухания выступа икры, доля длины сегмента.")

    s_sharp_ankle = add_input(tree, "Гребень_острота_У_лодыжки", "NodeSocketFloat",
                               default=0.85, min_value=0.0, max_value=1.0,
                               description="Острота гребня большеберцовой кости у лодыжки (0=круглое, 1=макс. острое).")
    s_sharp_knee = add_input(tree, "Гребень_острота_У_колена", "NodeSocketFloat",
                              default=0.15, min_value=0.0, max_value=1.0,
                              description="Острота гребня у колена (обычно ниже — больше мягких тканей).")
    s_crest_depth = add_input(tree, "Гребень_глубина_мм", "NodeSocketFloat",
                               default=6.0, min_value=0.0, max_value=15.0,
                               description="Максимальная глубина подрезки по бокам от гребня, мм.")
    s_crest_shift = add_input(tree, "Гребень_смещение_град", "NodeSocketFloat",
                               default=8.0, min_value=0.0, max_value=20.0,
                               description="Смещение направления гребня от строго переднего "
                                            "(+Y) в сторону — большеберцовый гребень анатомически "
                                            "не по центру голени, а слегка медиально. Знак "
                                            "определяется Стороной_ноги.")

    s_oval = add_input(tree, "Овальность_у_лодыжки_мм", "NodeSocketFloat",
                        default=4.0, min_value=-15.0, max_value=15.0,
                        description="Лёгкая овальность сечения у лодыжки: положительное "
                                     "значение = шире медиально-латерально (X), уже "
                                     "спереди-назад (Y) — типично для зоны над лодыжками.")
    s_oval_len = add_input(tree, "Овальность_протяжённость_доля", "NodeSocketFloat",
                            default=0.25, min_value=0.05, max_value=0.5,
                            description="На какой доле длины (от лодыжки вверх) овальность "
                                         "плавно сходит на нет.")

    s_res = add_input(tree, "Разрешение_кольца", "NodeSocketInt",
                       default=32, min_value=12, max_value=64,
                       description="Число точек в каждом кольце сечения.")

    out_vis = add_output(tree, "VIS_Кольца", "NodeSocketGeometry",
                          "Временная визуализация: каждое кольцо показано тонкой трубкой.")
    out_pts = add_output(tree, "Профиль_точки", "NodeSocketGeometry",
                          "Облако точек N колец x M точек, с атрибутами ring_T/ring_index "
                          "для Группы 3.")
    out_curves = add_output(tree, "Кольца_кривые", "NodeSocketGeometry",
                             "Те же точки, сгруппированные в N замкнутых кривых (по кольцу) — "
                             "удобный вход для лофта в Группе 3.")
    out_m = add_output(tree, "Точек_в_кольце", "NodeSocketInt", "= Разрешение_кольца, для Группы 3.")
    out_n = add_output(tree, "Колец_всего", "NodeSocketInt", "Число колец = число точек оси.")
    out_ok = add_output(tree, "Провер_ВСЕ_OK", "NodeSocketBool", "Итог проверок Группы 2.")
    out_report = add_output(tree, "Провер_Отчёт", "NodeSocketString", "Текстовый отчёт.")

    nodes = tree.nodes
    gin = nodes.new("NodeGroupInput")
    gin.name = "2.01 Вход"; gin.label = "2.01 Входные параметры"; gin.location = (-300, 500)
    gout = nodes.new("NodeGroupOutput")
    gout.name = "2.99 Выход"; gout.label = "2.99 Выходные сокеты группы"; gout.location = (3800, 500)

    def GI(name):
        return gin.outputs[name]

    def GO(name):
        return gout.inputs[name]

    # ------------------------------------------------------------------
    # СЕКЦИЯ 2: подготовка точек оси — запекаем T, центр, индекс
    # ------------------------------------------------------------------
    n202 = add_node(tree, "GeometryNodeSplineParameter", "2.02",
                     "T и индекс каждой точки оси", 0, 250)

    n202p = add_node(tree, "GeometryNodeInputPosition", "2.02p",
                      "Позиция каждой точки оси", 0, 60)

    n203 = add_node(tree, "GeometryNodeStoreNamedAttribute", "2.03",
                     "Запись 'ring_T'", 260, 300, domain='POINT', data_type='FLOAT')
    in_sock(n203, "Name").default_value = "ring_T"
    tree.links.new(GI("Ось_кривая"), in_sock(n203, "Geometry"))
    link(tree, n202, "Factor", n203, "Value_Float")

    n204 = add_node(tree, "GeometryNodeStoreNamedAttribute", "2.04",
                     "Запись 'ring_center'", 520, 300, domain='POINT', data_type='FLOAT_VECTOR')
    in_sock(n204, "Name").default_value = "ring_center"
    link(tree, n203, "Geometry", n204, "Geometry")
    link(tree, n202p, "Position", n204, "Value_Vector")

    n205 = add_node(tree, "GeometryNodeStoreNamedAttribute", "2.05",
                     "Запись 'ring_index'", 780, 300, domain='POINT', data_type='INT')
    in_sock(n205, "Name").default_value = "ring_index"
    link(tree, n204, "Geometry", n205, "Geometry")
    link(tree, n202, "Index", n205, "Value_Int")

    frame2 = make_frame(tree, "2. ПОДГОТОВКА ТОЧЕК ОСИ (T, центр, индекс кольца)",
                         [n202, n202p, n203, n204, n205])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 3: болванка кольца (единичная окружность)
    # ------------------------------------------------------------------
    n206 = add_node(tree, "GeometryNodeMeshCircle", "2.06",
                     "Болванка: окружность радиуса 1", 260, -60, fill_type='NONE')
    tree.links.new(GI("Разрешение_кольца"), in_sock(n206, "Vertices"))
    in_sock(n206, "Radius").default_value = 1.0

    n206p = add_node(tree, "GeometryNodeInputPosition", "2.06p",
                      "Позиция точки болванки", 260, -220)

    n207 = add_node(tree, "GeometryNodeStoreNamedAttribute", "2.07",
                     "Запись 'dir' (направление точки)", 520, -100,
                     domain='POINT', data_type='FLOAT_VECTOR')
    in_sock(n207, "Name").default_value = "dir"
    link(tree, n206, "Mesh", n207, "Geometry")
    link(tree, n206p, "Position", n207, "Value_Vector")

    frame3 = make_frame(tree, "3. БОЛВАНКА КОЛЬЦА (окружность r=1, направление = 'dir')",
                         [n206, n206p, n207])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 4: инстансирование болванки на точки оси + разворачивание
    # ------------------------------------------------------------------
    n208 = add_node(tree, "GeometryNodeInstanceOnPoints", "2.08",
                     "Инстансировать кольцо на каждую точку оси", 1040, 100)
    link(tree, n205, "Geometry", n208, "Points")
    link(tree, n207, "Geometry", n208, "Instance")

    n209 = add_node(tree, "GeometryNodeRealizeInstances", "2.09",
                     "Realize Instances (N колец -> облако N*M точек)", 1300, 100)
    link(tree, n208, "Instances", n209, "Geometry")

    frame4 = make_frame(tree, "4. ИНСТАНСИРОВАНИЕ И РАЗВОРАЧИВАНИЕ", [n208, n209])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 5: базовый радиус R_base(T) — интерполяция по 2 обхватам
    # ПРАВКА: Точка1/Точка2 заданы в мм от колена (не в долях) и точка
    # 1 не обязана быть НИЖЕ точки 2 — группа сама сортирует T1/T2, что
    # чинит баг "обхват в нижней точке иногда срабатывает сверху"
    # (раньше Map Range молча ломался, если From Min > From Max).
    # ------------------------------------------------------------------
    n210f = add_node(tree, "ShaderNodeMath", "2.10f",
                      "доля1_от_колена = Точка1_мм / Длина (зажато 0..1)",
                      -260, -430, operation='DIVIDE', use_clamp=True)
    tree.links.new(GI("Точка1_мм_от_колена"), in_sock(n210f, "Value"))
    tree.links.new(GI("Длина_сегмента_мм"), in_sock(n210f, "Value_001"))

    n210 = add_node(tree, "ShaderNodeMath", "2.10",
                     "T1 = 1 - доля1_от_колена", 0, -500, operation='SUBTRACT')
    in_sock(n210, "Value").default_value = 1.0
    link(tree, n210f, "Value", n210, "Value_001")

    n211f = add_node(tree, "ShaderNodeMath", "2.11f",
                      "доля2_от_колена = Точка2_мм / Длина (зажато 0..1)",
                      -260, -600, operation='DIVIDE', use_clamp=True)
    tree.links.new(GI("Точка2_мм_от_колена"), in_sock(n211f, "Value"))
    tree.links.new(GI("Длина_сегмента_мм"), in_sock(n211f, "Value_001"))

    n211 = add_node(tree, "ShaderNodeMath", "2.11",
                     "T2 = 1 - доля2_от_колена", 0, -650, operation='SUBTRACT')
    in_sock(n211, "Value").default_value = 1.0
    link(tree, n211f, "Value", n211, "Value_001")

    n212 = add_node(tree, "ShaderNodeMath", "2.12",
                     "R1 = Обхват1 / 2пи", 260, -500, operation='DIVIDE')
    tree.links.new(GI("Обхват_Точка1_мм"), in_sock(n212, "Value"))
    in_sock(n212, "Value_001").default_value = TWO_PI

    n213 = add_node(tree, "ShaderNodeMath", "2.13",
                     "R2 = Обхват2 / 2пи", 260, -650, operation='DIVIDE')
    tree.links.new(GI("Обхват_Точка2_мм"), in_sock(n213, "Value"))
    in_sock(n213, "Value_001").default_value = TWO_PI

    n213cmp = add_node(tree, "FunctionNodeCompare", "2.13cmp",
                        "T1 < T2 ? (какая точка ниже)", 560, -430,
                        data_type='FLOAT', operation='LESS_THAN')
    link(tree, n210, "Value", n213cmp, "A")
    link(tree, n211, "Value", n213cmp, "B")

    def sorter(num, label, x, y, val_if_1_lower, val_if_2_lower):
        sw = add_node(tree, "GeometryNodeSwitch", num, label, x, y, input_type='FLOAT')
        link(tree, n213cmp, "Result", sw, "Switch")
        tree.links.new(val_if_2_lower, in_sock(sw, "False"))
        tree.links.new(val_if_1_lower, in_sock(sw, "True"))
        return sw

    n213tlo = sorter("2.13tlo", "T_low = T1<T2 ? T1 : T2", 820, -350,
                      n210.outputs["Value"], n211.outputs["Value"])
    n213thi = sorter("2.13thi", "T_high = T1<T2 ? T2 : T1", 820, -500,
                      n211.outputs["Value"], n210.outputs["Value"])
    n213rlo = sorter("2.13rlo", "R_low = T1<T2 ? R1 : R2", 820, -650,
                      n212.outputs["Value"], n213.outputs["Value"])
    n213rhi = sorter("2.13rhi", "R_high = T1<T2 ? R2 : R1", 820, -800,
                      n213.outputs["Value"], n212.outputs["Value"])

    n214 = named_attr(tree, "2.14", "Читаем 'ring_T' (после Realize)",
                       1560, -300, "ring_T", 'FLOAT')

    n215 = add_node(tree, "ShaderNodeMapRange", "2.15",
                     "R_base(T): линейная интерполяция R_low..R_high", 1120, -570,
                     data_type='FLOAT', clamp=True)
    link(tree, n214, "Attribute_Float", n215, "Value")
    tree.links.new(out_sock(n213tlo, "Output"), in_sock(n215, "From Min"))
    tree.links.new(out_sock(n213thi, "Output"), in_sock(n215, "From Max"))
    tree.links.new(out_sock(n213rlo, "Output"), in_sock(n215, "To Min"))
    tree.links.new(out_sock(n213rhi, "Output"), in_sock(n215, "To Max"))

    frame5 = make_frame(
        tree, "5. БАЗОВЫЙ РАДИУС R_base(T) — интерполяция между 2 обхватами "
        "(сортировка T1/T2 чинит баг 'сверху вместо снизу')",
        [n210f, n210, n211f, n211, n212, n213, n213cmp,
         n213tlo, n213thi, n213rlo, n213rhi, n214, n215])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 5b: dir -> X/Y (используется гребнем, икрой и овальностью)
    # ------------------------------------------------------------------
    n216 = named_attr(tree, "2.16", "Читаем 'dir' (после Realize)",
                       1560, 250, "dir", 'FLOAT_VECTOR')

    n217 = add_node(tree, "ShaderNodeSeparateXYZ", "2.17",
                     "Разбор dir -> X (лат.), Y (перед/зад)", 1820, 250)
    link(tree, n216, "Attribute_Vector", n217, "Vector")

    frame5b = make_frame(tree, "5b. dir -> X/Y (общее для секций 6,7,7b)", [n216, n217])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 6: гребень большеберцовой кости (перед, со смещением по
    # стороне ноги) — подрезка боков от гребня, сглаженная у шва
    # ------------------------------------------------------------------
    n219a = add_node(tree, "ShaderNodeMath", "2.19a",
                      "Гребень_смещение -> рад", 1560, 950, operation='RADIANS')
    tree.links.new(GI("Гребень_смещение_град"), in_sock(n219a, "Value"))

    n219b = add_node(tree, "ShaderNodeMath", "2.19b",
                      "* Сторона_ноги (знак смещения)", 1820, 950, operation='MULTIPLY')
    link(tree, n219a, "Value", n219b, "Value")
    tree.links.new(GI("Сторона_ноги"), in_sock(n219b, "Value_001"))

    n219c = add_node(tree, "ShaderNodeCombineXYZ", "2.19c",
                      "Euler(Z=смещение)", 2080, 950)
    link(tree, n219b, "Value", n219c, "Z")

    n219d = add_node(tree, "FunctionNodeEulerToRotation", "2.19d",
                      "Euler -> Rotation", 2340, 950)
    link(tree, n219c, "Vector", n219d, "Euler")

    n219e = add_node(tree, "FunctionNodeInputVector", "2.19e",
                      "(0,1,0) — 'строго вперёд'", 2080, 780, vector=(0.0, 1.0, 0.0))

    n219f = add_node(tree, "FunctionNodeRotateVector", "2.19f",
                      "front_ref = поворот (0,1,0) на смещение", 2600, 900)
    link(tree, n219e, "Vector", n219f, "Vector")
    link(tree, n219d, "Rotation", n219f, "Rotation")

    n219g = add_node(tree, "ShaderNodeVectorMath", "2.19g",
                      "dot(dir, front_ref)", 2860, 700, operation='DOT_PRODUCT')
    link(tree, n216, "Attribute_Vector", n219g, "Vector")
    link(tree, n219f, "Vector", n219g, "Vector_001")

    n218 = add_node(tree, "ShaderNodeMath", "2.18",
                     "w_front = max(dot, 0)", 3120, 700, operation='MAXIMUM')
    link(tree, n219g, "Value", n218, "Value")
    in_sock(n218, "Value_001").default_value = 0.0

    n218sq = add_node(tree, "ShaderNodeMath", "2.18sq",
                       "w_front_смягчённый = w_front^2 (убирает излом на шве)",
                       3380, 700, operation='MULTIPLY')
    link(tree, n218, "Value", n218sq, "Value")
    link(tree, n218, "Value", n218sq, "Value_001")

    n219 = add_node(tree, "ShaderNodeMath", "2.19",
                     "(1 - w_front_смягчённый)", 3640, 700, operation='SUBTRACT')
    in_sock(n219, "Value").default_value = 1.0
    link(tree, n218sq, "Value", n219, "Value_001")

    n220 = add_node(tree, "ShaderNodeMath", "2.20",
                     "w_front_см * (1-w_front_см)", 3900, 700, operation='MULTIPLY')
    link(tree, n218sq, "Value", n220, "Value")
    link(tree, n219, "Value", n220, "Value_001")

    n221 = add_node(tree, "ShaderNodeMath", "2.21",
                     "crest_indent = *4 (нормировка пика в 1.0)",
                     4160, 700, operation='MULTIPLY')
    link(tree, n220, "Value", n221, "Value")
    in_sock(n221, "Value_001").default_value = 4.0

    n222 = add_node(tree, "ShaderNodeMix", "2.22",
                     "острота(T) = mix(У_лодыжки, У_колена, T)",
                     1820, 470, data_type='FLOAT')
    tree.links.new(GI("Гребень_острота_У_лодыжки"), in_sock(n222, "A_Float"))
    tree.links.new(GI("Гребень_острота_У_колена"), in_sock(n222, "B_Float"))
    link(tree, n214, "Attribute_Float", n222, "Factor_Float")

    n223 = add_node(tree, "ShaderNodeMath", "2.23",
                     "depth(T) = острота(T) * Гребень_глубина_мм",
                     2080, 470, operation='MULTIPLY')
    link(tree, n222, "Result_Float", n223, "Value")
    tree.links.new(GI("Гребень_глубина_мм"), in_sock(n223, "Value_001"))

    n224 = add_node(tree, "ShaderNodeMath", "2.24",
                     "crest_raw = depth(T) * crest_indent",
                     4420, 600, operation='MULTIPLY')
    link(tree, n223, "Value", n224, "Value")
    link(tree, n221, "Value", n224, "Value_001")

    n225 = add_node(tree, "ShaderNodeMath", "2.25",
                     "term_crest = -crest_raw (подрезка = минус)",
                     4680, 600, operation='MULTIPLY')
    link(tree, n224, "Value", n225, "Value")
    in_sock(n225, "Value_001").default_value = -1.0

    frame6 = make_frame(
        tree, "6. ГРЕБЕНЬ БОЛЬШЕБЕРЦОВОЙ КОСТИ: смещение по стороне ноги + сглаженный излом",
        [n219a, n219b, n219c, n219d, n219e, n219f, n219g,
         n218, n218sq, n219, n220, n221, n222, n223, n224, n225])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 7: икроножная мышца (зад, -Y), сглаженная у шва и по высоте
    # ------------------------------------------------------------------
    n226 = add_node(tree, "ShaderNodeMath", "2.26",
                     "-dir.Y", 2080, 150, operation='MULTIPLY')
    link(tree, n217, "Y", n226, "Value")
    in_sock(n226, "Value_001").default_value = -1.0

    n227 = add_node(tree, "ShaderNodeMath", "2.27",
                     "w_back = max(-dir.Y, 0)", 2340, 150, operation='MAXIMUM')
    link(tree, n226, "Value", n227, "Value")
    in_sock(n227, "Value_001").default_value = 0.0

    n227sq = add_node(tree, "ShaderNodeMath", "2.27sq",
                       "w_back_смягчённый = w_back^2 (убирает излом на шве)",
                       2600, 150, operation='MULTIPLY')
    link(tree, n227, "Value", n227sq, "Value")
    link(tree, n227, "Value", n227sq, "Value_001")

    n228f = add_node(tree, "ShaderNodeMath", "2.28f",
                      "доля_икры_от_колена = мм / Длина (зажато 0..1)",
                      -260, -50, operation='DIVIDE', use_clamp=True)
    tree.links.new(GI("Высота_икры_мм_от_колена"), in_sock(n228f, "Value"))
    tree.links.new(GI("Длина_сегмента_мм"), in_sock(n228f, "Value_001"))

    n228 = add_node(tree, "ShaderNodeMath", "2.28",
                     "T_икра = 1 - доля_икры_от_колена", 0, -50, operation='SUBTRACT')
    in_sock(n228, "Value").default_value = 1.0
    link(tree, n228f, "Value", n228, "Value_001")

    n229 = add_node(tree, "ShaderNodeMath", "2.29",
                     "diff = T - T_икра", 1820, -50, operation='SUBTRACT')
    link(tree, n214, "Attribute_Float", n229, "Value")
    link(tree, n228, "Value", n229, "Value_001")

    n230 = add_node(tree, "ShaderNodeMath", "2.30",
                     "|diff|", 2080, -50, operation='ABSOLUTE')
    link(tree, n229, "Value", n230, "Value")

    n231 = add_node(tree, "ShaderNodeMath", "2.31",
                     "норм. = |diff| / Икра_ширина_доля", 2340, -50, operation='DIVIDE')
    link(tree, n230, "Value", n231, "Value")
    tree.links.new(GI("Икра_ширина_доля"), in_sock(n231, "Value_001"))

    n231b = add_node(tree, "ShaderNodeMath", "2.31b",
                      "min(норм., 1) — за пределами ширины falloff=0",
                      2600, -50, operation='MINIMUM')
    link(tree, n231, "Value", n231b, "Value")
    in_sock(n231b, "Value_001").default_value = 1.0

    n231c = add_node(tree, "ShaderNodeMath", "2.31c",
                      "* пи", 2860, -50, operation='MULTIPLY')
    link(tree, n231b, "Value", n231c, "Value")
    in_sock(n231c, "Value_001").default_value = math.pi

    n231d = add_node(tree, "ShaderNodeMath", "2.31d",
                      "cos(...)", 3120, -50, operation='COSINE')
    link(tree, n231c, "Value", n231d, "Value")

    n231e = add_node(tree, "ShaderNodeMath", "2.31e",
                      "+1", 3380, -50, operation='ADD')
    link(tree, n231d, "Value", n231e, "Value")
    in_sock(n231e, "Value_001").default_value = 1.0

    n232 = add_node(tree, "ShaderNodeMath", "2.32",
                     "falloff(T) = 0.5*(cos(норм.*пи)+1) — гладкий колокол "
                     "(без излома в пике и на границе)", 3640, -50, operation='MULTIPLY')
    link(tree, n231e, "Value", n232, "Value")
    in_sock(n232, "Value_001").default_value = 0.5

    n233 = add_node(tree, "ShaderNodeMath", "2.33",
                     "Икра_выступ_мм * w_back_смягчённый", 2600, 150, operation='MULTIPLY')
    tree.links.new(GI("Икра_выступ_мм"), in_sock(n233, "Value"))
    link(tree, n227sq, "Value", n233, "Value_001")

    n234 = add_node(tree, "ShaderNodeMath", "2.34",
                     "term_calf = (Икра_выступ*w_back_см) * falloff(T)",
                     3900, 100, operation='MULTIPLY')
    link(tree, n233, "Value", n234, "Value")
    link(tree, n232, "Value", n234, "Value_001")

    frame7 = make_frame(
        tree, "7. ИКРОНОЖНАЯ МЫШЦА: гладкий колокол по высоте + сглаженный излом на шве",
        [n226, n227, n227sq, n228f, n228, n229, n230, n231, n231b, n231c,
         n231d, n231e, n232, n233, n234])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 7b: лёгкая овальность у лодыжки
    # oval_term = (dir.x² - dir.y²) * Овальность_мм * falloff_у_лодыжки(T)
    # ------------------------------------------------------------------
    n217x2 = add_node(tree, "ShaderNodeMath", "2.17x2",
                       "dir.X^2", 2080, -300, operation='MULTIPLY')
    link(tree, n217, "X", n217x2, "Value")
    link(tree, n217, "X", n217x2, "Value_001")

    n217y2 = add_node(tree, "ShaderNodeMath", "2.17y2",
                       "dir.Y^2", 2080, -430, operation='MULTIPLY')
    link(tree, n217, "Y", n217y2, "Value")
    link(tree, n217, "Y", n217y2, "Value_001")

    n217d = add_node(tree, "ShaderNodeMath", "2.17d",
                      "oval_dir = dir.X^2 - dir.Y^2 (+1 бок, -1 перед/зад)",
                      2340, -370, operation='SUBTRACT')
    link(tree, n217x2, "Value", n217d, "Value")
    link(tree, n217y2, "Value", n217d, "Value_001")

    n217e = add_node(tree, "ShaderNodeMath", "2.17e",
                      "норм. = ring_T / Овальность_протяжённость_доля",
                      2340, -550, operation='DIVIDE')
    link(tree, n214, "Attribute_Float", n217e, "Value")
    tree.links.new(GI("Овальность_протяжённость_доля"), in_sock(n217e, "Value_001"))

    n217f = add_node(tree, "ShaderNodeMath", "2.17f",
                      "min(норм., 1)", 2600, -550, operation='MINIMUM')
    link(tree, n217e, "Value", n217f, "Value")
    in_sock(n217f, "Value_001").default_value = 1.0

    n217g = add_node(tree, "ShaderNodeMath", "2.17g",
                      "* пи", 2860, -550, operation='MULTIPLY')
    link(tree, n217f, "Value", n217g, "Value")
    in_sock(n217g, "Value_001").default_value = math.pi

    n217h = add_node(tree, "ShaderNodeMath", "2.17h",
                      "cos(...)", 3120, -550, operation='COSINE')
    link(tree, n217g, "Value", n217h, "Value")

    n217i = add_node(tree, "ShaderNodeMath", "2.17i",
                      "+1", 3380, -550, operation='ADD')
    link(tree, n217h, "Value", n217i, "Value")
    in_sock(n217i, "Value_001").default_value = 1.0

    n217j = add_node(tree, "ShaderNodeMath", "2.17j",
                      "falloff_у_лодыжки(T) = 0.5*(cos(норм.*пи)+1): "
                      "1 у лодыжки, гладко к 0 выше", 3640, -550, operation='MULTIPLY')
    link(tree, n217i, "Value", n217j, "Value")
    in_sock(n217j, "Value_001").default_value = 0.5

    n217k = add_node(tree, "ShaderNodeMath", "2.17k",
                      "oval_dir * Овальность_у_лодыжки_мм", 3900, -400, operation='MULTIPLY')
    link(tree, n217d, "Value", n217k, "Value")
    tree.links.new(GI("Овальность_у_лодыжки_мм"), in_sock(n217k, "Value_001"))

    n217l = add_node(tree, "ShaderNodeMath", "2.17l",
                      "term_oval = (oval_dir*Овальность_мм) * falloff_у_лодыжки(T)",
                      4160, -450, operation='MULTIPLY')
    link(tree, n217k, "Value", n217l, "Value")
    link(tree, n217j, "Value", n217l, "Value_001")

    frame7b = make_frame(
        tree, "7b. ОВАЛЬНОСТЬ У ЛОДЫЖКИ (гладкий колокол от T=0 вверх)",
        [n217x2, n217y2, n217d, n217e, n217f, n217g, n217h, n217i, n217j, n217k, n217l])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 8: итоговый радиус и позиция
    # ------------------------------------------------------------------
    n235 = add_node(tree, "ShaderNodeMath", "2.35",
                     "R_mid = R_base + term_crest", 4680, 400, operation='ADD')
    link(tree, n215, "Result", n235, "Value")
    link(tree, n225, "Value", n235, "Value_001")

    n235o = add_node(tree, "ShaderNodeMath", "2.35o",
                      "R_mid2 = R_mid + term_oval", 4900, 350, operation='ADD')
    link(tree, n235, "Value", n235o, "Value")
    link(tree, n217l, "Value", n235o, "Value_001")

    n236 = add_node(tree, "ShaderNodeMath", "2.36",
                     "R_total = R_mid2 + term_calf", 5120, 300, operation='ADD')
    link(tree, n235o, "Value", n236, "Value")
    link(tree, n234, "Value", n236, "Value_001")

    n237 = named_attr(tree, "2.37", "Читаем 'ring_center'",
                       1560, 30, "ring_center", 'FLOAT_VECTOR')

    n238 = add_node(tree, "ShaderNodeVectorMath", "2.38",
                     "смещение = dir * R_total", 4160, 300, operation='SCALE')
    link(tree, n216, "Attribute_Vector", n238, "Vector")
    link(tree, n236, "Value", n238, "Scale")

    n239 = add_node(tree, "ShaderNodeVectorMath", "2.39",
                     "финальная позиция = центр + смещение", 4420, 150, operation='ADD')
    link(tree, n237, "Attribute_Vector", n239, "Vector")
    link(tree, n238, "Vector", n239, "Vector_001")

    n240 = add_node(tree, "GeometryNodeSetPosition", "2.40",
                     "Записать позицию -> 'Профиль_точки'", 4680, 150)
    link(tree, n209, "Geometry", n240, "Geometry")
    link(tree, n239, "Vector", n240, "Position")

    frame8 = make_frame(
        tree, "8. ИТОГОВЫЙ РАДИУС R_total(dir,T) И ПОЗИЦИЯ ТОЧКИ",
        [n235, n236, n237, n238, n239, n240])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 9: сборка колец в кривые + временная визуализация
    # ------------------------------------------------------------------
    n241 = named_attr(tree, "2.41", "Читаем 'ring_index'",
                       4680, -50, "ring_index", 'INT')

    # ВАЖНО: Points to Curves принимает геометрию именно типа "облако
    # точек" (Point Cloud), а не вершины меша — обычный меш он молча
    # игнорирует (0 результирующих точек). Поэтому явно конвертируем.
    n241b = add_node(tree, "GeometryNodeMeshToPoints", "2.41b",
                      "Меш -> облако точек (для Points to Curves)", 4780, 150)
    link(tree, n240, "Geometry", n241b, "Mesh")

    n242 = add_node(tree, "GeometryNodePointsToCurves", "2.42",
                     "Points to Curves (группировка по ring_index)", 4940, 0)
    link(tree, n241b, "Points", n242, "Points")
    link(tree, n241, "Attribute_Int", n242, "Curve Group ID")

    n243 = add_node(tree, "GeometryNodeSetSplineCyclic", "2.43",
                     "Замкнуть каждое кольцо (Cyclic=True)", 5200, 0)
    link(tree, n242, "Curves", n243, "Geometry")
    in_sock(n243, "Cyclic").default_value = True

    n244 = add_node(tree, "GeometryNodeCurvePrimitiveCircle", "2.44",
                     "VIS: профиль-кружок d=2.4мм для трубок", 5200, -200)
    in_sock(n244, "Radius").default_value = 1.2

    n245 = add_node(tree, "GeometryNodeCurveToMesh", "2.45",
                     "VIS: кольца -> тонкие трубки", 5460, -100)
    link(tree, n243, "Geometry", n245, "Curve")
    link(tree, n244, "Curve", n245, "Profile Curve")

    frame9 = make_frame(
        tree, "9. КОЛЬЦА В КРИВЫЕ (для Группы 3) + ВРЕМЕННАЯ ВИЗУАЛИЗАЦИЯ",
        [n241, n241b, n242, n243, n244, n245])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 10: проверки (V2.1 - V2.3)
    # ------------------------------------------------------------------
    v21a = add_node(tree, "GeometryNodeAttributeDomainSize", "V2.1a",
                     "N = число точек исходной оси", 260, -900, component='CURVE')
    link(tree, n205, "Geometry", v21a, "Geometry")

    v21b = add_node(tree, "ShaderNodeMath", "V2.1b",
                     "Ожидаемое кол-во точек = N * M", 560, -900, operation='MULTIPLY')
    link(tree, v21a, "Point Count", v21b, "Value")
    tree.links.new(GI("Разрешение_кольца"), in_sock(v21b, "Value_001"))

    v21c = add_node(tree, "GeometryNodeAttributeDomainSize", "V2.1c",
                     "Фактическое кол-во точек профиля", 4940, -300, component='MESH')
    link(tree, n240, "Geometry", v21c, "Geometry")

    v21 = add_node(tree, "FunctionNodeCompare", "V2.1",
                    "Факт. точки == N * M ?", 5200, -300,
                    data_type='FLOAT', operation='EQUAL')
    link(tree, v21c, "Point Count", v21, "A")
    link(tree, v21b, "Value", v21, "B")

    v22a = add_node(tree, "GeometryNodeAttributeStatistic", "V2.2a",
                     "Статистика R_total по всем точкам", 4940, -500, domain='POINT')
    link(tree, n209, "Geometry", v22a, "Geometry")
    link(tree, n236, "Value", v22a, "Attribute")

    v22 = add_node(tree, "FunctionNodeCompare", "V2.2",
                    "min(R_total) > 0 ? (сечение не схлопнулось)",
                    5200, -500, data_type='FLOAT', operation='GREATER_THAN')
    link(tree, v22a, "Min", v22, "A")
    in_sock(v22, "B").default_value = 0.0

    v23 = add_node(tree, "FunctionNodeBooleanMath", "V2.3",
                    "ИТОГ: все проверки Группы 2", 5460, -400, operation='AND')
    link(tree, v21, "Result", v23, "Boolean")
    link(tree, v22, "Result", v23, "Boolean_001")

    frame10 = make_frame(
        tree, "10. ПРОВЕРКИ (V2.1 - V2.3)",
        [v21a, v21b, v21c, v21, v22a, v22, v23])

    # ------------------------------------------------------------------
    # СЕКЦИЯ 11: текстовый отчёт
    # ------------------------------------------------------------------
    n290 = add_node(tree, "FunctionNodeValueToString", "2.90",
                     "R min -> строка", 5460, -650)
    link(tree, v22a, "Min", n290, "Value")
    in_sock(n290, "Decimals").default_value = 1

    n291 = add_node(tree, "FunctionNodeValueToString", "2.91",
                     "R max -> строка", 5460, -800)
    link(tree, v22a, "Max", n291, "Value")
    in_sock(n291, "Decimals").default_value = 1

    n292 = add_node(tree, "FunctionNodeValueToString", "2.92",
                     "Точек всего -> строка", 5460, -950)
    link(tree, v21c, "Point Count", n292, "Value")
    in_sock(n292, "Decimals").default_value = 0

    n293 = add_node(tree, "GeometryNodeStringJoin", "2.93",
                     "Сборка строки отчёта", 5720, -800)
    in_sock(n293, "Delimiter").default_value = " | "
    tree.links.new(n290.outputs["String"], n293.inputs["Strings"])
    tree.links.new(n291.outputs["String"], n293.inputs["Strings"])
    tree.links.new(n292.outputs["String"], n293.inputs["Strings"])

    frame11 = make_frame(tree, "11. ТЕКСТОВЫЙ ОТЧЁТ", [n290, n291, n292, n293])

    # ------------------------------------------------------------------
    # Финальные соединения в Group Output
    # ------------------------------------------------------------------
    tree.links.new(n245.outputs["Mesh"], GO("VIS_Кольца"))
    tree.links.new(n240.outputs["Geometry"], GO("Профиль_точки"))
    tree.links.new(n243.outputs["Geometry"], GO("Кольца_кривые"))
    tree.links.new(GI("Разрешение_кольца"), GO("Точек_в_кольце"))
    tree.links.new(v21a.outputs["Point Count"], GO("Колец_всего"))
    tree.links.new(v23.outputs["Boolean"], GO("Провер_ВСЕ_OK"))
    tree.links.new(n293.outputs["String"], GO("Провер_Отчёт"))

    return tree


def build_demo_object(tree, axis_tree):
    """Демо-объект: NK.1_Ось -> NK.2_Профиль в одном модификаторе через
    вложенный узел Group, чтобы видеть результат целиком (первая сборка
    будущего NK.Master)."""
    name = "NK_Group2_Demo"
    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    mesh = bpy.data.meshes.new(name + "_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    mod = obj.modifiers.new("NK_Master_preview", "NODES")
    master = bpy.data.node_groups.new("NK.Master_preview", "GeometryNodeTree")
    if "Geometry" not in [s.name for s in master.interface.items_tree if s.item_type == 'SOCKET' and s.in_out == 'OUTPUT']:
        master.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    mod.node_group = master

    gout = master.nodes.new("NodeGroupOutput")
    gout.location = (600, 0)

    g1 = master.nodes.new("GeometryNodeGroup")
    g1.node_tree = axis_tree
    g1.location = (-200, 0)
    g1.name = "M.1 Группа 1 (Ось)"
    g1.label = "M.1 Группа 1 (Ось)"

    g2 = master.nodes.new("GeometryNodeGroup")
    g2.node_tree = tree
    g2.location = (200, 0)
    g2.name = "M.2 Группа 2 (Профиль)"
    g2.label = "M.2 Группа 2 (Профиль)"

    master.links.new(g1.outputs["Ось_кривая"], g2.inputs["Ось_кривая"])
    # Длина и сторона ноги должны совпадать между Группой 1 и Группой 2 -
    # тянем их напрямую из выходов Группы 1, чтобы не дублировать ввод и
    # не допустить рассинхронизации (баг "гребень не туда" при разных
    # значениях Сторона_ноги в двух группах).
    master.links.new(g1.outputs["Факт_длина_дуги_мм"], g2.inputs["Длина_сегмента_мм"])
    master.links.new(g1.outputs["Сторона_ноги"], g2.inputs["Сторона_ноги"])
    master.links.new(g2.outputs["VIS_Кольца"], gout.inputs["Geometry"])

    return obj, mod, master, g1, g2


if __name__ == "__main__":
    from build_group1_axis import build as build_axis
    axis_tree = build_axis()
    tree = build()
    obj, mod, master, g1, g2 = build_demo_object(tree, axis_tree)
    print("OK: группа '%s' собрана, узлов: %d" % (GROUP_NAME, len(tree.nodes)))
