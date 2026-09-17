# -*- coding: utf-8 -*-
"""
ГРУППА 4 — «NK.4_Закладные» (Inserts: clamps + magnets)
==========================================================
Добавляет на переднюю/заднюю половины оболочки (из Группы 3) то, чем
накладка реально крепится:

  - ХОМУТЫ на трубку протеза: короткий отрезок трубы (охватывает
    диаметр трубки + зазор), разрезанный по той же плоскости
    перед/зад, что и Группа 3. На концах каждой половины хомута -
    бобышка с отверстием: в передней половине - гнездо под
    вплавляемую гайку М3 (глухое), в задней - сквозное отверстие под
    винт М3. Винт проходит сквозь заднюю половину в гайку в передней
    и стягивает обе половины хомута (а значит - и обе половины
    накладки) на трубке.

  - МАГНИТЫ у швов перед/зад: до 4 гнёзд на половину (2 шва x 2
    высоты), с бобышкой-утолщением (тонкая стенка сама по себе
    недостаточно толстая под магнит) и высверленным гнездом нужного
    диаметра/глубины.

Оба механизма используют один и тот же приём: `Mesh Boolean` UNION
(добавить бобышку-утолщение) + `Mesh Boolean` DIFFERENCE (высверлить
отверстие/гнездо) - собран как переиспользуемая группа
`NK.4c_Бобышка_с_отверстием`.

УПРОЩЕНИЕ (осознанное, см. docs/04_group4_inserts.md): хомут
строится с осью строго по глобальному Z, а не по направлению
A->B (которое может быть немного наклонено параметрами Группы 1).
Штифт-трубка протеза жёсткая и прямая, поэтому её положение по
высоте берётся честно (линейная интерполяция между Точка_A и
Точка_B), но сам цилиндр хомута не поворачивается вслед за наклоном
- при типичных углах (до ±10°) разница на высоте хомута 14мм не
превышает ~1.2мм, что для первой версии несущественно.

Запуск:
    blender --background --python scripts/build_group4_inserts.py
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
from build_group3_shell import SAMPLER_NAME, build_sampler, _grp

BOSSHOLE_NAME = "NK.4c_Бобышка_с_отверстием"
CLAMP_NAME = "NK.4a_Хомут"
INSERTS_NAME = "NK.4_Закладные"


def named_attr(tree, num, label, x, y, attr_name, data_type):
    n = add_node(tree, "GeometryNodeInputNamedAttribute", num, label, x, y,
                 data_type=data_type)
    in_sock(n, "Name").default_value = attr_name
    return n


# ----------------------------------------------------------------------
# 1) NK.4c_Бобышка_с_отверстием
# ----------------------------------------------------------------------
def build_boss_hole():
    """Бобышка (для Boolean UNION) + высверленное в ней отверстие/гнездо
    (для Boolean DIFFERENCE), в точке 'Позиция', ось цилиндров - вдоль
    'Направление' (не обязательно единичный вектор). Бобышка стоит
    СИММЕТРИЧНО вокруг Позиции; отверстие - глухое, от Позиции В СТОРОНУ
    Направления на глубину Глубина_отверстия_мм (то есть "растёт" только
    в одну сторону - именно так гайка/винт входят с одной стороны шва).
    """
    tree = new_group(BOSSHOLE_NAME)
    add_input(tree, "Позиция", "NodeSocketVector")
    add_input(tree, "Направление", "NodeSocketVector", default=(0.0, 1.0, 0.0))
    add_input(tree, "Радиус_бобышки_мм", "NodeSocketFloat", default=6.0, min_value=1.0, max_value=20.0)
    add_input(tree, "Длина_бобышки_мм", "NodeSocketFloat", default=10.0, min_value=1.0, max_value=40.0)
    add_input(tree, "Радиус_отверстия_мм", "NodeSocketFloat", default=2.0, min_value=0.5, max_value=15.0)
    add_input(tree, "Глубина_отверстия_мм", "NodeSocketFloat", default=5.0, min_value=0.5, max_value=30.0)
    add_output(tree, "Бобышка", "NodeSocketGeometry", "Для Boolean UNION с оболочкой.")
    add_output(tree, "Отверстие", "NodeSocketGeometry", "Для Boolean DIFFERENCE из оболочки.")

    gin = tree.nodes.new("NodeGroupInput")
    gin.name = "4c.01 Вход"; gin.label = "4c.01 Входные параметры"; gin.location = (-400, 0)
    gout = tree.nodes.new("NodeGroupOutput")
    gout.name = "4c.99 Выход"; gout.label = "4c.99 Выход"; gout.location = (1400, 0)

    def GI(name):
        return gin.outputs[name]

    n02 = add_node(tree, "ShaderNodeVectorMath", "4c.02", "единичное направление",
                    -100, -200, operation='NORMALIZE')
    tree.links.new(GI("Направление"), in_sock(n02, "Vector"))

    n03 = add_node(tree, "GeometryNodeMeshCylinder", "4c.03", "Бобышка (цилиндр)",
                    200, 250, fill_type='NGON')
    tree.links.new(GI("Радиус_бобышки_мм"), in_sock(n03, "Radius"))
    tree.links.new(GI("Длина_бобышки_мм"), in_sock(n03, "Depth"))

    n05rot = add_node(tree, "FunctionNodeAlignEulerToVector", "4c.05rot",
                       "Euler: локальный Z -> Направление", 200, 480)
    n05rot.axis = 'Z'
    tree.links.new(n02.outputs["Vector"], in_sock(n05rot, "Vector"))
    # ВАЖНО: выход этого узла - уже готовый Euler-вектор (тип VECTOR,
    # не Rotation!), его можно подключать прямо в Transform.Rotation
    # без промежуточной конвертации.

    n05 = add_node(tree, "GeometryNodeTransform", "4c.05",
                    "Бобышка на место (поворот+сдвиг)", 500, 250)
    link(tree, n03, "Mesh", n05, "Geometry")
    link(tree, n05rot, "Rotation", n05, "Rotation")
    tree.links.new(GI("Позиция"), in_sock(n05, "Translation"))

    frameA = make_frame(tree, "A. БОБЫШКА (симметрично вокруг Позиции)",
                         [n03, n05rot, n05])

    n06 = add_node(tree, "GeometryNodeMeshCylinder", "4c.06", "Отверстие (цилиндр)",
                    200, -50, fill_type='NGON')
    tree.links.new(GI("Радиус_отверстия_мм"), in_sock(n06, "Radius"))
    n06d = add_node(tree, "ShaderNodeMath", "4c.06d", "длина цилиндра отверстия = глубина*2 "
                     "(с запасом на чистое вычитание)", -100, -350, operation='MULTIPLY')
    tree.links.new(GI("Глубина_отверстия_мм"), in_sock(n06d, "Value"))
    in_sock(n06d, "Value_001").default_value = 2.0
    link(tree, n06d, "Value", n06, "Depth")

    n07 = add_node(tree, "ShaderNodeVectorMath", "4c.07",
                    "сдвиг центра = направление * глубина/2", 200, -200, operation='SCALE')
    link(tree, n02, "Vector", n07, "Vector")
    n07s = add_node(tree, "ShaderNodeMath", "4c.07s", "глубина/2", -100, -480, operation='MULTIPLY')
    tree.links.new(GI("Глубина_отверстия_мм"), in_sock(n07s, "Value"))
    in_sock(n07s, "Value_001").default_value = 0.5
    link(tree, n07s, "Value", n07, "Scale")

    n08 = add_node(tree, "ShaderNodeVectorMath", "4c.08",
                    "центр отверстия = Позиция + сдвиг", 500, -150, operation='ADD')
    tree.links.new(GI("Позиция"), in_sock(n08, "Vector"))
    link(tree, n07, "Vector", n08, "Vector_001")

    n09 = add_node(tree, "GeometryNodeTransform", "4c.09",
                    "Отверстие на место (поворот+сдвиг)", 800, -100)
    link(tree, n06, "Mesh", n09, "Geometry")
    link(tree, n05rot, "Rotation", n09, "Rotation")
    link(tree, n08, "Vector", n09, "Translation")

    frameB = make_frame(tree, "B. ОТВЕРСТИЕ (от Позиции, вглубь по Направлению)",
                         [n06, n06d, n07, n07s, n08, n09])

    tree.links.new(n05.outputs["Geometry"], gout.inputs["Бобышка"])
    tree.links.new(n09.outputs["Geometry"], gout.inputs["Отверстие"])
    return tree


# ----------------------------------------------------------------------
# 2) NK.4a_Хомут
# ----------------------------------------------------------------------
def build_clamp(boss_tree):
    tree = new_group(CLAMP_NAME)
    add_input(tree, "Перед", "NodeSocketGeometry")
    add_input(tree, "Зад", "NodeSocketGeometry")
    add_input(tree, "Точка_A", "NodeSocketVector", description="Выход Группы 1 (дистальная точка).")
    add_input(tree, "Точка_B", "NodeSocketVector", description="Выход Группы 1 (проксимальная точка).")
    add_input(tree, "Высота_доля_от_колена", "NodeSocketFloat", default=0.5,
              min_value=0.0, max_value=1.0)
    add_input(tree, "Трубка_диаметр_мм", "NodeSocketFloat", default=25.0,
              min_value=16.0, max_value=35.0)
    add_input(tree, "Хомут_толщина_мм", "NodeSocketFloat", default=3.5,
              min_value=2.5, max_value=6.0)
    add_input(tree, "Хомут_высота_мм", "NodeSocketFloat", default=14.0,
              min_value=8.0, max_value=25.0)
    add_input(tree, "Гайка_диаметр_мм", "NodeSocketFloat", default=4.0,
              min_value=3.6, max_value=4.6)
    add_input(tree, "Гайка_глубина_мм", "NodeSocketFloat", default=5.0,
              min_value=3.0, max_value=8.0)
    add_input(tree, "Винт_зазор_диаметр_мм", "NodeSocketFloat", default=3.4,
              min_value=3.2, max_value=3.8)
    add_output(tree, "Перед", "NodeSocketGeometry")
    add_output(tree, "Зад", "NodeSocketGeometry")

    gin = tree.nodes.new("NodeGroupInput")
    gin.name = "4a.01 Вход"; gin.label = "4a.01 Входные параметры"; gin.location = (-500, 300)
    gout = tree.nodes.new("NodeGroupOutput")
    gout.name = "4a.99 Выход"; gout.label = "4a.99 Выход"; gout.location = (3200, 300)

    def GI(name):
        return gin.outputs[name]

    # -- центр хомута на прямой A-B --
    n02 = add_node(tree, "ShaderNodeMath", "4a.02", "t = 1 - Высота_доля_от_колена",
                    -200, 550, operation='SUBTRACT')
    in_sock(n02, "Value").default_value = 1.0
    tree.links.new(GI("Высота_доля_от_колена"), in_sock(n02, "Value_001"))

    n03 = add_node(tree, "ShaderNodeMix", "4a.03", "центр = mix(A, B, t)",
                    100, 550, data_type='VECTOR')
    tree.links.new(GI("Точка_A"), in_sock(n03, "A_Vector"))
    tree.links.new(GI("Точка_B"), in_sock(n03, "B_Vector"))
    link(tree, n02, "Value", n03, "Factor_Float")

    frame0 = make_frame(tree, "0. ЦЕНТР ХОМУТА (линейная интерполяция A->B, см. docs про упрощение)",
                         [n02, n03])

    # -- радиусы --
    n04 = add_node(tree, "ShaderNodeMath", "4a.04", "R_трубки = Трубка_диаметр/2",
                    -200, 350, operation='DIVIDE')
    tree.links.new(GI("Трубка_диаметр_мм"), in_sock(n04, "Value"))
    in_sock(n04, "Value_001").default_value = 2.0

    n05 = add_node(tree, "ShaderNodeMath", "4a.05", "R_внеш = R_трубки + Хомут_толщина",
                    100, 350, operation='ADD')
    link(tree, n04, "Value", n05, "Value")
    tree.links.new(GI("Хомут_толщина_мм"), in_sock(n05, "Value_001"))

    n06 = add_node(tree, "ShaderNodeMath", "4a.06", "R_средний = R_трубки + Хомут_толщина/2",
                    100, 200, operation='ADD')
    link(tree, n04, "Value", n06, "Value")
    n06h = add_node(tree, "ShaderNodeMath", "4a.06h", "Хомут_толщина/2", -200, 150, operation='MULTIPLY')
    tree.links.new(GI("Хомут_толщина_мм"), in_sock(n06h, "Value"))
    in_sock(n06h, "Value_001").default_value = 0.5
    link(tree, n06h, "Value", n06, "Value_001")

    frame1 = make_frame(tree, "1. РАДИУСЫ (трубки, внешний, средний по стенке хомута)",
                         [n04, n05, n06, n06h])

    # -- труба-хомут (внешний минус внутренний цилиндр) --
    n07 = add_node(tree, "GeometryNodeMeshCylinder", "4a.07", "внешний цилиндр",
                    400, 700, fill_type='NGON')
    link(tree, n05, "Value", n07, "Radius")
    tree.links.new(GI("Хомут_высота_мм"), in_sock(n07, "Depth"))

    n08 = add_node(tree, "GeometryNodeMeshCylinder", "4a.08", "внутренний цилиндр "
                    "(чуть выше внешнего - чистое вычитание)", 400, 550, fill_type='NGON')
    link(tree, n04, "Value", n08, "Radius")
    n08h = add_node(tree, "ShaderNodeMath", "4a.08h", "Хомут_высота + 2мм", 100, 500, operation='ADD')
    tree.links.new(GI("Хомут_высота_мм"), in_sock(n08h, "Value"))
    in_sock(n08h, "Value_001").default_value = 2.0
    link(tree, n08h, "Value", n08, "Depth")

    n09 = add_node(tree, "GeometryNodeMeshBoolean", "4a.09",
                    "труба = внешний - внутренний", 700, 620, operation='DIFFERENCE')
    tree.links.new(n07.outputs["Mesh"], in_sock(n09, "Mesh 1"))
    tree.links.new(n08.outputs["Mesh"], in_sock(n09, "Mesh 2"))

    n10 = add_node(tree, "GeometryNodeTransform", "4a.10",
                    "труба на высоту хомута (без поворота - см. docs)", 1000, 620)
    tree.links.new(n09.outputs["Mesh"], in_sock(n10, "Geometry"))
    link(tree, n03, "Result_Vector", n10, "Translation")

    frame2 = make_frame(tree, "2. ТРУБА-ХОМУТ (внешний минус внутренний цилиндр)",
                         [n07, n08, n08h, n09, n10])

    # -- разрез перед/зад большими "полу-пространствами" --
    n11 = add_node(tree, "GeometryNodeMeshCube", "4a.11", "куб-полупространство (огромный)",
                    1000, 300)
    in_sock(n11, "Size").default_value = (4000.0, 4000.0, 4000.0)

    n12f = add_node(tree, "GeometryNodeTransform", "4a.12f",
                     "сдвиг -> занимает Y>0 (перёд)", 1300, 350)
    tree.links.new(n11.outputs["Mesh"], in_sock(n12f, "Geometry"))
    in_sock(n12f, "Translation").default_value = (0.0, 2000.0, 0.0)

    n12b = add_node(tree, "GeometryNodeTransform", "4a.12b",
                     "сдвиг -> занимает Y<0 (зад)", 1300, 150)
    tree.links.new(n11.outputs["Mesh"], in_sock(n12b, "Geometry"))
    in_sock(n12b, "Translation").default_value = (0.0, -2000.0, 0.0)

    # ВАЖНО про Mesh Boolean (грабли, обнаруженные тестом перед сборкой
    # этой группы): сокет "Mesh 1" учитывается ТОЛЬКО для DIFFERENCE.
    # Для UNION и INTERSECT все операнды нужно подключать в "Mesh 2"
    # (он мульти-input, принимает несколько связей) - иначе "Mesh 1"
    # молча игнорируется и в результате остаётся только то, что было
    # в Mesh 2. Проверено отдельным тестовым скриптом до сборки этой
    # группы: команда `boolean.operation='UNION'` + один линк в Mesh1
    # и один в Mesh2 отбрасывает Mesh1 целиком.
    n13f = add_node(tree, "GeometryNodeMeshBoolean", "4a.13f",
                     "передняя половина трубы", 1600, 400, operation='INTERSECT')
    tree.links.new(n10.outputs["Geometry"], in_sock(n13f, "Mesh 2"))
    tree.links.new(n12f.outputs["Geometry"], in_sock(n13f, "Mesh 2"))

    n13b = add_node(tree, "GeometryNodeMeshBoolean", "4a.13b",
                     "задняя половина трубы", 1600, 150, operation='INTERSECT')
    tree.links.new(n10.outputs["Geometry"], in_sock(n13b, "Mesh 2"))
    tree.links.new(n12b.outputs["Geometry"], in_sock(n13b, "Mesh 2"))

    frame3 = make_frame(tree, "3. РАЗРЕЗ ТРУБЫ ПО Y=0 (та же плоскость, что и в Группе 3)",
                         [n11, n12f, n12b, n13f, n13b])

    # -- позиции концов полу-трубы (X = +-R_средний, Y=0, Z=центр) --
    n14 = add_node(tree, "ShaderNodeCombineXYZ", "4a.14", "смещение конца 1 = (+R_средний,0,0)",
                    400, -50)
    link(tree, n06, "Value", n14, "X")

    n15 = add_node(tree, "ShaderNodeCombineXYZ", "4a.15", "смещение конца 2 = (-R_средний,0,0)",
                    400, -200)
    n15n = add_node(tree, "ShaderNodeMath", "4a.15n", "-R_средний", 100, -250, operation='MULTIPLY')
    link(tree, n06, "Value", n15n, "Value")
    in_sock(n15n, "Value_001").default_value = -1.0
    link(tree, n15n, "Value", n15, "X")

    n16 = add_node(tree, "ShaderNodeVectorMath", "4a.16", "конец1 = центр + смещение1",
                    700, -50, operation='ADD')
    link(tree, n03, "Result_Vector", n16, "Vector")
    link(tree, n14, "Vector", n16, "Vector_001")

    n17 = add_node(tree, "ShaderNodeVectorMath", "4a.17", "конец2 = центр + смещение2",
                    700, -200, operation='ADD')
    link(tree, n03, "Result_Vector", n17, "Vector")
    link(tree, n15, "Vector", n17, "Vector_001")

    frame4 = make_frame(tree, "4. ДВА КОНЦА ПОЛУ-ТРУБЫ (там будут гайка/винт)",
                         [n14, n15, n15n, n16, n17])

    # -- бобышки+отверстия: перед (гайка), зад (зазор под винт) --
    boss_r = add_node(tree, "ShaderNodeMath", "4a.18", "радиус бобышки = Гайка_диаметр/2 + 2мм",
                       400, -450, operation='MULTIPLY')
    tree.links.new(GI("Гайка_диаметр_мм"), in_sock(boss_r, "Value"))
    in_sock(boss_r, "Value_001").default_value = 0.5
    boss_r2 = add_node(tree, "ShaderNodeMath", "4a.18b", "+2мм", 650, -450, operation='ADD')
    link(tree, boss_r, "Value", boss_r2, "Value")
    in_sock(boss_r2, "Value_001").default_value = 2.0

    nut_r = add_node(tree, "ShaderNodeMath", "4a.18c", "R_гайки = Гайка_диаметр/2",
                      400, -600, operation='DIVIDE')
    tree.links.new(GI("Гайка_диаметр_мм"), in_sock(nut_r, "Value"))
    in_sock(nut_r, "Value_001").default_value = 2.0

    clr_r = add_node(tree, "ShaderNodeMath", "4a.18d", "R_зазора = Винт_зазор_диаметр/2",
                      400, -750, operation='DIVIDE')
    tree.links.new(GI("Винт_зазор_диаметр_мм"), in_sock(clr_r, "Value"))
    in_sock(clr_r, "Value_001").default_value = 2.0

    # передняя бобышка/гайка в конце 1
    g1 = _grp(tree, boss_tree, "4a.19", "бобышка+гайка (перед, конец1)", 1000, -50)
    tree.links.new(n16.outputs["Vector"], g1.inputs["Позиция"])
    g1.inputs["Направление"].default_value = (0.0, 1.0, 0.0)
    tree.links.new(boss_r2.outputs["Value"], g1.inputs["Радиус_бобышки_мм"])
    g1.inputs["Длина_бобышки_мм"].default_value = 12.0
    tree.links.new(nut_r.outputs["Value"], g1.inputs["Радиус_отверстия_мм"])
    tree.links.new(GI("Гайка_глубина_мм"), g1.inputs["Глубина_отверстия_мм"])

    # передняя бобышка/гайка в конце 2
    g2 = _grp(tree, boss_tree, "4a.20", "бобышка+гайка (перед, конец2)", 1000, -250)
    tree.links.new(n17.outputs["Vector"], g2.inputs["Позиция"])
    g2.inputs["Направление"].default_value = (0.0, 1.0, 0.0)
    tree.links.new(boss_r2.outputs["Value"], g2.inputs["Радиус_бобышки_мм"])
    g2.inputs["Длина_бобышки_мм"].default_value = 12.0
    tree.links.new(nut_r.outputs["Value"], g2.inputs["Радиус_отверстия_мм"])
    tree.links.new(GI("Гайка_глубина_мм"), g2.inputs["Глубина_отверстия_мм"])

    # задняя бобышка/зазор в конце 1
    g3 = _grp(tree, boss_tree, "4a.21", "бобышка+зазор (зад, конец1)", 1000, -450)
    tree.links.new(n16.outputs["Vector"], g3.inputs["Позиция"])
    g3.inputs["Направление"].default_value = (0.0, -1.0, 0.0)
    tree.links.new(boss_r2.outputs["Value"], g3.inputs["Радиус_бобышки_мм"])
    g3.inputs["Длина_бобышки_мм"].default_value = 12.0
    tree.links.new(clr_r.outputs["Value"], g3.inputs["Радиус_отверстия_мм"])
    g3.inputs["Глубина_отверстия_мм"].default_value = 8.0

    # задняя бобышка/зазор в конце 2
    g4 = _grp(tree, boss_tree, "4a.22", "бобышка+зазор (зад, конец2)", 1000, -650)
    tree.links.new(n17.outputs["Vector"], g4.inputs["Позиция"])
    g4.inputs["Направление"].default_value = (0.0, -1.0, 0.0)
    tree.links.new(boss_r2.outputs["Value"], g4.inputs["Радиус_бобышки_мм"])
    g4.inputs["Длина_бобышки_мм"].default_value = 12.0
    tree.links.new(clr_r.outputs["Value"], g4.inputs["Радиус_отверстия_мм"])
    g4.inputs["Глубина_отверстия_мм"].default_value = 8.0

    frame5 = make_frame(tree, "5. БОБЫШКИ+ОТВЕРСТИЯ: перед=гайка М3, зад=зазор под винт М3",
                         [boss_r, boss_r2, g1, g2, g3, g4])

    # -- сборка: перед --
    j1 = add_node(tree, "GeometryNodeJoinGeometry", "4a.23", "бобышки перед", 1300, -50)
    tree.links.new(g1.outputs["Бобышка"], j1.inputs["Geometry"])
    tree.links.new(g2.outputs["Бобышка"], j1.inputs["Geometry"])

    u1 = add_node(tree, "GeometryNodeMeshBoolean", "4a.24",
                   "перед. половина трубы + бобышки", 1600, -50, operation='UNION')
    tree.links.new(n13f.outputs["Mesh"], in_sock(u1, "Mesh 2"))  # UNION: оба в Mesh 2, см. врезку выше
    tree.links.new(j1.outputs["Geometry"], in_sock(u1, "Mesh 2"))

    h1 = add_node(tree, "GeometryNodeJoinGeometry", "4a.25", "отверстия-гайки перед", 1300, -180)
    tree.links.new(g1.outputs["Отверстие"], h1.inputs["Geometry"])
    tree.links.new(g2.outputs["Отверстие"], h1.inputs["Geometry"])

    d1 = add_node(tree, "GeometryNodeMeshBoolean", "4a.26",
                   "минус отверстия гаек -> клипса перед", 1900, -50, operation='DIFFERENCE')
    tree.links.new(u1.outputs["Mesh"], in_sock(d1, "Mesh 1"))
    tree.links.new(h1.outputs["Geometry"], in_sock(d1, "Mesh 2"))

    front_final = add_node(tree, "GeometryNodeMeshBoolean", "4a.27",
                            "Перед(вход) + клипса хомута -> Перед(выход)", 2300, 300,
                            operation='UNION')
    tree.links.new(GI("Перед"), in_sock(front_final, "Mesh 2"))  # UNION: оба в Mesh 2
    tree.links.new(d1.outputs["Mesh"], in_sock(front_final, "Mesh 2"))

    frame6 = make_frame(tree, "6. СБОРКА: ПЕРЕДНЯЯ КЛИПСА ХОМУТА -> UNION С Перед",
                         [j1, u1, h1, d1, front_final])

    # -- сборка: зад --
    j2 = add_node(tree, "GeometryNodeJoinGeometry", "4a.28", "бобышки зад", 1300, -450)
    tree.links.new(g3.outputs["Бобышка"], j2.inputs["Geometry"])
    tree.links.new(g4.outputs["Бобышка"], j2.inputs["Geometry"])

    u2 = add_node(tree, "GeometryNodeMeshBoolean", "4a.29",
                   "зад. половина трубы + бобышки", 1600, -450, operation='UNION')
    tree.links.new(n13b.outputs["Mesh"], in_sock(u2, "Mesh 2"))  # UNION: оба в Mesh 2
    tree.links.new(j2.outputs["Geometry"], in_sock(u2, "Mesh 2"))

    h2 = add_node(tree, "GeometryNodeJoinGeometry", "4a.30", "зазоры под винт зад", 1300, -580)
    tree.links.new(g3.outputs["Отверстие"], h2.inputs["Geometry"])
    tree.links.new(g4.outputs["Отверстие"], h2.inputs["Geometry"])

    d2 = add_node(tree, "GeometryNodeMeshBoolean", "4a.31",
                   "минус зазоры под винт -> клипса зад", 1900, -450, operation='DIFFERENCE')
    tree.links.new(u2.outputs["Mesh"], in_sock(d2, "Mesh 1"))
    tree.links.new(h2.outputs["Geometry"], in_sock(d2, "Mesh 2"))

    back_final = add_node(tree, "GeometryNodeMeshBoolean", "4a.32",
                           "Зад(вход) + клипса хомута -> Зад(выход)", 2300, 50,
                           operation='UNION')
    tree.links.new(GI("Зад"), in_sock(back_final, "Mesh 2"))  # UNION: оба в Mesh 2
    tree.links.new(d2.outputs["Mesh"], in_sock(back_final, "Mesh 2"))

    frame7 = make_frame(tree, "7. СБОРКА: ЗАДНЯЯ КЛИПСА ХОМУТА -> UNION С Зад",
                         [j2, u2, h2, d2, back_final])

    tree.links.new(front_final.outputs["Mesh"], gout.inputs["Перед"])
    tree.links.new(back_final.outputs["Mesh"], gout.inputs["Зад"])

    return tree


# ----------------------------------------------------------------------
# 3) NK.4_Закладные (верхний уровень)
# ----------------------------------------------------------------------
def build_inserts(boss_tree, clamp_tree, sampler_tree):
    tree = new_group(INSERTS_NAME)
    add_input(tree, "Перед", "NodeSocketGeometry")
    add_input(tree, "Зад", "NodeSocketGeometry")
    add_input(tree, "Точка_A", "NodeSocketVector")
    add_input(tree, "Точка_B", "NodeSocketVector")
    add_input(tree, "Профиль_точки", "NodeSocketGeometry",
              description="Выход 'Профиль_точки' Группы 2 (НЕ обрезанный по высоте - "
                           "используется для позиционирования магнитов у шва).")
    add_input(tree, "Точек_в_кольце", "NodeSocketInt", default=32, min_value=3, max_value=256)
    add_input(tree, "Колец_всего", "NodeSocketInt", default=48, min_value=2, max_value=4096)

    add_input(tree, "Трубка_диаметр_мм", "NodeSocketFloat", default=25.0, min_value=16.0, max_value=35.0)
    add_input(tree, "Хомут_толщина_мм", "NodeSocketFloat", default=3.5, min_value=2.5, max_value=6.0)
    add_input(tree, "Хомут_высота_мм", "NodeSocketFloat", default=14.0, min_value=8.0, max_value=25.0)
    add_input(tree, "Хомут1_высота_доля_от_колена", "NodeSocketFloat", default=0.20,
              min_value=0.0, max_value=1.0)
    add_input(tree, "Хомут2_высота_доля_от_колена", "NodeSocketFloat", default=0.80,
              min_value=0.0, max_value=1.0)
    add_input(tree, "Гайка_диаметр_мм", "NodeSocketFloat", default=4.0, min_value=3.6, max_value=4.6)
    add_input(tree, "Гайка_глубина_мм", "NodeSocketFloat", default=5.0, min_value=3.0, max_value=8.0)
    add_input(tree, "Винт_зазор_диаметр_мм", "NodeSocketFloat", default=3.4, min_value=3.2, max_value=3.8)

    add_input(tree, "Магнит_диаметр_мм", "NodeSocketFloat", default=10.0, min_value=8.0, max_value=12.0)
    add_input(tree, "Магнит_глубина_мм", "NodeSocketFloat", default=3.0, min_value=2.0, max_value=6.0)
    add_input(tree, "Магнит_зазор_мм", "NodeSocketFloat", default=0.2, min_value=0.0, max_value=0.5)
    add_input(tree, "Магнит1_высота_доля_от_колена", "NodeSocketFloat", default=0.25,
              min_value=0.0, max_value=1.0)
    add_input(tree, "Магнит2_высота_доля_от_колена", "NodeSocketFloat", default=0.70,
              min_value=0.0, max_value=1.0)

    add_output(tree, "VIS_Вместе", "NodeSocketGeometry")
    add_output(tree, "Перед", "NodeSocketGeometry")
    add_output(tree, "Зад", "NodeSocketGeometry")
    add_output(tree, "Провер_ВСЕ_OK", "NodeSocketBool")
    add_output(tree, "Провер_Отчёт", "NodeSocketString")

    gin = tree.nodes.new("NodeGroupInput")
    gin.name = "4.01 Вход"; gin.label = "4.01 Входные параметры"; gin.location = (-500, 400)
    gout = tree.nodes.new("NodeGroupOutput")
    gout.name = "4.99 Выход"; gout.label = "4.99 Выход"; gout.location = (4200, 400)

    def GI(name):
        return gin.outputs[name]

    # ------------------------------------------------------------------
    # 1. ДВА ХОМУТА (цепочкой: Перед/Зад проходят через оба)
    # ------------------------------------------------------------------
    c1 = _grp(tree, clamp_tree, "4.02", "Хомут 1", 0, 700)
    tree.links.new(GI("Перед"), c1.inputs["Перед"])
    tree.links.new(GI("Зад"), c1.inputs["Зад"])
    tree.links.new(GI("Точка_A"), c1.inputs["Точка_A"])
    tree.links.new(GI("Точка_B"), c1.inputs["Точка_B"])
    tree.links.new(GI("Хомут1_высота_доля_от_колена"), c1.inputs["Высота_доля_от_колена"])
    tree.links.new(GI("Трубка_диаметр_мм"), c1.inputs["Трубка_диаметр_мм"])
    tree.links.new(GI("Хомут_толщина_мм"), c1.inputs["Хомут_толщина_мм"])
    tree.links.new(GI("Хомут_высота_мм"), c1.inputs["Хомут_высота_мм"])
    tree.links.new(GI("Гайка_диаметр_мм"), c1.inputs["Гайка_диаметр_мм"])
    tree.links.new(GI("Гайка_глубина_мм"), c1.inputs["Гайка_глубина_мм"])
    tree.links.new(GI("Винт_зазор_диаметр_мм"), c1.inputs["Винт_зазор_диаметр_мм"])

    c2 = _grp(tree, clamp_tree, "4.03", "Хомут 2", 400, 700)
    tree.links.new(c1.outputs["Перед"], c2.inputs["Перед"])
    tree.links.new(c1.outputs["Зад"], c2.inputs["Зад"])
    tree.links.new(GI("Точка_A"), c2.inputs["Точка_A"])
    tree.links.new(GI("Точка_B"), c2.inputs["Точка_B"])
    tree.links.new(GI("Хомут2_высота_доля_от_колена"), c2.inputs["Высота_доля_от_колена"])
    tree.links.new(GI("Трубка_диаметр_мм"), c2.inputs["Трубка_диаметр_мм"])
    tree.links.new(GI("Хомут_толщина_мм"), c2.inputs["Хомут_толщина_мм"])
    tree.links.new(GI("Хомут_высота_мм"), c2.inputs["Хомут_высота_мм"])
    tree.links.new(GI("Гайка_диаметр_мм"), c2.inputs["Гайка_диаметр_мм"])
    tree.links.new(GI("Гайка_глубина_мм"), c2.inputs["Гайка_глубина_мм"])
    tree.links.new(GI("Винт_зазор_диаметр_мм"), c2.inputs["Винт_зазор_диаметр_мм"])

    frame1 = make_frame(tree, "1. ДВА ХОМУТА (цепочкой через Перед/Зад)", [c1, c2])

    # ------------------------------------------------------------------
    # 2. ПОЗИЦИИ МАГНИТОВ: сэмплируем Профиль_точки у шва (col=0/M/2)
    #    на 2 высотах - переиспользуем сэмплер Группы 3.
    # ------------------------------------------------------------------
    mhalf = add_node(tree, "ShaderNodeMath", "4.04", "M/2 (второй шов)",
                      -200, 100, operation='DIVIDE')
    tree.links.new(GI("Точек_в_кольце"), in_sock(mhalf, "Value"))
    in_sock(mhalf, "Value_001").default_value = 2.0
    mhalf_i = add_node(tree, "FunctionNodeFloatToInt", "4.04i", "-> Int", 60, 100)
    link(tree, mhalf, "Value", mhalf_i, "Float")

    nm1 = add_node(tree, "ShaderNodeMath", "4.05", "Колец_всего - 1",
                    -200, -50, operation='SUBTRACT')
    tree.links.new(GI("Колец_всего"), in_sock(nm1, "Value"))
    in_sock(nm1, "Value_001").default_value = 1.0

    def ring_row(num, label, x, y, height_frac_name):
        t = add_node(tree, "ShaderNodeMath", num + "t", "1-" + height_frac_name,
                      x, y, operation='SUBTRACT')
        in_sock(t, "Value").default_value = 1.0
        tree.links.new(GI(height_frac_name), in_sock(t, "Value_001"))
        row = add_node(tree, "ShaderNodeMath", num + "r", "round(T*(Колец_всего-1))",
                        x + 260, y, operation='MULTIPLY')
        link(tree, t, "Value", row, "Value")
        link(tree, nm1, "Value", row, "Value_001")
        row_round = add_node(tree, "ShaderNodeMath", num + "rr", "round", x + 520, y,
                              operation='ROUND')
        link(tree, row, "Value", row_round, "Value")
        row_i = add_node(tree, "FunctionNodeFloatToInt", num + "ri", "-> Int", x + 780, y)
        link(tree, row_round, "Value", row_i, "Float")
        return [t, row, row_round, row_i], row_i

    row1_nodes, row1_i = ring_row("4.06", "row", -200, 250, "Магнит1_высота_доля_от_колена")
    row2_nodes, row2_i = ring_row("4.07", "row", -200, 400, "Магнит2_высота_доля_от_колена")

    def sample_seam(num, label, x, y, row_i_node, col_val):
        s = _grp(tree, sampler_tree, num, label, x, y)
        tree.links.new(GI("Профиль_точки"), s.inputs["Точки"])
        tree.links.new(GI("Точек_в_кольце"), s.inputs["M_источника"])
        tree.links.new(row_i_node.outputs["Integer"], s.inputs["Row_от"])
        tree.links.new(row_i_node.outputs["Integer"], s.inputs["Row_до"])
        if isinstance(col_val, int):
            s.inputs["Col_от"].default_value = col_val
            s.inputs["Col_до"].default_value = col_val
        else:
            tree.links.new(col_val.outputs["Integer"], s.inputs["Col_от"])
            tree.links.new(col_val.outputs["Integer"], s.inputs["Col_до"])
        idx = add_node(tree, "GeometryNodeSampleIndex", num + "s", "позиция точки шва",
                        x + 280, y, data_type='FLOAT_VECTOR')
        tree.links.new(s.outputs["Mesh"], in_sock(idx, "Geometry"))
        posn = add_node(tree, "GeometryNodeInputPosition", num + "p", "Position", x, y - 120)
        link(tree, posn, "Position", idx, "Value_Vector")
        in_sock(idx, "Index").default_value = 0
        return [s, idx, posn], idx

    seamA_h1_nodes, seamA_h1 = sample_seam("4.08", "шов1(col0) высота1", 400, 900, row1_i, 0)
    seamB_h1_nodes, seamB_h1 = sample_seam("4.09", "шов2(col M/2) высота1", 400, 700, row1_i, mhalf_i)
    seamA_h2_nodes, seamA_h2 = sample_seam("4.10", "шов1(col0) высота2", 400, 500, row2_i, 0)
    seamB_h2_nodes, seamB_h2 = sample_seam("4.11", "шов2(col M/2) высота2", 400, 300, row2_i, mhalf_i)

    frame2 = make_frame(
        tree, "2. ПОЗИЦИИ 4 МАГНИТНЫХ ТОЧЕК (2 шва x 2 высоты), сэмплировано с Профиль_точки",
        [mhalf, mhalf_i, nm1] + row1_nodes + row2_nodes +
        seamA_h1_nodes + seamB_h1_nodes + seamA_h2_nodes + seamB_h2_nodes)

    # ------------------------------------------------------------------
    # 3. БОБЫШКИ+ГНЁЗДА МАГНИТОВ: по одной с каждой стороны на каждую точку
    # ------------------------------------------------------------------
    mr = add_node(tree, "ShaderNodeMath", "4.12", "R_магнита = Магнит_диаметр/2 + Магнит_зазор",
                   400, 100, operation='DIVIDE')
    tree.links.new(GI("Магнит_диаметр_мм"), in_sock(mr, "Value"))
    in_sock(mr, "Value_001").default_value = 2.0
    mr2 = add_node(tree, "ShaderNodeMath", "4.12b", "+ Магнит_зазор", 660, 100, operation='ADD')
    link(tree, mr, "Value", mr2, "Value")
    tree.links.new(GI("Магнит_зазор_мм"), in_sock(mr2, "Value_001"))

    boss_mr = add_node(tree, "ShaderNodeMath", "4.13", "R_бобышки_магнита = R_магнита + 5мм "
                        "(с запасом, чтобы бобышка надёжно охватывала тонкий шов)",
                        920, 100, operation='ADD')
    link(tree, mr2, "Value", boss_mr, "Value")
    in_sock(boss_mr, "Value_001").default_value = 5.0

    frame3a = make_frame(tree, "3. РАДИУСЫ ГНЕЗДА/БОБЫШКИ МАГНИТА", [mr, mr2, boss_mr])

    def magnet_pocket(num, label, x, y, pos_idx_node, direction):
        g = _grp(tree, boss_tree, num, label, x, y)
        tree.links.new(out_sock(pos_idx_node, "Value_Vector"), g.inputs["Позиция"])
        g.inputs["Направление"].default_value = direction
        tree.links.new(boss_mr.outputs["Value"], g.inputs["Радиус_бобышки_мм"])
        g.inputs["Длина_бобышки_мм"].default_value = 20.0
        tree.links.new(mr2.outputs["Value"], g.inputs["Радиус_отверстия_мм"])
        tree.links.new(GI("Магнит_глубина_мм"), g.inputs["Глубина_отверстия_мм"])
        return g

    mag_front_1 = magnet_pocket("4.14", "магнит перед: шов1 высота1", 1300, 900, seamA_h1, (0.0, 1.0, 0.0))
    mag_front_2 = magnet_pocket("4.15", "магнит перед: шов2 высота1", 1300, 750, seamB_h1, (0.0, 1.0, 0.0))
    mag_front_3 = magnet_pocket("4.16", "магнит перед: шов1 высота2", 1300, 600, seamA_h2, (0.0, 1.0, 0.0))
    mag_front_4 = magnet_pocket("4.17", "магнит перед: шов2 высота2", 1300, 450, seamB_h2, (0.0, 1.0, 0.0))

    mag_back_1 = magnet_pocket("4.18", "магнит зад: шов1 высота1", 1300, 250, seamA_h1, (0.0, -1.0, 0.0))
    mag_back_2 = magnet_pocket("4.19", "магнит зад: шов2 высота1", 1300, 100, seamB_h1, (0.0, -1.0, 0.0))
    mag_back_3 = magnet_pocket("4.20", "магнит зад: шов1 высота2", 1300, -50, seamA_h2, (0.0, -1.0, 0.0))
    mag_back_4 = magnet_pocket("4.21", "магнит зад: шов2 высота2", 1300, -200, seamB_h2, (0.0, -1.0, 0.0))

    frame3b = make_frame(
        tree, "3b. 8 ГНЁЗД МАГНИТОВ (4 на Перед, 4 на Зад)",
        [mag_front_1, mag_front_2, mag_front_3, mag_front_4,
         mag_back_1, mag_back_2, mag_back_3, mag_back_4])

    # -- сборка: перед --
    jbf = add_node(tree, "GeometryNodeJoinGeometry", "4.22", "бобышки магнитов (перед)", 1700, 750)
    for g in (mag_front_1, mag_front_2, mag_front_3, mag_front_4):
        tree.links.new(g.outputs["Бобышка"], jbf.inputs["Geometry"])

    uf = add_node(tree, "GeometryNodeMeshBoolean", "4.23",
                   "Перед(хомуты) + бобышки магнитов", 2000, 750, operation='UNION')
    tree.links.new(c2.outputs["Перед"], in_sock(uf, "Mesh 2"))
    tree.links.new(jbf.outputs["Geometry"], in_sock(uf, "Mesh 2"))

    jhf = add_node(tree, "GeometryNodeJoinGeometry", "4.24", "гнёзда магнитов (перед)", 1700, 600)
    for g in (mag_front_1, mag_front_2, mag_front_3, mag_front_4):
        tree.links.new(g.outputs["Отверстие"], jhf.inputs["Geometry"])

    df = add_node(tree, "GeometryNodeMeshBoolean", "4.25",
                   "минус гнёзда -> Перед (итог)", 2300, 750, operation='DIFFERENCE')
    tree.links.new(uf.outputs["Mesh"], in_sock(df, "Mesh 1"))
    tree.links.new(jhf.outputs["Geometry"], in_sock(df, "Mesh 2"))

    # -- сборка: зад --
    jbb = add_node(tree, "GeometryNodeJoinGeometry", "4.26", "бобышки магнитов (зад)", 1700, 200)
    for g in (mag_back_1, mag_back_2, mag_back_3, mag_back_4):
        tree.links.new(g.outputs["Бобышка"], jbb.inputs["Geometry"])

    ub = add_node(tree, "GeometryNodeMeshBoolean", "4.27",
                   "Зад(хомуты) + бобышки магнитов", 2000, 200, operation='UNION')
    tree.links.new(c2.outputs["Зад"], in_sock(ub, "Mesh 2"))
    tree.links.new(jbb.outputs["Geometry"], in_sock(ub, "Mesh 2"))

    jhb = add_node(tree, "GeometryNodeJoinGeometry", "4.28", "гнёзда магнитов (зад)", 1700, 50)
    for g in (mag_back_1, mag_back_2, mag_back_3, mag_back_4):
        tree.links.new(g.outputs["Отверстие"], jhb.inputs["Geometry"])

    db = add_node(tree, "GeometryNodeMeshBoolean", "4.29",
                   "минус гнёзда -> Зад (итог)", 2300, 200, operation='DIFFERENCE')
    tree.links.new(ub.outputs["Mesh"], in_sock(db, "Mesh 1"))
    tree.links.new(jhb.outputs["Geometry"], in_sock(db, "Mesh 2"))

    frame4 = make_frame(
        tree, "4. СБОРКА: МАГНИТЫ UNION+DIFFERENCE (по образцу Группы 4a)",
        [jbf, uf, jhf, df, jbb, ub, jhb, db])

    # ------------------------------------------------------------------
    # 5. ИТОГ: VIS, проверки, отчёт
    # ------------------------------------------------------------------
    vjoin = add_node(tree, "GeometryNodeJoinGeometry", "4.30", "VIS_Вместе = Перед+Зад", 2600, 500)
    tree.links.new(df.outputs["Mesh"], vjoin.inputs["Geometry"])
    tree.links.new(db.outputs["Mesh"], vjoin.inputs["Geometry"])

    def watertight_check(num, label, x, y, geo_node):
        en = add_node(tree, "GeometryNodeInputMeshEdgeNeighbors", num + "a",
                       "кол-во граней/ребро", x, y)
        cmp = add_node(tree, "FunctionNodeCompare", num + "b", "ребро граничное?",
                        x + 260, y, data_type='INT', operation='NOT_EQUAL')
        link(tree, en, "Face Count", cmp, "A_INT")
        in_sock(cmp, "B_INT").default_value = 2
        stat = add_node(tree, "GeometryNodeAttributeStatistic", num + "c",
                         "сумма граничных рёбер", x + 520, y, domain='EDGE')
        tree.links.new(geo_node.outputs["Mesh"], in_sock(stat, "Geometry"))
        link(tree, cmp, "Result", stat, "Attribute")
        ok = add_node(tree, "FunctionNodeCompare", num + "d", "== 0 ?", x + 780, y,
                       data_type='FLOAT', operation='EQUAL')
        link(tree, stat, "Sum", ok, "A")
        in_sock(ok, "B").default_value = 0.0
        return [en, cmp, stat, ok], ok

    vf_nodes, vf_ok = watertight_check("V4.1", "watertight", 2600, 250, df)
    vb_nodes, vb_ok = watertight_check("V4.2", "watertight", 2600, 0, db)

    v_all = add_node(tree, "FunctionNodeBooleanMath", "V4.3",
                      "ИТОГ: обе половины замкнуты", 3400, 150, operation='AND')
    link(tree, vf_ok, "Result", v_all, "Boolean")
    link(tree, vb_ok, "Result", v_all, "Boolean_001")

    rep_f = add_node(tree, "FunctionNodeValueToString", "4.31", "гранич.рёбер перед -> строка",
                      3400, 350)
    link(tree, vf_nodes[2], "Sum", rep_f, "Value")
    in_sock(rep_f, "Decimals").default_value = 0
    rep_b = add_node(tree, "FunctionNodeValueToString", "4.32", "гранич.рёбер зад -> строка",
                      3400, 250)
    link(tree, vb_nodes[2], "Sum", rep_b, "Value")
    in_sock(rep_b, "Decimals").default_value = 0
    rep_join = add_node(tree, "GeometryNodeStringJoin", "4.33", "сборка отчёта", 3650, 300)
    in_sock(rep_join, "Delimiter").default_value = " | "
    tree.links.new(rep_f.outputs["String"], rep_join.inputs["Strings"])
    tree.links.new(rep_b.outputs["String"], rep_join.inputs["Strings"])

    frame5 = make_frame(tree, "5. ИТОГ: VIS + ПРОВЕРКА ЗАМКНУТОСТИ + ОТЧЁТ",
                         vf_nodes + vb_nodes + [v_all, vjoin, rep_f, rep_b, rep_join])

    tree.links.new(vjoin.outputs["Geometry"], gout.inputs["VIS_Вместе"])
    tree.links.new(df.outputs["Mesh"], gout.inputs["Перед"])
    tree.links.new(db.outputs["Mesh"], gout.inputs["Зад"])
    tree.links.new(v_all.outputs["Boolean"], gout.inputs["Провер_ВСЕ_OK"])
    tree.links.new(rep_join.outputs["String"], gout.inputs["Провер_Отчёт"])

    return tree


def build_all_groups(sampler_tree=None):
    """sampler_tree: переиспользовать уже существующую группу
    'NK.3z_Сетка_по_индексам' (например, ту, что уже создала Группа 3
    в этом же сеансе). Если не передана - будет создана заново, НО
    ВНИМАНИЕ: если Группа 3 уже собрана в этом же файле/сеансе, у нас
    ОДНА node group с этим именем на весь .blend - build_sampler()
    удаляет и пересоздаёт её (new_group()), что оборвёт ссылки узлов
    Group внутри уже собранной NK.3a_Половина_оболочки на старую
    версию! Поэтому при совместной сборке с Группой 3 sampler_tree
    ОБЯЗАТЕЛЬНО нужно передавать явно (см. verify_group4.py)."""
    boss_tree = build_boss_hole()
    clamp_tree = build_clamp(boss_tree)
    if sampler_tree is None:
        sampler_tree = build_sampler()
    inserts_tree = build_inserts(boss_tree, clamp_tree, sampler_tree)
    return inserts_tree


if __name__ == "__main__":
    inserts_tree = build_all_groups()
    print("OK: '%s' собрана, узлов=%d" % (INSERTS_NAME, len(inserts_tree.nodes)))
