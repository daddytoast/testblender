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
MAGNET_NAME = "NK.4e_Закладная_магнита"
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
# 1e) NK.4e_Закладная_магнита (male=усечённый конус с зенковкой у узкого
# торца, female=подушка с воронкой-гнездом под тот же конус + карман
# магнита у дна) - см. правку по ревью в docs/04_group4_inserts.md.
#
# КЛЮЧЕВОЕ ОТЛИЧИЕ от старой версии (magnet_pocket() через NK.4c):
# закладная растёт СТРОГО ВДОЛЬ 'Dir' (локальная внешняя нормаль стены)
# ЦЕЛИКОМ ВНУТРЬ (anchor = Позиция, т.е. flush у внешней стены, без
# смещения) - это одновременно (а) гарантирует, что закладная никогда
# не пересекает внешнюю границу модели (растёт только в -Dir), и (б)
# чинит найденный этим же ревью баг: старая версия строилась СИММЕТРИЧНО
# вокруг точки на стене с осью ВДОЛЬ ПОВЕРХНОСТИ (не по нормали), из-за
# чего закладная почти не перекрывала саму стену и оставалась ДЫРЯВО
# НЕ СОЕДИНЕННОЙ с оболочкой (см. отдельную проверку связности компонент
# в docs) - Boolean UNION физически не имел общей области со стенкой.
# ----------------------------------------------------------------------
def build_magnet_insert():
    tree = new_group(MAGNET_NAME)
    add_input(tree, "Позиция", "NodeSocketVector",
              description="Точка на ВНЕШНЕЙ поверхности стены (шов), из 'Профиль_точки' Группы 2.")
    add_input(tree, "Dir", "NodeSocketVector", default=(1.0, 0.0, 0.0),
              description="Локальная внешняя нормаль стены в этой точке (атрибут 'dir' Группы 2) - "
                           "используется ТОЛЬКО чтобы утопить якорь и не выступать наружу.")
    add_input(tree, "Ось", "NodeSocketVector", default=(0.0, 1.0, 0.0),
              description="Направление роста закладной (КАСАТЕЛЬНО к стене, не по нормали!). "
                           "Растить вдоль нормали ('Dir') нельзя - точный Boolean-решатель "
                           "Blender даёт дырявые края на выпуклой поверхности (весь круглый "
                           "торец бобышки касается стены по касательной сразу со всех сторон). "
                           "Одно и то же значение для male/female в одной паре - тогда male-конус "
                           "'дотягивается' ровно туда же, где female открывает воронку.")
    add_input(tree, "Male", "NodeSocketFloat", default=0.0, min_value=0.0, max_value=1.0,
              description="0 = female (перед, воронка+магнит на дне), 1 = male (зад, конус+зенковка на торце).")
    add_input(tree, "Радиус_бобышки_мм", "NodeSocketFloat", default=9.0, min_value=5.0, max_value=20.0)
    add_input(tree, "Длина_бобышки_мм", "NodeSocketFloat", default=14.0, min_value=6.0, max_value=30.0)
    add_input(tree, "Кончик_радиус_мм", "NodeSocketFloat", default=6.0, min_value=3.0, max_value=15.0)
    add_input(tree, "Посадка_зазор_мм", "NodeSocketFloat", default=0.3, min_value=0.1, max_value=1.0,
              description="Зазор между male-конусом и female-воронкой (посадка с возможностью сборки).")
    add_input(tree, "Магнит_диаметр_мм", "NodeSocketFloat", default=10.0, min_value=6.0, max_value=14.0)
    add_input(tree, "Магнит_глубина_мм", "NodeSocketFloat", default=3.0, min_value=1.0, max_value=6.0)
    add_input(tree, "Магнит_зазор_мм", "NodeSocketFloat", default=0.2, min_value=0.0, max_value=1.0)
    add_input(tree, "Зенковка_радиус_мм", "NodeSocketFloat", default=6.5, min_value=3.0, max_value=15.0)
    add_input(tree, "Зенковка_глубина_мм", "NodeSocketFloat", default=1.0, min_value=0.2, max_value=5.0)
    add_input(tree, "Ребро_толщина_мм", "NodeSocketFloat", default=2.0, min_value=0.0, max_value=6.0,
              description="Толщина опционального ребра жёсткости (0 = без ребра).")
    add_input(tree, "Стена_нахлёст_мм", "NodeSocketFloat", default=2.0, min_value=0.5, max_value=5.0,
              description="Насколько бобышка выступает наружу за исходную точку (мало, всего "
                           "пара мм) - нужно для настоящего (не касательного) пересечения "
                           "объёмов при Boolean. Якорь утоплен на (Радиус_бобышки-нахлёст), "
                           "поэтому итоговый выступ = нахлёст, а не полный радиус.")
    add_output(tree, "Бобышка", "NodeSocketGeometry", "Для Boolean UNION с оболочкой.")
    add_output(tree, "Отверстие", "NodeSocketGeometry", "Для Boolean DIFFERENCE из оболочки.")

    gin = tree.nodes.new("NodeGroupInput")
    gin.name = "4e.01 Вход"; gin.label = "4e.01 Входные параметры"; gin.location = (-400, 0)
    gout = tree.nodes.new("NodeGroupOutput")
    gout.name = "4e.99 Выход"; gout.label = "4e.99 Выход"; gout.location = (4400, 0)

    def GI(name):
        return gin.outputs[name]

    # ВАЖНО (найдено этой же правкой, см. docs/04_group4_inserts.md):
    # закладная растёт КАСАТЕЛЬНО к стене (вдоль 'Ось'), а НЕ по нормали
    # ('Dir'). Раньше здесь стояла ось = -Dir (строго внутрь по нормали) -
    # это выглядело правильно для "не выступать наружу", но на выпуклой
    # поверхности круглый торец бобышки касается стены ПО КАСАТЕЛЬНОЙ
    # сразу со всех сторон одновременно - точный Boolean-решатель Blender
    # в этом случае стабильно давал дырявые края (проверено изолированным
    # тестом: 8 дырявых рёбер что с малым, что с большим радиусом бобышки,
    # что с высоким разрешением цилиндра - не лечится). Тот же тест с
    # КАСАТЕЛЬНОЙ осью (как было в самой первой версии этой группы, до
    # переноса на нормаль) на той же самой точке стены дал 0 дырявых
    # рёбер. 'Dir' используется только для лёгкого утапливания якоря.
    dirn = add_node(tree, "ShaderNodeVectorMath", "4e.02", "dir единичный", -100, 300, operation='NORMALIZE')
    tree.links.new(GI("Dir"), in_sock(dirn, "Vector"))
    axisn = add_node(tree, "ShaderNodeVectorMath", "4e.03", "Ось единичная (растёт вдоль неё)",
                      150, 300, operation='NORMALIZE')
    tree.links.new(GI("Ось"), in_sock(axisn, "Vector"))

    align = add_node(tree, "FunctionNodeAlignEulerToVector", "4e.04",
                      "Euler: локальный Z -> Ось", 400, 100)
    align.axis = 'Z'
    link(tree, axisn, "Vector", align, "Vector")

    male_cmp = add_node(tree, "FunctionNodeCompare", "4e.05", "Male > 0.5", 150, 150,
                         data_type='FLOAT', operation='GREATER_THAN')
    tree.links.new(GI("Male"), in_sock(male_cmp, "A"))
    in_sock(male_cmp, "B").default_value = 0.5

    # Якорь утоплен по нормали на (Радиус_бобышки - нахлёст), поэтому
    # круглый бок бобышки (перпендикулярно 'Ось', в т.ч. вдоль 'Dir')
    # выступает наружу ровно на Стена_нахлёст_мм - не больше.
    # female-подушка на 3мм шире Радиус_бобышки (см. "R_подушки" ниже) -
    # утопление считаем от НЕЁ (максимальный реальный радиус тела),
    # иначе female выступает на 3мм больше задуманного нахлёста.
    pad_r_for_inset = add_node(tree, "ShaderNodeMath", "4e.05e", "Радиус_бобышки + 3мм (=R_подушки)",
                                150, 350, operation='ADD')
    tree.links.new(GI("Радиус_бобышки_мм"), in_sock(pad_r_for_inset, "Value"))
    in_sock(pad_r_for_inset, "Value_001").default_value = 3.0
    inset_depth = add_node(tree, "ShaderNodeMath", "4e.05a", "утопление = R_подушки - нахлёст",
                            150, 500, operation='SUBTRACT')
    link(tree, pad_r_for_inset, "Value", inset_depth, "Value")
    tree.links.new(GI("Стена_нахлёст_мм"), in_sock(inset_depth, "Value_001"))
    inset_off = add_node(tree, "ShaderNodeVectorMath", "4e.05b", "-dir*утопление",
                          400, 450, operation='SCALE')
    link(tree, dirn, "Vector", inset_off, "Vector")
    inset_neg = add_node(tree, "ShaderNodeMath", "4e.05d", "* -1", 400, 600, operation='MULTIPLY')
    link(tree, inset_depth, "Value", inset_neg, "Value")
    in_sock(inset_neg, "Value_001").default_value = -1.0
    link(tree, inset_neg, "Value", inset_off, "Scale")
    pos_eff = add_node(tree, "ShaderNodeVectorMath", "4e.05c", "якорь = Позиция - dir*утопление",
                        650, 400, operation='ADD')
    tree.links.new(GI("Позиция"), in_sock(pos_eff, "Vector"))
    link(tree, inset_off, "Vector", pos_eff, "Vector_001")

    frameA = make_frame(
        tree, "A. ОСЬ = 'Ось' (КАСАТЕЛЬНО к стене!), якорь утоплен ПО НОРМАЛИ на (R-нахлёст)",
        [dirn, axisn, align, male_cmp, pad_r_for_inset, inset_depth, inset_off, inset_neg, pos_eff])

    # -- точка на оси на заданной глубине: point(depth) = якорь + Ось*depth --
    along_nodes = []

    def along(num, label, x, y, depth_out_socket):
        off = add_node(tree, "ShaderNodeVectorMath", num + "v", label, x, y, operation='SCALE')
        link(tree, axisn, "Vector", off, "Vector")
        tree.links.new(depth_out_socket, in_sock(off, "Scale"))
        pos = add_node(tree, "ShaderNodeVectorMath", num + "p", label + " (точка)", x + 260, y, operation='ADD')
        link(tree, pos_eff, "Vector", pos, "Vector")
        link(tree, off, "Vector", pos, "Vector_001")
        along_nodes.extend([off, pos])
        return pos

    halflen = add_node(tree, "ShaderNodeMath", "4e.06", "Длина/2", -100, -100, operation='MULTIPLY')
    tree.links.new(GI("Длина_бобышки_мм"), in_sock(halflen, "Value"))
    in_sock(halflen, "Value_001").default_value = 0.5
    along_nodes.append(halflen)
    mid_pos = along("4e.07", "середина конуса (Длина/2 внутрь)", 150, -100, out_sock(halflen, "Value"))
    tip_pos = along("4e.08", "торец конуса/вход воронки (Длина внутрь)", 150, -300, GI("Длина_бобышки_мм"))

    frameB = make_frame(tree, "B. КЛЮЧЕВЫЕ ТОЧКИ НА ОСИ (середина конуса на Длина/2, торец на Длина)",
                         along_nodes)

    # ------------------------------------------------------------------
    # C. БОБЫШКА: male = усечённый конус (широкий торец у стены, узкий
    # у torec, глубина Длина), female = цилиндр-подушка (чуть шире и
    # длиннее, с запасом под воронку+магнит)
    # ------------------------------------------------------------------
    male_cone = add_node(tree, "GeometryNodeMeshCone", "4e.09", "male: усечённый конус",
                          900, 400, fill_type='NGON')
    tree.links.new(GI("Радиус_бобышки_мм"), in_sock(male_cone, "Radius Bottom"))
    tree.links.new(GI("Кончик_радиус_мм"), in_sock(male_cone, "Radius Top"))
    tree.links.new(GI("Длина_бобышки_мм"), in_sock(male_cone, "Depth"))
    male_xf = add_node(tree, "GeometryNodeTransform", "4e.10", "male на место", 1200, 400)
    link(tree, male_cone, "Mesh", male_xf, "Geometry")
    link(tree, align, "Rotation", male_xf, "Rotation")
    link(tree, mid_pos, "Vector", male_xf, "Translation")

    fem_pad_r = add_node(tree, "ShaderNodeMath", "4e.11", "R_подушки = R_бобышки + 3мм",
                          900, 150, operation='ADD')
    tree.links.new(GI("Радиус_бобышки_мм"), in_sock(fem_pad_r, "Value"))
    in_sock(fem_pad_r, "Value_001").default_value = 3.0
    fem_pad_len = add_node(tree, "ShaderNodeMath", "4e.12",
                            "Длина_подушки = Длина + Магнит_глубина + 1.5мм",
                            900, 0, operation='ADD')
    tree.links.new(GI("Длина_бобышки_мм"), in_sock(fem_pad_len, "Value"))
    fem_pad_len2 = add_node(tree, "ShaderNodeMath", "4e.12b", "Магнит_глубина+1.5", 650, -50, operation='ADD')
    tree.links.new(GI("Магнит_глубина_мм"), in_sock(fem_pad_len2, "Value"))
    in_sock(fem_pad_len2, "Value_001").default_value = 1.5
    link(tree, fem_pad_len2, "Value", fem_pad_len, "Value_001")

    fem_cyl = add_node(tree, "GeometryNodeMeshCylinder", "4e.13", "female: подушка (цилиндр)",
                        900, 250, fill_type='NGON')
    link(tree, fem_pad_r, "Value", fem_cyl, "Radius")
    link(tree, fem_pad_len, "Value", fem_cyl, "Depth")
    fem_pad_halflen = add_node(tree, "ShaderNodeMath", "4e.14", "Длина_подушки/2",
                                900, -150, operation='MULTIPLY')
    link(tree, fem_pad_len, "Value", fem_pad_halflen, "Value")
    in_sock(fem_pad_halflen, "Value_001").default_value = 0.5
    fem_pad_center = along("4e.15", "центр подушки (Длина_подушки/2 внутрь)", 1150, -150,
                            out_sock(fem_pad_halflen, "Value"))
    fem_xf = add_node(tree, "GeometryNodeTransform", "4e.16", "female на место", 1500, 250)
    link(tree, fem_cyl, "Mesh", fem_xf, "Geometry")
    link(tree, align, "Rotation", fem_xf, "Rotation")
    link(tree, fem_pad_center, "Vector", fem_xf, "Translation")

    boss_sw = add_node(tree, "GeometryNodeSwitch", "4e.17", "male? бобышка", 1800, 320, input_type='GEOMETRY')
    link(tree, male_cmp, "Result", boss_sw, "Switch_001")
    link(tree, fem_xf, "Geometry", boss_sw, "False_006")
    link(tree, male_xf, "Geometry", boss_sw, "True_006")

    frameC = make_frame(
        tree, "C. БОБЫШКА: male=усечённый конус (у стены R_бобышки, у торца Кончик_радиус); "
        "female=цилиндр-подушка", [male_cone, male_xf, fem_pad_r, fem_pad_len, fem_pad_len2,
                                     fem_cyl, fem_pad_halflen, fem_xf, boss_sw])

    # ------------------------------------------------------------------
    # D. MALE ОТВЕРСТИЕ: карман магнита + зенковка у узкого торца
    # (дальше вглубь модели от torec на Магнит_глубина/Зенковка_глубина)
    # ------------------------------------------------------------------
    mag_r = add_node(tree, "ShaderNodeMath", "4e.18", "R_магнита = Диаметр/2", 150, -500, operation='DIVIDE')
    tree.links.new(GI("Магнит_диаметр_мм"), in_sock(mag_r, "Value"))
    in_sock(mag_r, "Value_001").default_value = 2.0
    mag_r2 = add_node(tree, "ShaderNodeMath", "4e.19", "+Магнит_зазор", 400, -500, operation='ADD')
    link(tree, mag_r, "Value", mag_r2, "Value")
    tree.links.new(GI("Магнит_зазор_мм"), in_sock(mag_r2, "Value_001"))

    pocket_cyl = add_node(tree, "GeometryNodeMeshCylinder", "4e.20", "карман магнита (общий male/female)",
                           900, -700, fill_type='NGON')
    link(tree, mag_r2, "Value", pocket_cyl, "Radius")
    pocket_depth2 = add_node(tree, "ShaderNodeMath", "4e.21", "Магнит_глубина*2 (запас)",
                              650, -750, operation='MULTIPLY')
    tree.links.new(GI("Магнит_глубина_мм"), in_sock(pocket_depth2, "Value"))
    in_sock(pocket_depth2, "Value_001").default_value = 2.0
    link(tree, pocket_depth2, "Value", pocket_cyl, "Depth")

    pocket_halfdepth = add_node(tree, "ShaderNodeMath", "4e.22", "Магнит_глубина/2",
                                 650, -900, operation='MULTIPLY')
    tree.links.new(GI("Магнит_глубина_мм"), in_sock(pocket_halfdepth, "Value"))
    in_sock(pocket_halfdepth, "Value_001").default_value = 0.5
    pocket_depth_from_pos = add_node(tree, "ShaderNodeMath", "4e.23",
                                      "глубина_от_Позиции = Длина + Магнит_глубина/2",
                                      900, -950, operation='ADD')
    tree.links.new(GI("Длина_бобышки_мм"), in_sock(pocket_depth_from_pos, "Value"))
    link(tree, pocket_halfdepth, "Value", pocket_depth_from_pos, "Value_001")
    pocket_center = along("4e.24", "центр кармана (torec + Магнит_глубина/2 внутрь)", 1150, -950,
                           out_sock(pocket_depth_from_pos, "Value"))
    pocket_xf = add_node(tree, "GeometryNodeTransform", "4e.25", "карман на место", 1500, -700)
    link(tree, pocket_cyl, "Mesh", pocket_xf, "Geometry")
    link(tree, align, "Rotation", pocket_xf, "Rotation")
    link(tree, pocket_center, "Vector", pocket_xf, "Translation")

    cs_cone = add_node(tree, "GeometryNodeMeshCone", "4e.26", "male: зенковка (конус)",
                        900, -1150, fill_type='NGON')
    tree.links.new(GI("Зенковка_радиус_мм"), in_sock(cs_cone, "Radius Bottom"))
    link(tree, mag_r2, "Value", cs_cone, "Radius Top")
    tree.links.new(GI("Зенковка_глубина_мм"), in_sock(cs_cone, "Depth"))
    cs_halfdepth = add_node(tree, "ShaderNodeMath", "4e.27", "Зенковка_глубина/2",
                             650, -1200, operation='MULTIPLY')
    tree.links.new(GI("Зенковка_глубина_мм"), in_sock(cs_halfdepth, "Value"))
    in_sock(cs_halfdepth, "Value_001").default_value = 0.5
    cs_depth_from_pos = add_node(tree, "ShaderNodeMath", "4e.28",
                                  "глубина_от_Позиции = Длина + Зенковка_глубина/2",
                                  900, -1250, operation='ADD')
    tree.links.new(GI("Длина_бобышки_мм"), in_sock(cs_depth_from_pos, "Value"))
    link(tree, cs_halfdepth, "Value", cs_depth_from_pos, "Value_001")
    cs_center = along("4e.29", "центр зенковки (torec + Зенковка_глубина/2 внутрь)", 1150, -1250,
                       out_sock(cs_depth_from_pos, "Value"))
    cs_xf = add_node(tree, "GeometryNodeTransform", "4e.30", "зенковка на место", 1500, -1150)
    link(tree, cs_cone, "Mesh", cs_xf, "Geometry")
    link(tree, align, "Rotation", cs_xf, "Rotation")
    link(tree, cs_center, "Vector", cs_xf, "Translation")

    male_hole_join = add_node(tree, "GeometryNodeJoinGeometry", "4e.31", "male: карман+зенковка",
                               1800, -950)
    tree.links.new(pocket_xf.outputs["Geometry"], male_hole_join.inputs["Geometry"])
    tree.links.new(cs_xf.outputs["Geometry"], male_hole_join.inputs["Geometry"])

    frameD = make_frame(
        tree, "D. MALE ОТВЕРСТИЕ: карман магнита + зенковка (вглубь модели от узкого торца)",
        [mag_r, mag_r2, pocket_cyl, pocket_depth2, pocket_halfdepth, pocket_depth_from_pos,
         pocket_xf, cs_cone, cs_halfdepth, cs_depth_from_pos, cs_xf, male_hole_join])

    # ------------------------------------------------------------------
    # E. FEMALE ОТВЕРСТИЕ: воронка (конус, повторяет форму male-конуса
    # + Посадка_зазор_мм по радиусу) + тот же карман магнита у torec
    # (той же глубины, что и male - при сборке магниты сходятся встык)
    # ------------------------------------------------------------------
    fem_r_bottom = add_node(tree, "ShaderNodeMath", "4e.32", "R_бобышки+Посадка_зазор",
                             150, -1450, operation='ADD')
    tree.links.new(GI("Радиус_бобышки_мм"), in_sock(fem_r_bottom, "Value"))
    tree.links.new(GI("Посадка_зазор_мм"), in_sock(fem_r_bottom, "Value_001"))
    fem_r_top = add_node(tree, "ShaderNodeMath", "4e.33", "Кончик_радиус+Посадка_зазор",
                          150, -1600, operation='ADD')
    tree.links.new(GI("Кончик_радиус_мм"), in_sock(fem_r_top, "Value"))
    tree.links.new(GI("Посадка_зазор_мм"), in_sock(fem_r_top, "Value_001"))

    funnel_cone = add_node(tree, "GeometryNodeMeshCone", "4e.34",
                            "female: воронка (конус, форма male + зазор)", 900, -1450, fill_type='NGON')
    link(tree, fem_r_bottom, "Value", funnel_cone, "Radius Bottom")
    link(tree, fem_r_top, "Value", funnel_cone, "Radius Top")
    tree.links.new(GI("Длина_бобышки_мм"), in_sock(funnel_cone, "Depth"))
    funnel_xf = add_node(tree, "GeometryNodeTransform", "4e.35", "воронка на место", 1500, -1450)
    link(tree, funnel_cone, "Mesh", funnel_xf, "Geometry")
    link(tree, align, "Rotation", funnel_xf, "Rotation")
    link(tree, mid_pos, "Vector", funnel_xf, "Translation")

    fem_pocket_xf = add_node(tree, "GeometryNodeTransform", "4e.36", "female карман магнита (та же глубина)",
                              1500, -1700)
    link(tree, pocket_cyl, "Mesh", fem_pocket_xf, "Geometry")
    link(tree, align, "Rotation", fem_pocket_xf, "Rotation")
    link(tree, pocket_center, "Vector", fem_pocket_xf, "Translation")

    female_hole_join = add_node(tree, "GeometryNodeJoinGeometry", "4e.37", "female: воронка+карман",
                                 1800, -1550)
    tree.links.new(funnel_xf.outputs["Geometry"], female_hole_join.inputs["Geometry"])
    tree.links.new(fem_pocket_xf.outputs["Geometry"], female_hole_join.inputs["Geometry"])

    frameE = make_frame(
        tree, "E. FEMALE ОТВЕРСТИЕ: воронка под male-конус (+Посадка_зазор) + карман магнита у torec",
        [fem_r_bottom, fem_r_top, funnel_cone, funnel_xf, fem_pocket_xf, female_hole_join])

    hole_sw = add_node(tree, "GeometryNodeSwitch", "4e.38", "male? отверстие", 2100, -1150,
                        input_type='GEOMETRY')
    link(tree, male_cmp, "Result", hole_sw, "Switch_001")
    link(tree, female_hole_join, "Geometry", hole_sw, "False_006")
    link(tree, male_hole_join, "Geometry", hole_sw, "True_006")

    # ------------------------------------------------------------------
    # F. РЕБРО ЖЁСТКОСТИ (опционально): тонкий гребень вдоль -dir,
    # соединяющий бобышку со стеной по касательной - добавляет опору
    # без увеличения диаметра бобышки.
    # ------------------------------------------------------------------
    rib_cube = add_node(tree, "GeometryNodeMeshCube", "4e.39", "куб-ребро 1x1x1", 900, 700)
    in_sock(rib_cube, "Size").default_value = (1.0, 1.0, 1.0)
    # Высота ребра НАМЕРЕННО скромная (меньше радиуса бобышки): большой
    # плоский гребень поперёк выпуклой стены даёт ту же болезнь Boolean-
    # решателя, что и старая версия закладной вдоль нормали (см. docs) -
    # широкая плоская грань почти касается кривой поверхности сразу на
    # большой площади. Небольшое ребро всё ещё добавляет опору, но не
    # рискует зацепить стену по касательной.
    rib_h = add_node(tree, "ShaderNodeMath", "4e.40", "высота ребра = R_бобышки*0.5",
                      650, 850, operation='MULTIPLY')
    tree.links.new(GI("Радиус_бобышки_мм"), in_sock(rib_h, "Value"))
    in_sock(rib_h, "Value_001").default_value = 0.5
    ribsize = add_node(tree, "ShaderNodeCombineXYZ", "4e.41",
                        "размер=(толщина, длина_вдоль_Оси=Длина, высота)", 900, 850)
    tree.links.new(GI("Ребро_толщина_мм"), in_sock(ribsize, "X"))
    tree.links.new(GI("Длина_бобышки_мм"), in_sock(ribsize, "Y"))
    link(tree, rib_h, "Value", ribsize, "Z")
    rib_sc = add_node(tree, "GeometryNodeTransform", "4e.42", "масштаб ребра", 1150, 700)
    link(tree, rib_cube, "Mesh", rib_sc, "Geometry")
    link(tree, ribsize, "Vector", rib_sc, "Scale")
    rib_align = add_node(tree, "FunctionNodeAlignEulerToVector", "4e.43",
                          "Euler: локальный Y -> Ось (длина ребра вдоль закладной)", 900, 550)
    rib_align.axis = 'Y'
    link(tree, axisn, "Vector", rib_align, "Vector")
    rib_xf = add_node(tree, "GeometryNodeTransform", "4e.44", "ребро на место (центр=середина закладной)",
                       1500, 700)
    link(tree, rib_sc, "Geometry", rib_xf, "Geometry")
    link(tree, rib_align, "Rotation", rib_xf, "Rotation")
    link(tree, mid_pos, "Vector", rib_xf, "Translation")

    rib_on = add_node(tree, "FunctionNodeCompare", "4e.45", "Ребро_толщина > 0 ?", 900, 400,
                       data_type='FLOAT', operation='GREATER_THAN')
    tree.links.new(GI("Ребро_толщина_мм"), in_sock(rib_on, "A"))
    in_sock(rib_on, "B").default_value = 0.001
    empty_rib = add_node(tree, "GeometryNodeMeshCube", "4e.46", "пусто (для выключенного ребра)",
                          1150, 550)
    in_sock(empty_rib, "Size").default_value = (0.0, 0.0, 0.0)
    rib_sw = add_node(tree, "GeometryNodeSwitch", "4e.47", "ребро вкл?", 1800, 550, input_type='GEOMETRY')
    link(tree, rib_on, "Result", rib_sw, "Switch_001")
    link(tree, empty_rib, "Mesh", rib_sw, "False_006")
    link(tree, rib_xf, "Geometry", rib_sw, "True_006")

    boss_plus_rib = add_node(tree, "GeometryNodeJoinGeometry", "4e.48", "бобышка + ребро", 2100, 380)
    link(tree, boss_sw, "Output_006", boss_plus_rib, "Geometry")
    link(tree, rib_sw, "Output_006", boss_plus_rib, "Geometry")

    frameF = make_frame(
        tree, "F. РЕБРО ЖЁСТКОСТИ (опционально, толщина=0 отключает)",
        [rib_cube, rib_h, ribsize, rib_sc, rib_align, rib_xf, rib_on, empty_rib, rib_sw, boss_plus_rib])

    tree.links.new(boss_plus_rib.outputs["Geometry"], gout.inputs["Бобышка"])
    tree.links.new(out_sock(hole_sw, "Output_006"), gout.inputs["Отверстие"])
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
    add_input(tree, "Стойка_радиус_мм", "NodeSocketFloat", default=5.5, min_value=3.5, max_value=10.0,
              description="Радиус закладной-стойки под гайку на внутренней стороне передней панели.")
    add_input(tree, "Хомут_зазор_под_шайбы_мм", "NodeSocketFloat", default=1.5,
              min_value=0.0, max_value=5.0,
              description="Зазор между стойкой (на стене) и концом хомута - место под шайбы "
                           "для тонкой корректировки позиционирования.")
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

    # передняя бобышка + СКВОЗНОЕ отверстие под винт (гайка теперь не
    # здесь - см. секцию 5b: отдельная закладная-стойка на внутренней
    # стороне передней панели, со своим пилотным отверстием под гайку)
    g1 = _grp(tree, boss_tree, "4a.19", "бобышка+отверстие (перед, конец1)", 1000, -50)
    tree.links.new(n16.outputs["Vector"], g1.inputs["Позиция"])
    g1.inputs["Направление"].default_value = (0.0, 1.0, 0.0)
    tree.links.new(boss_r2.outputs["Value"], g1.inputs["Радиус_бобышки_мм"])
    g1.inputs["Длина_бобышки_мм"].default_value = 12.0
    tree.links.new(clr_r.outputs["Value"], g1.inputs["Радиус_отверстия_мм"])
    g1.inputs["Глубина_отверстия_мм"].default_value = 8.0

    # передняя бобышка + СКВОЗНОЕ отверстие, конец 2
    g2 = _grp(tree, boss_tree, "4a.20", "бобышка+отверстие (перед, конец2)", 1000, -250)
    tree.links.new(n17.outputs["Vector"], g2.inputs["Позиция"])
    g2.inputs["Направление"].default_value = (0.0, 1.0, 0.0)
    tree.links.new(boss_r2.outputs["Value"], g2.inputs["Радиус_бобышки_мм"])
    g2.inputs["Длина_бобышки_мм"].default_value = 12.0
    tree.links.new(clr_r.outputs["Value"], g2.inputs["Радиус_отверстия_мм"])
    g2.inputs["Глубина_отверстия_мм"].default_value = 8.0

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

    frame5 = make_frame(tree, "5. БОБЫШКИ+ОТВЕРСТИЯ: сквозные под винт М3 (перед и зад одинаково)",
                         [boss_r, boss_r2, g1, g2, g3, g4])

    # ------------------------------------------------------------------
    # 5b. ЗАКЛАДНЫЕ-СТОЙКИ ПОД ГАЙКУ (только на передней части, с
    # внутренней стороны передней площадки, с рёбрами жёсткости к стене)
    # Хомут сам по себе НЕ касается внешней оболочки (он маленький, вокруг
    # трубки, в центре полости) - раньше бобышки хомута просто "плавали"
    # внутри Boolean UNION, физически НЕ соединяясь со стенкой (найдено
    # проверкой связности компонент меша при этой правке, см. docs).
    # Поэтому: находим БЛИЖАЙШУЮ точку реальной стены Перед через
    # `Geometry Proximity`, ставим туда закладную-стойку (цилиндр с
    # пилотным глухим отверстием под гайку, растёт от стены К хомуту),
    # и явно НЕ доводим её до конца хомута - зазор оставлен под шайбы.
    # ------------------------------------------------------------------
    def nut_standoff(num, label, x, y, end_pos_node):
        prox = add_node(tree, "GeometryNodeProximity", num + "px",
                         "ближайшая точка стены Перед", x, y + 150, target_element='FACES')
        tree.links.new(GI("Перед"), in_sock(prox, "Target"))
        link(tree, end_pos_node, "Vector", prox, "Source Position")

        reach = add_node(tree, "ShaderNodeVectorMath", num + "rv",
                          "направление стена->хомут", x + 260, y + 150, operation='SUBTRACT')
        link(tree, end_pos_node, "Vector", reach, "Vector")
        tree.links.new(out_sock(prox, "Position"), in_sock(reach, "Vector_001"))
        reach_n = add_node(tree, "ShaderNodeVectorMath", num + "rn", "единичное",
                            x + 520, y + 150, operation='NORMALIZE')
        link(tree, reach, "Vector", reach_n, "Vector")

        standoff_len = add_node(tree, "ShaderNodeMath", num + "sl",
                                 "длина стойки = расстояние_до_стены - Зазор_под_шайбы",
                                 x + 260, y + 300, operation='SUBTRACT')
        tree.links.new(out_sock(prox, "Distance"), in_sock(standoff_len, "Value"))
        tree.links.new(GI("Хомут_зазор_под_шайбы_мм"), in_sock(standoff_len, "Value_001"))
        standoff_len_safe = add_node(tree, "ShaderNodeMath", num + "sls",
                                      "min(длина, 25мм) - не даём стойке стать нереально длинной",
                                      x + 520, y + 300, operation='MINIMUM')
        link(tree, standoff_len, "Value", standoff_len_safe, "Value")
        in_sock(standoff_len_safe, "Value_001").default_value = 25.0
        standoff_len_pos = add_node(tree, "ShaderNodeMath", num + "slp", "max(длина, 4мм)",
                                     x + 780, y + 300, operation='MAXIMUM')
        link(tree, standoff_len_safe, "Value", standoff_len_pos, "Value")
        in_sock(standoff_len_pos, "Value_001").default_value = 4.0

        # + 2мм нахлёста в стену (иначе стойка лишь КАСАЕТСЯ поверхности
        # в одной точке - Boolean UNION с касанием "в ноль" ненадёжен;
        # нужно реальное пересечение объёмов для чистого сращивания).
        len_total = add_node(tree, "ShaderNodeMath", num + "lt", "+ 2мм нахлёста в стену",
                              x + 1040, y + 300, operation='ADD')
        link(tree, standoff_len_pos, "Value", len_total, "Value")
        in_sock(len_total, "Value_001").default_value = 2.0

        near_off = add_node(tree, "ShaderNodeVectorMath", num + "no", "-направление*2мм (вглубь стены)",
                             x + 260, y + 450, operation='SCALE')
        link(tree, reach_n, "Vector", near_off, "Vector")
        in_sock(near_off, "Scale").default_value = -2.0
        near_point = add_node(tree, "ShaderNodeVectorMath", num + "np", "near = точка_стены - направление*2мм",
                               x + 520, y + 450, operation='ADD')
        tree.links.new(out_sock(prox, "Position"), in_sock(near_point, "Vector"))
        link(tree, near_off, "Vector", near_point, "Vector_001")

        half_len = add_node(tree, "ShaderNodeMath", num + "hl", "(длина+нахлёст)/2", x + 780, y + 150,
                             operation='MULTIPLY')
        link(tree, len_total, "Value", half_len, "Value")
        in_sock(half_len, "Value_001").default_value = 0.5
        half_off = add_node(tree, "ShaderNodeVectorMath", num + "ho", "направление*(длина+нахлёст)/2",
                             x + 1040, y + 150, operation='SCALE')
        link(tree, reach_n, "Vector", half_off, "Vector")
        link(tree, half_len, "Value", half_off, "Scale")
        standoff_center = add_node(tree, "ShaderNodeVectorMath", num + "sc",
                                    "центр = near + направление*(длина+нахлёст)/2",
                                    x + 1300, y + 150, operation='ADD')
        link(tree, near_point, "Vector", standoff_center, "Vector")
        link(tree, half_off, "Vector", standoff_center, "Vector_001")

        g = _grp(tree, boss_tree, num, label, x + 1600, y)
        tree.links.new(out_sock(standoff_center, "Vector"), g.inputs["Позиция"])
        tree.links.new(out_sock(reach_n, "Vector"), g.inputs["Направление"])
        tree.links.new(GI("Стойка_радиус_мм"), g.inputs["Радиус_бобышки_мм"])
        tree.links.new(out_sock(len_total, "Value"), g.inputs["Длина_бобышки_мм"])
        tree.links.new(nut_r.outputs["Value"], g.inputs["Радиус_отверстия_мм"])
        tree.links.new(GI("Гайка_глубина_мм"), g.inputs["Глубина_отверстия_мм"])
        return ([prox, reach, reach_n, standoff_len, standoff_len_safe, standoff_len_pos,
                 len_total, near_off, near_point, half_len, half_off, standoff_center, g], g)

    standoff1_nodes, standoff1 = nut_standoff("4a.33", "стойка-гайка (конец1)", 1000, -900, n16)
    standoff2_nodes, standoff2 = nut_standoff("4a.34", "стойка-гайка (конец2)", 1000, -1250, n17)

    frame5b = make_frame(
        tree, "5b. ЗАКЛАДНЫЕ-СТОЙКИ ПОД ГАЙКУ (растут ОТ стены Перед к хомуту, "
        "зазор под шайбы, соединяют хомут со стенкой)",
        standoff1_nodes + standoff2_nodes)

    # -- сборка: перед --
    j1 = add_node(tree, "GeometryNodeJoinGeometry", "4a.23", "бобышки перед + стойки-гайки", 1300, -50)
    tree.links.new(g1.outputs["Бобышка"], j1.inputs["Geometry"])
    tree.links.new(g2.outputs["Бобышка"], j1.inputs["Geometry"])
    tree.links.new(standoff1.outputs["Бобышка"], j1.inputs["Geometry"])
    tree.links.new(standoff2.outputs["Бобышка"], j1.inputs["Geometry"])

    u1 = add_node(tree, "GeometryNodeMeshBoolean", "4a.24",
                   "перед. половина трубы + бобышки", 1600, -50, operation='UNION')
    tree.links.new(n13f.outputs["Mesh"], in_sock(u1, "Mesh 2"))  # UNION: оба в Mesh 2, см. врезку выше
    tree.links.new(j1.outputs["Geometry"], in_sock(u1, "Mesh 2"))

    h1 = add_node(tree, "GeometryNodeJoinGeometry", "4a.25", "отверстия перед (сквозные+гайка стойки)", 1300, -180)
    tree.links.new(g1.outputs["Отверстие"], h1.inputs["Geometry"])
    tree.links.new(g2.outputs["Отверстие"], h1.inputs["Geometry"])
    tree.links.new(standoff1.outputs["Отверстие"], h1.inputs["Geometry"])
    tree.links.new(standoff2.outputs["Отверстие"], h1.inputs["Geometry"])

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
def build_inserts(boss_tree, clamp_tree, sampler_tree, magnet_tree):
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
    add_input(tree, "Стойка_радиус_мм", "NodeSocketFloat", default=5.5, min_value=3.5, max_value=10.0,
              description="Радиус закладной-стойки под гайку на внутренней стороне передней панели.")
    add_input(tree, "Хомут_зазор_под_шайбы_мм", "NodeSocketFloat", default=1.5,
              min_value=0.0, max_value=5.0,
              description="Зазор между стойкой и концом хомута - место под шайбы.")

    add_input(tree, "Магнит_диаметр_мм", "NodeSocketFloat", default=10.0, min_value=8.0, max_value=12.0)
    add_input(tree, "Магнит_глубина_мм", "NodeSocketFloat", default=3.0, min_value=2.0, max_value=6.0)
    add_input(tree, "Магнит_зазор_мм", "NodeSocketFloat", default=0.2, min_value=0.0, max_value=0.5)
    add_input(tree, "Магнит1_высота_доля_от_колена", "NodeSocketFloat", default=0.25,
              min_value=0.0, max_value=1.0)
    add_input(tree, "Магнит2_высота_доля_от_колена", "NodeSocketFloat", default=0.70,
              min_value=0.0, max_value=1.0)
    add_input(tree, "Закладная_радиус_мм", "NodeSocketFloat", default=9.0, min_value=5.0, max_value=20.0,
              description="Радиус закладной у стены (широкий торец male-конуса).")
    add_input(tree, "Закладная_длина_мм", "NodeSocketFloat", default=14.0, min_value=6.0, max_value=30.0,
              description="Длина закладной внутрь от стены.")
    add_input(tree, "Закладная_кончик_радиус_мм", "NodeSocketFloat", default=6.0, min_value=3.0, max_value=15.0)
    add_input(tree, "Закладная_посадка_зазор_мм", "NodeSocketFloat", default=0.3, min_value=0.1, max_value=1.0)
    add_input(tree, "Зенковка_радиус_мм", "NodeSocketFloat", default=6.5, min_value=3.0, max_value=15.0)
    add_input(tree, "Зенковка_глубина_мм", "NodeSocketFloat", default=1.0, min_value=0.2, max_value=5.0)
    add_input(tree, "Закладная_ребро_мм", "NodeSocketFloat", default=2.0, min_value=0.0, max_value=6.0,
              description="Толщина ребра жёсткости закладной магнита (0 = без ребра).")
    add_input(tree, "Закладная_нахлёст_мм", "NodeSocketFloat", default=1.5, min_value=0.0, max_value=4.0,
              description="Нахлёст закладной в стену (надёжность Boolean на кривой поверхности).")
    add_input(tree, "Короткая_накладка_порог_мм", "NodeSocketFloat", default=280.0,
              min_value=150.0, max_value=400.0,
              description="Если Длина_сегмента (из Группы 1/2) меньше этого порога - "
                           "на каждую половину ставится всего 1 закладная магнита "
                           "(вместо 2 швов x 2 высоты = 4).")
    add_input(tree, "Длина_сегмента_мм", "NodeSocketFloat", default=350.0, min_value=150.0, max_value=500.0,
              description="То же, что в Группе 1/2 - для решения 'короткая ли накладка'.")

    add_output(tree, "VIS_Вместе", "NodeSocketGeometry")
    add_output(tree, "Перед", "NodeSocketGeometry")
    add_output(tree, "Зад", "NodeSocketGeometry")
    add_output(tree, "Провер_ВСЕ_OK", "NodeSocketBool")
    add_output(tree, "Провер_Отчёт", "NodeSocketString")
    add_output(tree, "Провер_Зазор_до_трубки_OK", "NodeSocketBool",
               "True, если ни одна закладная магнита не подходит к оси трубки ближе, "
               "чем Трубка_диаметр/2 + запас.")

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
    tree.links.new(GI("Стойка_радиус_мм"), c1.inputs["Стойка_радиус_мм"])
    tree.links.new(GI("Хомут_зазор_под_шайбы_мм"), c1.inputs["Хомут_зазор_под_шайбы_мм"])

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
    tree.links.new(GI("Стойка_радиус_мм"), c2.inputs["Стойка_радиус_мм"])
    tree.links.new(GI("Хомут_зазор_под_шайбы_мм"), c2.inputs["Хомут_зазор_под_шайбы_мм"])

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

        # -- тот же исходный индекс (row*M+col) во 'Профиль_точки', чтобы
        # прочитать 'dir' В ТОЙ ЖЕ точке (сэмплер не пробрасывает 'dir',
        # только Position - поэтому индекс считаем заново, напрямую).
        flat_mul = add_node(tree, "ShaderNodeMath", num + "fm", "row*Точек_в_кольце",
                             x, y - 260, operation='MULTIPLY')
        link(tree, row_i_node, "Integer", flat_mul, "Value")
        tree.links.new(GI("Точек_в_кольце"), in_sock(flat_mul, "Value_001"))
        flat_add = add_node(tree, "ShaderNodeMath", num + "fa", "+col = flat_index",
                             x + 140, y - 260, operation='ADD')
        link(tree, flat_mul, "Value", flat_add, "Value")
        if isinstance(col_val, int):
            in_sock(flat_add, "Value_001").default_value = float(col_val)
        else:
            tree.links.new(col_val.outputs["Integer"], in_sock(flat_add, "Value_001"))
        flat_i = add_node(tree, "FunctionNodeFloatToInt", num + "fi", "-> Int", x + 280, y - 260)
        link(tree, flat_add, "Value", flat_i, "Float")

        diridx = add_node(tree, "GeometryNodeSampleIndex", num + "d", "'dir' точки шва",
                           x + 420, y - 260, data_type='FLOAT_VECTOR')
        tree.links.new(GI("Профиль_точки"), in_sock(diridx, "Geometry"))
        dirattr = named_attr(tree, num + "da", "'dir' атрибут", x, y - 400, "dir", 'FLOAT_VECTOR')
        link(tree, dirattr, "Attribute_Vector", diridx, "Value_Vector")
        link(tree, flat_i, "Integer", diridx, "Index")

        return [s, idx, posn, flat_mul, flat_add, flat_i, diridx, dirattr], idx, diridx

    seamA_h1_nodes, seamA_h1, seamA_h1_dir = sample_seam("4.08", "шов1(col0) высота1", 400, 900, row1_i, 0)
    seamB_h1_nodes, seamB_h1, seamB_h1_dir = sample_seam("4.09", "шов2(col M/2) высота1", 400, 700, row1_i, mhalf_i)
    seamA_h2_nodes, seamA_h2, seamA_h2_dir = sample_seam("4.10", "шов1(col0) высота2", 400, 500, row2_i, 0)
    seamB_h2_nodes, seamB_h2, seamB_h2_dir = sample_seam("4.11", "шов2(col M/2) высота2", 400, 300, row2_i, mhalf_i)

    frame2 = make_frame(
        tree, "2. ПОЗИЦИИ 4 МАГНИТНЫХ ТОЧЕК (2 шва x 2 высоты), сэмплировано с Профиль_точки",
        [mhalf, mhalf_i, nm1] + row1_nodes + row2_nodes +
        seamA_h1_nodes + seamB_h1_nodes + seamA_h2_nodes + seamB_h2_nodes)

    # ------------------------------------------------------------------
    # 3. КОРОТКАЯ НАКЛАДКА? (по длине сегмента) - если да, из 4 позиций
    # на половину оставляем только одну (шов1/высота1), остальные 3
    # "гасим" (заменяем на пустую геометрию Switch'ем), не удаляя узлы -
    # см. п.6 правки: "при малой длине... достаточно по 1 закладной".
    # ------------------------------------------------------------------
    is_short = add_node(tree, "FunctionNodeCompare", "4.13s",
                         "Длина_сегмента < Короткая_накладка_порог ?", 400, -350,
                         data_type='FLOAT', operation='LESS_THAN')
    tree.links.new(GI("Длина_сегмента_мм"), in_sock(is_short, "A"))
    tree.links.new(GI("Короткая_накладка_порог_мм"), in_sock(is_short, "B"))
    keep_extra = add_node(tree, "FunctionNodeBooleanMath", "4.13k",
                           "оставить доп.позиции? = НЕ короткая", 660, -350, operation='NOT')
    link(tree, is_short, "Result", keep_extra, "Boolean")
    empty_geo = add_node(tree, "GeometryNodeMeshCube", "4.13e", "пусто (для погашенных позиций)",
                          400, -500)
    in_sock(empty_geo, "Size").default_value = (0.0, 0.0, 0.0)

    frame3s = make_frame(tree, "3. КОРОТКАЯ НАКЛАДКА? (гасит 3 из 4 позиций магнитов на половину)",
                          [is_short, keep_extra, empty_geo])

    # ------------------------------------------------------------------
    # 3b. ЗАКЛАДНЫЕ МАГНИТОВ: Перед=female (воронка+магнит на дне),
    # Зад=male (усечённый конус+зенковка на торце) - NK.4e_Закладная_магнита
    # ------------------------------------------------------------------
    def magnet_insert(num, label, x, y, pos_node, dir_node, male_val, gate_extra):
        g = _grp(tree, magnet_tree, num, label, x, y)
        tree.links.new(out_sock(pos_node, "Value_Vector"), g.inputs["Позиция"])
        tree.links.new(out_sock(dir_node, "Value_Vector"), g.inputs["Dir"])
        g.inputs["Male"].default_value = male_val
        tree.links.new(GI("Закладная_радиус_мм"), g.inputs["Радиус_бобышки_мм"])
        tree.links.new(GI("Закладная_длина_мм"), g.inputs["Длина_бобышки_мм"])
        tree.links.new(GI("Закладная_кончик_радиус_мм"), g.inputs["Кончик_радиус_мм"])
        tree.links.new(GI("Закладная_посадка_зазор_мм"), g.inputs["Посадка_зазор_мм"])
        tree.links.new(GI("Магнит_диаметр_мм"), g.inputs["Магнит_диаметр_мм"])
        tree.links.new(GI("Магнит_глубина_мм"), g.inputs["Магнит_глубина_мм"])
        tree.links.new(GI("Магнит_зазор_мм"), g.inputs["Магнит_зазор_мм"])
        tree.links.new(GI("Зенковка_радиус_мм"), g.inputs["Зенковка_радиус_мм"])
        tree.links.new(GI("Зенковка_глубина_мм"), g.inputs["Зенковка_глубина_мм"])
        tree.links.new(GI("Закладная_ребро_мм"), g.inputs["Ребро_толщина_мм"])
        tree.links.new(GI("Закладная_нахлёст_мм"), g.inputs["Стена_нахлёст_мм"])

        if not gate_extra:
            return g.outputs["Бобышка"], g.outputs["Отверстие"]

        boss_sw = add_node(tree, "GeometryNodeSwitch", num + "gb", "гасить? (бобышка)",
                            x + 300, y, input_type='GEOMETRY')
        link(tree, keep_extra, "Boolean", boss_sw, "Switch_001")
        tree.links.new(empty_geo.outputs["Mesh"], in_sock(boss_sw, "False_006"))
        tree.links.new(g.outputs["Бобышка"], in_sock(boss_sw, "True_006"))
        hole_sw = add_node(tree, "GeometryNodeSwitch", num + "gh", "гасить? (отверстие)",
                            x + 300, y - 150, input_type='GEOMETRY')
        link(tree, keep_extra, "Boolean", hole_sw, "Switch_001")
        tree.links.new(empty_geo.outputs["Mesh"], in_sock(hole_sw, "False_006"))
        tree.links.new(g.outputs["Отверстие"], in_sock(hole_sw, "True_006"))
        return out_sock(boss_sw, "Output_006"), out_sock(hole_sw, "Output_006")

    mag_front_1_b, mag_front_1_h = magnet_insert("4.14", "магнит перед(female): шов1 высота1",
                                                  1300, 900, seamA_h1, seamA_h1_dir, 0.0, False)
    mag_front_2_b, mag_front_2_h = magnet_insert("4.15", "магнит перед(female): шов2 высота1",
                                                  1300, 750, seamB_h1, seamB_h1_dir, 0.0, True)
    mag_front_3_b, mag_front_3_h = magnet_insert("4.16", "магнит перед(female): шов1 высота2",
                                                  1300, 600, seamA_h2, seamA_h2_dir, 0.0, True)
    mag_front_4_b, mag_front_4_h = magnet_insert("4.17", "магнит перед(female): шов2 высота2",
                                                  1300, 450, seamB_h2, seamB_h2_dir, 0.0, True)

    mag_back_1_b, mag_back_1_h = magnet_insert("4.18", "магнит зад(male): шов1 высота1",
                                                1300, 250, seamA_h1, seamA_h1_dir, 1.0, False)
    mag_back_2_b, mag_back_2_h = magnet_insert("4.19", "магнит зад(male): шов2 высота1",
                                                1300, 100, seamB_h1, seamB_h1_dir, 1.0, True)
    mag_back_3_b, mag_back_3_h = magnet_insert("4.20", "магнит зад(male): шов1 высота2",
                                                1300, -50, seamA_h2, seamA_h2_dir, 1.0, True)
    mag_back_4_b, mag_back_4_h = magnet_insert("4.21", "магнит зад(male): шов2 высота2",
                                                1300, -200, seamB_h2, seamB_h2_dir, 1.0, True)

    frame3b = make_frame(
        tree, "3b. 8 ЗАКЛАДНЫХ МАГНИТОВ (4 female на Перед, 4 male на Зад; "
        "3 из 4 на половину гасятся при короткой накладке)",
        [mag_front_1_b.node, mag_front_2_b.node, mag_front_3_b.node, mag_front_4_b.node,
         mag_back_1_b.node, mag_back_2_b.node, mag_back_3_b.node, mag_back_4_b.node])

    # -- сборка: перед --
    jbf = add_node(tree, "GeometryNodeJoinGeometry", "4.22", "бобышки магнитов (перед)", 1700, 750)
    for s in (mag_front_1_b, mag_front_2_b, mag_front_3_b, mag_front_4_b):
        tree.links.new(s, jbf.inputs["Geometry"])

    uf = add_node(tree, "GeometryNodeMeshBoolean", "4.23",
                   "Перед(хомуты) + бобышки магнитов", 2000, 750, operation='UNION')
    tree.links.new(c2.outputs["Перед"], in_sock(uf, "Mesh 2"))
    tree.links.new(jbf.outputs["Geometry"], in_sock(uf, "Mesh 2"))

    jhf = add_node(tree, "GeometryNodeJoinGeometry", "4.24", "гнёзда магнитов (перед)", 1700, 600)
    for s in (mag_front_1_h, mag_front_2_h, mag_front_3_h, mag_front_4_h):
        tree.links.new(s, jhf.inputs["Geometry"])

    df = add_node(tree, "GeometryNodeMeshBoolean", "4.25",
                   "минус гнёзда -> Перед (итог)", 2300, 750, operation='DIFFERENCE')
    tree.links.new(uf.outputs["Mesh"], in_sock(df, "Mesh 1"))
    tree.links.new(jhf.outputs["Geometry"], in_sock(df, "Mesh 2"))

    # -- сборка: зад --
    jbb = add_node(tree, "GeometryNodeJoinGeometry", "4.26", "бобышки магнитов (зад)", 1700, 200)
    for s in (mag_back_1_b, mag_back_2_b, mag_back_3_b, mag_back_4_b):
        tree.links.new(s, jbb.inputs["Geometry"])

    ub = add_node(tree, "GeometryNodeMeshBoolean", "4.27",
                   "Зад(хомуты) + бобышки магнитов", 2000, 200, operation='UNION')
    tree.links.new(c2.outputs["Зад"], in_sock(ub, "Mesh 2"))
    tree.links.new(jbb.outputs["Geometry"], in_sock(ub, "Mesh 2"))

    jhb = add_node(tree, "GeometryNodeJoinGeometry", "4.28", "гнёзда магнитов (зад)", 1700, 50)
    for s in (mag_back_1_h, mag_back_2_h, mag_back_3_h, mag_back_4_h):
        tree.links.new(s, jhb.inputs["Geometry"])

    db = add_node(tree, "GeometryNodeMeshBoolean", "4.29",
                   "минус гнёзда -> Зад (итог)", 2300, 200, operation='DIFFERENCE')
    tree.links.new(ub.outputs["Mesh"], in_sock(db, "Mesh 1"))
    tree.links.new(jhb.outputs["Geometry"], in_sock(db, "Mesh 2"))

    frame4 = make_frame(
        tree, "4. СБОРКА: МАГНИТЫ UNION+DIFFERENCE (по образцу Группы 4a)",
        [jbf, uf, jhf, df, jbb, ub, jhb, db])

    # ------------------------------------------------------------------
    # 4b. ПРОВЕРКА: закладные магнитов не подходят к оси трубки ближе,
    # чем её радиус + запас (см. п. "не должны мешать проходу трубки").
    # Для каждой из 4 уникальных позиций считаем расстояние от точки на
    # глубине Закладная_длина_мм (самой внутренней) до прямой A-B.
    # ------------------------------------------------------------------
    def dist_to_axis_line(num, x, y, pos_node, dir_node):
        neg_len = add_node(tree, "ShaderNodeMath", num + "nl", "-Закладная_длина_мм",
                            x - 260, y - 100, operation='MULTIPLY')
        tree.links.new(GI("Закладная_длина_мм"), in_sock(neg_len, "Value"))
        in_sock(neg_len, "Value_001").default_value = -1.0
        depth_off = add_node(tree, "ShaderNodeVectorMath", num + "do",
                              "-Dir*Закладная_длина_мм (самая внутренняя точка закладной)",
                              x, y, operation='SCALE')
        tree.links.new(out_sock(dir_node, "Value_Vector"), in_sock(depth_off, "Vector"))
        link(tree, neg_len, "Value", depth_off, "Scale")
        tip = add_node(tree, "ShaderNodeVectorMath", num + "tp", "самая внутренняя точка закладной",
                        x + 260, y, operation='ADD')
        tree.links.new(out_sock(pos_node, "Value_Vector"), in_sock(tip, "Vector"))
        link(tree, depth_off, "Vector", tip, "Vector_001")

        # Ближайшая точка на отрезке A-B считается вручную (проекция):
        ab = add_node(tree, "ShaderNodeVectorMath", num + "ab", "AB = B-A", x, y - 300, operation='SUBTRACT')
        tree.links.new(GI("Точка_B"), in_sock(ab, "Vector"))
        tree.links.new(GI("Точка_A"), in_sock(ab, "Vector_001"))
        ap = add_node(tree, "ShaderNodeVectorMath", num + "ap", "AP = tip-A", x, y - 450, operation='SUBTRACT')
        link(tree, tip, "Vector", ap, "Vector")
        tree.links.new(GI("Точка_A"), in_sock(ap, "Vector_001"))
        dot_ap_ab = add_node(tree, "ShaderNodeVectorMath", num + "dpa", "AP.AB", x + 260, y - 380,
                              operation='DOT_PRODUCT')
        link(tree, ap, "Vector", dot_ap_ab, "Vector")
        link(tree, ab, "Vector", dot_ap_ab, "Vector_001")
        dot_ab_ab = add_node(tree, "ShaderNodeVectorMath", num + "dbb", "AB.AB", x + 260, y - 520,
                              operation='DOT_PRODUCT')
        link(tree, ab, "Vector", dot_ab_ab, "Vector")
        link(tree, ab, "Vector", dot_ab_ab, "Vector_001")
        t_raw = add_node(tree, "ShaderNodeMath", num + "tr", "t = AP.AB / AB.AB", x + 520, y - 450,
                          operation='DIVIDE')
        link(tree, dot_ap_ab, "Value", t_raw, "Value")
        link(tree, dot_ab_ab, "Value", t_raw, "Value_001")
        t_clamp = add_node(tree, "ShaderNodeClamp", num + "tc", "t зажат в 0..1", x + 780, y - 450)
        link(tree, t_raw, "Value", t_clamp, "Value")
        in_sock(t_clamp, "Min").default_value = 0.0
        in_sock(t_clamp, "Max").default_value = 1.0
        ab_t = add_node(tree, "ShaderNodeVectorMath", num + "abt", "AB*t", x + 1040, y - 300,
                         operation='SCALE')
        link(tree, ab, "Vector", ab_t, "Vector")
        link(tree, t_clamp, "Result", ab_t, "Scale")
        nearest = add_node(tree, "ShaderNodeVectorMath", num + "nr", "ближайшая точка = A + AB*t",
                            x + 1300, y - 300, operation='ADD')
        tree.links.new(GI("Точка_A"), in_sock(nearest, "Vector"))
        link(tree, ab_t, "Vector", nearest, "Vector_001")
        dist = add_node(tree, "ShaderNodeVectorMath", num + "ds", "расстояние(tip, ближайшая)",
                         x + 1560, y - 300, operation='DISTANCE')
        link(tree, tip, "Vector", dist, "Vector")
        link(tree, nearest, "Vector", dist, "Vector_001")
        return [depth_off, neg_len, tip, ab, ap, dot_ap_ab, dot_ab_ab, t_raw, t_clamp,
                ab_t, nearest, dist], dist

    clr_nodes1, clr1 = dist_to_axis_line("4.50", 400, -700, seamA_h1, seamA_h1_dir)
    clr_nodes2, clr2 = dist_to_axis_line("4.51", 400, -1000, seamB_h1, seamB_h1_dir)
    clr_nodes3, clr3 = dist_to_axis_line("4.52", 400, -1300, seamA_h2, seamA_h2_dir)
    clr_nodes4, clr4 = dist_to_axis_line("4.53", 400, -1600, seamB_h2, seamB_h2_dir)

    min12 = add_node(tree, "ShaderNodeMath", "4.54a", "min(d1,d2)", 2400, -700, operation='MINIMUM')
    link(tree, clr1, "Value", min12, "Value")
    link(tree, clr2, "Value", min12, "Value_001")
    min34 = add_node(tree, "ShaderNodeMath", "4.54b", "min(d3,d4)", 2400, -900, operation='MINIMUM')
    link(tree, clr3, "Value", min34, "Value")
    link(tree, clr4, "Value", min34, "Value_001")
    min_dist = add_node(tree, "ShaderNodeMath", "4.54c", "min_расст = min(min12,min34)",
                         2660, -800, operation='MINIMUM')
    link(tree, min12, "Value", min_dist, "Value")
    link(tree, min34, "Value", min_dist, "Value_001")

    tube_r = add_node(tree, "ShaderNodeMath", "4.55", "R_трубки = Трубка_диаметр/2",
                       2400, -1050, operation='DIVIDE')
    tree.links.new(GI("Трубка_диаметр_мм"), in_sock(tube_r, "Value"))
    in_sock(tube_r, "Value_001").default_value = 2.0

    clr_ok = add_node(tree, "FunctionNodeCompare", "4.56",
                       "min_расст >= R_трубки ? (закладные не мешают трубке)",
                       2920, -900, data_type='FLOAT', operation='GREATER_EQUAL')
    link(tree, min_dist, "Value", clr_ok, "A")
    link(tree, tube_r, "Value", clr_ok, "B")

    frame4b = make_frame(
        tree, "4b. ПРОВЕРКА: закладные магнитов не мешают проходу трубки (>= R_трубки от оси A-B)",
        clr_nodes1 + clr_nodes2 + clr_nodes3 + clr_nodes4 +
        [min12, min34, min_dist, tube_r, clr_ok])

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
    tree.links.new(clr_ok.outputs["Result"], gout.inputs["Провер_Зазор_до_трубки_OK"])

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
    magnet_tree = build_magnet_insert()
    if sampler_tree is None:
        sampler_tree = build_sampler()
    inserts_tree = build_inserts(boss_tree, clamp_tree, sampler_tree, magnet_tree)
    return inserts_tree


if __name__ == "__main__":
    inserts_tree = build_all_groups()
    print("OK: '%s' собрана, узлов=%d" % (INSERTS_NAME, len(inserts_tree.nodes)))
