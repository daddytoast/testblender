# -*- coding: utf-8 -*-
"""
ГРУППА 5 — «NK.5_Печать» (Split for printer bed / print orientation)
========================================================================
Последняя группа: режет переднюю/заднюю половину (уже с закладными из
Группы 4) на печатаемые сегменты, если высота накладки превышает
рабочую зону принтера, и делает стык менее заметным наклоном плоскости
разреза.

Состоит из 2 вложенных groups:

  NK.5b_Крышка_среза - переиспользуемый "капсюль": берёт меш С ОТКРЫТЫМИ
      рёбрами после булевого разреза (Edge Neighbors != 2) и закрывает
      их плоской "крышкой" через Mesh to Curve -> Fill Curve (режим
      NGONS корректно обрабатывает КОЛЬЦЕВОЕ сечение - и внешний, и
      внутренний контур одновременно, оставляя дырку внутри кольца,
      а не заливая её). Проверено отдельным тестом на полой трубе
      перед сборкой: 0 открытых рёбер, положительный объём.

  NK.5a_Разрез_с_крышкой - режет геометрию ОДНОЙ плоскостью (точка +
      нормаль, необязательно горизонтальная - см. "Наклон_шва_град")
      на 2 части через Boolean INTERSECT с гигантским кубом-
      полупространством (тот же приём, что и разрез перед/зад в
      Группе 3/4), и закрывает обе получившиеся части через NK.5b.

  NK.5_Печать - верхний уровень: считает, сколько сегментов нужно
      (по высоте A->B и рабочей зоне принтера), режет Перед и Зад
      (максимум на 2 сегмента в этой версии - см. "Известные
      упрощения" в документации).

Печать по умолчанию рассчитана на Elegoo Centauri Carbon (рабочая
зона ~256x256x256 мм - см. docs/05_group5_print.md, уточните под
свой принтер).

Запуск:
    blender --background --python scripts/build_group5_print.py
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
from build_group3_shell import _grp

CAP_NAME = "NK.5b_Крышка_среза"
CUT_NAME = "NK.5a_Разрез_с_крышкой"
PRINT_NAME = "NK.5_Печать"


# ----------------------------------------------------------------------
# 1) NK.5b_Крышка_среза
# ----------------------------------------------------------------------
def build_cap():
    tree = new_group(CAP_NAME)
    add_input(tree, "Mesh", "NodeSocketGeometry",
              description="Меш с открытыми (граничными) рёбрами после Boolean-разреза.")
    add_output(tree, "Mesh", "NodeSocketGeometry", "Тот же меш с закрытыми крышкой рёбрами.")

    gin = tree.nodes.new("NodeGroupInput")
    gin.name = "5b.01 Вход"; gin.label = "5b.01 Входные параметры"; gin.location = (-300, 0)
    gout = tree.nodes.new("NodeGroupOutput")
    gout.name = "5b.99 Выход"; gout.label = "5b.99 Выход"; gout.location = (1600, 0)

    n02 = add_node(tree, "GeometryNodeInputMeshEdgeNeighbors", "5b.02",
                    "Кол-во граней на каждом ребре", 0, -150)

    n03 = add_node(tree, "FunctionNodeCompare", "5b.03",
                    "ребро открытое? (соседей != 2)", 260, -150,
                    data_type='INT', operation='NOT_EQUAL')
    link(tree, n02, "Face Count", n03, "A_INT")
    in_sock(n03, "B_INT").default_value = 2

    n04 = add_node(tree, "GeometryNodeMeshToCurve", "5b.04",
                    "Открытые рёбра -> контур(ы)-кривая(ые)", 520, 100)
    tree.links.new(gin.outputs["Mesh"], in_sock(n04, "Mesh"))
    link(tree, n03, "Result", n04, "Selection")

    n05 = add_node(tree, "GeometryNodeFillCurve", "5b.05",
                    "Залить контур(ы) плоской крышкой (кольцо остаётся "
                    "с дыркой - учтён и внешний, и внутренний контур)",
                    780, 100, mode='NGONS')
    link(tree, n04, "Curve", n05, "Curve")

    n06 = add_node(tree, "GeometryNodeJoinGeometry", "5b.06",
                    "Исходный меш + крышка", 1040, 0)
    tree.links.new(gin.outputs["Mesh"], n06.inputs["Geometry"])
    tree.links.new(n05.outputs["Mesh"], n06.inputs["Geometry"])

    n07 = add_node(tree, "GeometryNodeMergeByDistance", "5b.07",
                    "Сварить крышку с краем меша (0.01мм)", 1300, 0)
    link(tree, n06, "Geometry", n07, "Geometry")
    in_sock(n07, "Distance").default_value = 0.01

    tree.links.new(n07.outputs["Geometry"], gout.inputs["Mesh"])

    frame1 = make_frame(tree, "КРЫШКА СРЕЗА (Edge Neighbors -> Mesh to Curve -> Fill Curve -> Join -> Merge)",
                         [n02, n03, n04, n05, n06, n07])
    return tree


# ----------------------------------------------------------------------
# 2) NK.5a_Разрез_с_крышкой
# ----------------------------------------------------------------------
def build_cut(cap_tree):
    tree = new_group(CUT_NAME)
    add_input(tree, "Geometry", "NodeSocketGeometry")
    add_input(tree, "Точка_на_плоскости", "NodeSocketVector")
    add_input(tree, "Нормаль_плоскости", "NodeSocketVector", default=(0.0, 0.0, 1.0))
    add_output(tree, "Часть_A", "NodeSocketGeometry", "Сторона, куда указывает нормаль.")
    add_output(tree, "Часть_B", "NodeSocketGeometry", "Противоположная сторона.")

    gin = tree.nodes.new("NodeGroupInput")
    gin.name = "5a.01 Вход"; gin.label = "5a.01 Входные параметры"; gin.location = (-400, 0)
    gout = tree.nodes.new("NodeGroupOutput")
    gout.name = "5a.99 Выход"; gout.label = "5a.99 Выход"; gout.location = (2200, 0)

    def GI(name):
        return gin.outputs[name]

    n02 = add_node(tree, "ShaderNodeVectorMath", "5a.02",
                    "единичная нормаль плоскости", 0, -100, operation='NORMALIZE')
    tree.links.new(GI("Нормаль_плоскости"), in_sock(n02, "Vector"))

    n03 = add_node(tree, "FunctionNodeAlignEulerToVector", "5a.03",
                    "Euler: локальный Z -> нормаль (для поворота куба-разреза)",
                    260, -100)
    n03.axis = 'Z'
    link(tree, n02, "Vector", n03, "Vector")

    n04 = add_node(tree, "GeometryNodeMeshCube", "5a.04",
                    "куб-полупространство (огромный)", 0, 200)
    in_sock(n04, "Size").default_value = (4000.0, 4000.0, 4000.0)

    n05 = add_node(tree, "ShaderNodeVectorMath", "5a.05",
                    "смещение = нормаль * 2000мм (половина куба)",
                    260, 250, operation='SCALE')
    link(tree, n02, "Vector", n05, "Vector")
    in_sock(n05, "Scale").default_value = 2000.0

    n06 = add_node(tree, "ShaderNodeVectorMath", "5a.06",
                    "центр куба A = Точка + смещение", 520, 300, operation='ADD')
    tree.links.new(GI("Точка_на_плоскости"), in_sock(n06, "Vector"))
    link(tree, n05, "Vector", n06, "Vector_001")

    n07 = add_node(tree, "ShaderNodeVectorMath", "5a.07",
                    "центр куба B = Точка - смещение", 520, 100, operation='SUBTRACT')
    tree.links.new(GI("Точка_на_плоскости"), in_sock(n07, "Vector"))
    link(tree, n05, "Vector", n07, "Vector_001")

    n08 = add_node(tree, "GeometryNodeTransform", "5a.08",
                    "куб A на место (поворот+сдвиг)", 780, 300)
    link(tree, n04, "Mesh", n08, "Geometry")
    link(tree, n03, "Rotation", n08, "Rotation")
    link(tree, n06, "Vector", n08, "Translation")

    n09 = add_node(tree, "GeometryNodeTransform", "5a.09",
                    "куб B на место (поворот+сдвиг)", 780, 100)
    link(tree, n04, "Mesh", n09, "Geometry")
    link(tree, n03, "Rotation", n09, "Rotation")
    link(tree, n07, "Vector", n09, "Translation")

    frame1 = make_frame(tree, "1. ДВА КУБА-ПОЛУПРОСТРАНСТВА (по обе стороны от плоскости)",
                         [n02, n03, n04, n05, n06, n07, n08, n09])

    n10 = add_node(tree, "GeometryNodeMeshBoolean", "5a.10",
                    "Часть A (сторона нормали) = Geometry INTERSECT куб A",
                    1080, 250, operation='INTERSECT')
    tree.links.new(GI("Geometry"), in_sock(n10, "Mesh 2"))
    tree.links.new(n08.outputs["Geometry"], in_sock(n10, "Mesh 2"))

    n11 = add_node(tree, "GeometryNodeMeshBoolean", "5a.11",
                    "Часть B (противоположная) = Geometry INTERSECT куб B",
                    1080, 50, operation='INTERSECT')
    tree.links.new(GI("Geometry"), in_sock(n11, "Mesh 2"))
    tree.links.new(n09.outputs["Geometry"], in_sock(n11, "Mesh 2"))

    n12 = _grp(tree, cap_tree, "5a.12", "Закрыть срез части A", 1400, 250)
    tree.links.new(n10.outputs["Mesh"], n12.inputs["Mesh"])

    n13 = _grp(tree, cap_tree, "5a.13", "Закрыть срез части B", 1400, 50)
    tree.links.new(n11.outputs["Mesh"], n13.inputs["Mesh"])

    frame2 = make_frame(tree, "2. РАЗРЕЗ (Boolean INTERSECT, оба операнда в Mesh 2) + КРЫШКИ",
                         [n10, n11, n12, n13])

    tree.links.new(n12.outputs["Mesh"], gout.inputs["Часть_A"])
    tree.links.new(n13.outputs["Mesh"], gout.inputs["Часть_B"])
    return tree


# ----------------------------------------------------------------------
# 3) NK.5_Печать (верхний уровень)
# ----------------------------------------------------------------------
def build_print(cut_tree):
    tree = new_group(PRINT_NAME)
    add_input(tree, "Перед", "NodeSocketGeometry")
    add_input(tree, "Зад", "NodeSocketGeometry")
    add_input(tree, "Точка_A", "NodeSocketVector")
    add_input(tree, "Точка_B", "NodeSocketVector")
    add_input(tree, "Печать_X_мм", "NodeSocketFloat", default=256.0, min_value=150.0, max_value=400.0,
              description="Рабочая зона принтера по X (см. docs - Elegoo Centauri Carbon).")
    add_input(tree, "Печать_Y_мм", "NodeSocketFloat", default=256.0, min_value=150.0, max_value=400.0)
    add_input(tree, "Печать_Z_мм", "NodeSocketFloat", default=256.0, min_value=150.0, max_value=400.0)
    add_input(tree, "Зазор_реза_мм", "NodeSocketFloat", default=5.0, min_value=0.0, max_value=15.0,
              description="Запас, чтобы сегмент точно поместился в рабочую зону.")
    add_input(tree, "Наклон_шва_град", "NodeSocketFloat", default=12.0, min_value=0.0, max_value=25.0,
              description="Наклон плоскости разреза от горизонтали - делает стык менее заметным "
                           "и увеличивает площадь склейки.")
    add_input(tree, "Паз_гребня_вкл", "NodeSocketFloat", default=1.0, min_value=0.0, max_value=1.0,
              description="1 = добавить паз-шип на стыке ПЕРЕДНЕЙ детали, в районе гребня "
                           "большеберцовой кости (шип снизу входит в паз сверху - позиционирует "
                           "и прячет линию стыка). 0 = отключить (только Перед; на Зад не влияет - "
                           "гребень есть только спереди).")
    add_input(tree, "Паз_гребня_ширина_мм", "NodeSocketFloat", default=16.0,
              min_value=6.0, max_value=30.0, description="Ширина шипа (вбок, по X).")
    add_input(tree, "Паз_гребня_глубина_мм", "NodeSocketFloat", default=8.0,
              min_value=4.0, max_value=20.0, description="Глубина шипа (перед-зад, по Y).")
    add_input(tree, "Паз_гребня_выступ_мм", "NodeSocketFloat", default=4.0,
              min_value=1.5, max_value=10.0, description="Насколько шип выступает от плоскости "
                           "разреза в верхнюю деталь (и на столько же паз врезается в неё).")
    add_input(tree, "Паз_гребня_зазор_мм", "NodeSocketFloat", default=0.3,
              min_value=0.0, max_value=1.0, description="Зазор паза относительно шипа (посадка).")

    add_output(tree, "VIS_Вместе", "NodeSocketGeometry")
    add_output(tree, "Перед_Низ", "NodeSocketGeometry")
    add_output(tree, "Перед_Верх", "NodeSocketGeometry", "Пусто, если сегмент не нужен (накладка помещается целиком).")
    add_output(tree, "Зад_Низ", "NodeSocketGeometry")
    add_output(tree, "Зад_Верх", "NodeSocketGeometry")
    add_output(tree, "Число_сегментов", "NodeSocketInt")
    add_output(tree, "Провер_ВСЕ_OK", "NodeSocketBool")
    add_output(tree, "Провер_Отчёт", "NodeSocketString")

    gin = tree.nodes.new("NodeGroupInput")
    gin.name = "5.01 Вход"; gin.label = "5.01 Входные параметры"; gin.location = (-500, 300)
    gout = tree.nodes.new("NodeGroupOutput")
    gout.name = "5.99 Выход"; gout.label = "5.99 Выход"; gout.location = (3200, 300)

    def GI(name):
        return gin.outputs[name]

    # ------------------------------------------------------------------
    # 1. СКОЛЬКО СЕГМЕНТОВ НУЖНО (макс. 2 в этой версии)
    # ------------------------------------------------------------------
    n02 = add_node(tree, "ShaderNodeVectorMath", "5.02",
                    "H = расстояние Точка_A - Точка_B", 0, 500, operation='DISTANCE')
    tree.links.new(GI("Точка_A"), in_sock(n02, "Vector"))
    tree.links.new(GI("Точка_B"), in_sock(n02, "Vector_001"))

    n03 = add_node(tree, "ShaderNodeMath", "5.03",
                    "usable = Печать_Z_мм - Зазор_реза_мм", 0, 350, operation='SUBTRACT')
    tree.links.new(GI("Печать_Z_мм"), in_sock(n03, "Value"))
    tree.links.new(GI("Зазор_реза_мм"), in_sock(n03, "Value_001"))

    n04 = add_node(tree, "ShaderNodeMath", "5.04", "H / usable", 260, 420, operation='DIVIDE')
    link(tree, n02, "Value", n04, "Value")
    link(tree, n03, "Value", n04, "Value_001")

    n05 = add_node(tree, "ShaderNodeMath", "5.05", "ceil(H/usable)", 520, 420, operation='CEIL')
    link(tree, n04, "Value", n05, "Value")

    n06 = add_node(tree, "ShaderNodeMath", "5.06", "не больше 2 (макс. в этой версии)",
                    780, 420, operation='MINIMUM')
    link(tree, n05, "Value", n06, "Value")
    in_sock(n06, "Value_001").default_value = 2.0

    n07 = add_node(tree, "ShaderNodeMath", "5.07", "не меньше 1", 1040, 420, operation='MAXIMUM')
    link(tree, n06, "Value", n07, "Value")
    in_sock(n07, "Value_001").default_value = 1.0

    n08 = add_node(tree, "FunctionNodeFloatToInt", "5.08", "Число_сегментов -> Int", 1300, 420)
    link(tree, n07, "Value", n08, "Float")

    n09 = add_node(tree, "FunctionNodeCompare", "5.09", "нужен разрез? (сегментов >= 2)",
                    1300, 250, data_type='INT', operation='GREATER_EQUAL')
    link(tree, n08, "Integer", n09, "A_INT")
    in_sock(n09, "B_INT").default_value = 2

    frame1 = make_frame(tree, "1. СКОЛЬКО СЕГМЕНТОВ НУЖНО (H / рабочая зона принтера, макс. 2)",
                         [n02, n03, n04, n05, n06, n07, n08, n09])

    # ------------------------------------------------------------------
    # 2. ПЛОСКОСТЬ РАЗРЕЗА: высота (посередине) + наклон
    # ------------------------------------------------------------------
    n10 = add_node(tree, "ShaderNodeMath", "5.10", "высота разреза = H / Число_сегментов",
                    0, 100, operation='DIVIDE')
    link(tree, n02, "Value", n10, "Value")
    link(tree, n08, "Integer", n10, "Value_001")

    n11 = add_node(tree, "ShaderNodeCombineXYZ", "5.11",
                    "Точка_на_плоскости = (0, 0, высота_разреза)", 260, 100)
    link(tree, n10, "Value", n11, "Z")

    n12 = add_node(tree, "ShaderNodeMath", "5.12", "наклон -> рад", 0, -50, operation='RADIANS')
    tree.links.new(GI("Наклон_шва_град"), in_sock(n12, "Value"))

    n13 = add_node(tree, "ShaderNodeCombineXYZ", "5.13", "Euler(Y=наклон)", 260, -50)
    link(tree, n12, "Value", n13, "Y")

    n14 = add_node(tree, "FunctionNodeRotateVector", "5.14",
                    "нормаль = поворот (0,0,1) на наклон вокруг Y", 520, 0)
    n14v = add_node(tree, "FunctionNodeInputVector", "5.14v", "(0,0,1)", 260, -180, vector=(0.0, 0.0, 1.0))
    link(tree, n14v, "Vector", n14, "Vector")
    n13e = add_node(tree, "FunctionNodeEulerToRotation", "5.13e", "Euler -> Rotation", 400, -80)
    link(tree, n13, "Vector", n13e, "Euler")
    link(tree, n13e, "Rotation", n14, "Rotation")

    frame2 = make_frame(tree, "2. ПЛОСКОСТЬ РАЗРЕЗА (высота посередине + наклон для незаметности шва)",
                         [n10, n11, n12, n13, n13e, n14, n14v])

    # ------------------------------------------------------------------
    # 3. РАЗРЕЗ Перед и Зад
    # ------------------------------------------------------------------
    cutF = _grp(tree, cut_tree, "5.15", "Разрез: Перед", 800, 300)
    tree.links.new(GI("Перед"), cutF.inputs["Geometry"])
    tree.links.new(n11.outputs["Vector"], cutF.inputs["Точка_на_плоскости"])
    tree.links.new(n14.outputs["Vector"], cutF.inputs["Нормаль_плоскости"])

    cutB = _grp(tree, cut_tree, "5.16", "Разрез: Зад", 800, 100)
    tree.links.new(GI("Зад"), cutB.inputs["Geometry"])
    tree.links.new(n11.outputs["Vector"], cutB.inputs["Точка_на_плоскости"])
    tree.links.new(n14.outputs["Vector"], cutB.inputs["Нормаль_плоскости"])

    frame3 = make_frame(tree, "3. РАЗРЕЗ ПЕРЕД И ЗАД (Group: NK.5a_Разрез_с_крышкой)", [cutF, cutB])

    # ------------------------------------------------------------------
    # 3b. ПАЗ-ШИП НА СТЫКЕ У ГРЕБНЯ (только Перед - гребень большеберцовой
    # кости есть только спереди). Находим РЕАЛЬНУЮ точку на поверхности
    # Перед возле гребня на высоте разреза через Geometry Proximity
    # (зондирующая точка далеко впереди оси - гарантированно снаружи,
    # Proximity привяжется к настоящей передней поверхности), строим
    # прямоугольный шип поперёк плоскости разреза (наклонённой вместе с
    # ней), объединяем с Низ (снаружи от плоскости), вычитаем чуть
    # больший паз из Верх - швов почти не видно, и деталь сама
    # позиционируется при сборке.
    # ------------------------------------------------------------------
    probe_pt = add_node(tree, "ShaderNodeCombineXYZ", "5.30", "зонд = (0, 150мм, высота_разреза) "
                         "- заведомо снаружи спереди", 0, -350)
    in_sock(probe_pt, "Y").default_value = 150.0
    link(tree, n10, "Value", probe_pt, "Z")

    prox = add_node(tree, "GeometryNodeProximity", "5.31", "ближайшая точка Перед к зонду",
                     260, -350, target_element='FACES')
    tree.links.new(GI("Перед"), in_sock(prox, "Target"))
    link(tree, probe_pt, "Vector", prox, "Source Position")

    tongue_box = add_node(tree, "GeometryNodeMeshCube", "5.32", "шип (куб)", 0, -550)
    tongue_size = add_node(tree, "ShaderNodeCombineXYZ", "5.32s",
                            "размер = (ширина, глубина, 2*выступ+запас в Низ)", 260, -550)
    tree.links.new(GI("Паз_гребня_ширина_мм"), in_sock(tongue_size, "X"))
    tree.links.new(GI("Паз_гребня_глубина_мм"), in_sock(tongue_size, "Y"))
    tongue_h = add_node(tree, "ShaderNodeMath", "5.32h", "2*выступ + 6мм (запас в Низ для сварки)",
                         0, -700, operation='MULTIPLY')
    tree.links.new(GI("Паз_гребня_выступ_мм"), in_sock(tongue_h, "Value"))
    in_sock(tongue_h, "Value_001").default_value = 2.0
    tongue_h2 = add_node(tree, "ShaderNodeMath", "5.32h2", "+6мм", 130, -700, operation='ADD')
    link(tree, tongue_h, "Value", tongue_h2, "Value")
    in_sock(tongue_h2, "Value_001").default_value = 6.0
    link(tree, tongue_h2, "Value", tongue_size, "Z")
    in_sock(tongue_box, "Size").default_value = (1.0, 1.0, 1.0)
    tongue_sc = add_node(tree, "GeometryNodeTransform", "5.32t", "масштаб шипа", 520, -550)
    link(tree, tongue_box, "Mesh", tongue_sc, "Geometry")
    link(tree, tongue_size, "Vector", tongue_sc, "Scale")

    # центр шипа: точка на поверхности гребня, смещённая ВДОЛЬ НОРМАЛИ
    # РАЗРЕЗА на (выступ - 3мм) - т.е. большая часть куба уходит В Низ
    # (запас на сварку), а наружу (в Верх) торчит ровно "выступ".
    tongue_off_len = add_node(tree, "ShaderNodeMath", "5.32o", "выступ - 3мм",
                               0, -850, operation='SUBTRACT')
    tree.links.new(GI("Паз_гребня_выступ_мм"), in_sock(tongue_off_len, "Value"))
    in_sock(tongue_off_len, "Value_001").default_value = 3.0
    tongue_off = add_node(tree, "ShaderNodeVectorMath", "5.32ov", "нормаль_разреза*(выступ-3мм)",
                           260, -850, operation='SCALE')
    link(tree, n14, "Vector", tongue_off, "Vector")
    link(tree, tongue_off_len, "Value", tongue_off, "Scale")
    tongue_center = add_node(tree, "ShaderNodeVectorMath", "5.32c", "центр = точка_гребня + смещение",
                              520, -800, operation='ADD')
    tree.links.new(out_sock(prox, "Position"), in_sock(tongue_center, "Vector"))
    link(tree, tongue_off, "Vector", tongue_center, "Vector_001")

    tongue_xf = add_node(tree, "GeometryNodeTransform", "5.33", "шип на место (поворот как у разреза)",
                          780, -550)
    link(tree, tongue_sc, "Geometry", tongue_xf, "Geometry")
    link(tree, n13e, "Rotation", tongue_xf, "Rotation")
    link(tree, tongue_center, "Vector", tongue_xf, "Translation")

    groove_size = add_node(tree, "ShaderNodeVectorMath", "5.34", "паз = шип + Паз_гребня_зазор*2 "
                            "(по X,Y; Z оставляем - паз той же глубины выемки)",
                            0, -1000, operation='ADD')
    link(tree, tongue_size, "Vector", groove_size, "Vector")
    gap2 = add_node(tree, "ShaderNodeVectorMath", "5.34g", "(зазор*2, зазор*2, 0)", 0, -1150,
                     operation='SCALE')
    gap2v = add_node(tree, "ShaderNodeCombineXYZ", "5.34gv", "(1,1,0)", -260, -1150)
    in_sock(gap2v, "X").default_value = 1.0
    in_sock(gap2v, "Y").default_value = 1.0
    link(tree, gap2v, "Vector", gap2, "Vector")
    gap2s = add_node(tree, "ShaderNodeMath", "5.34gs", "зазор*2", -260, -1000, operation='MULTIPLY')
    tree.links.new(GI("Паз_гребня_зазор_мм"), in_sock(gap2s, "Value"))
    in_sock(gap2s, "Value_001").default_value = 2.0
    link(tree, gap2s, "Value", gap2, "Scale")
    link(tree, gap2, "Vector", groove_size, "Vector_001")

    groove_box = add_node(tree, "GeometryNodeMeshCube", "5.35", "паз (куб)", 260, -1000)
    in_sock(groove_box, "Size").default_value = (1.0, 1.0, 1.0)
    groove_sc = add_node(tree, "GeometryNodeTransform", "5.35t", "масштаб паза", 520, -1000)
    link(tree, groove_box, "Mesh", groove_sc, "Geometry")
    link(tree, groove_size, "Vector", groove_sc, "Scale")
    groove_xf = add_node(tree, "GeometryNodeTransform", "5.36", "паз на место (тот же центр, что шип)",
                          780, -1000)
    link(tree, groove_sc, "Geometry", groove_xf, "Geometry")
    link(tree, n13e, "Rotation", groove_xf, "Rotation")
    link(tree, tongue_center, "Vector", groove_xf, "Translation")

    joint_on = add_node(tree, "FunctionNodeCompare", "5.37", "Паз_гребня_вкл > 0.5 И нужен разрез?",
                         1040, -200, data_type='FLOAT', operation='GREATER_THAN')
    tree.links.new(GI("Паз_гребня_вкл"), in_sock(joint_on, "A"))
    in_sock(joint_on, "B").default_value = 0.5
    joint_on2 = add_node(tree, "FunctionNodeBooleanMath", "5.37b", "И нужен разрез (иначе нет "
                          "второй детали, шип некуда ставить)", 1040, -100, operation='AND')
    link(tree, joint_on, "Result", joint_on2, "Boolean")
    link(tree, n09, "Result", joint_on2, "Boolean_001")

    empty_g = add_node(tree, "GeometryNodeMeshCube", "5.37e", "пусто (паз выкл.)", 780, -250)
    in_sock(empty_g, "Size").default_value = (0.0, 0.0, 0.0)
    tongue_sw = add_node(tree, "GeometryNodeSwitch", "5.38", "шип вкл?", 1040, -400, input_type='GEOMETRY')
    link(tree, joint_on2, "Boolean", tongue_sw, "Switch_001")
    link(tree, empty_g, "Mesh", tongue_sw, "False_006")
    link(tree, tongue_xf, "Geometry", tongue_sw, "True_006")
    groove_sw = add_node(tree, "GeometryNodeSwitch", "5.39", "паз вкл?", 1040, -650, input_type='GEOMETRY')
    link(tree, joint_on2, "Boolean", groove_sw, "Switch_001")
    link(tree, empty_g, "Mesh", groove_sw, "False_006")
    link(tree, groove_xf, "Geometry", groove_sw, "True_006")

    lowF_u = add_node(tree, "GeometryNodeMeshBoolean", "5.40", "Низ(Перед) + шип", 1300, -420,
                       operation='UNION')
    tree.links.new(cutF.outputs["Часть_B"], in_sock(lowF_u, "Mesh 2"))
    link(tree, tongue_sw, "Output_006", lowF_u, "Mesh 2")
    highF_d = add_node(tree, "GeometryNodeMeshBoolean", "5.41", "Верх(Перед) - паз", 1300, -650,
                        operation='DIFFERENCE')
    tree.links.new(cutF.outputs["Часть_A"], in_sock(highF_d, "Mesh 1"))
    link(tree, groove_sw, "Output_006", highF_d, "Mesh 2")

    frame3b = make_frame(
        tree, "3b. ПАЗ-ШИП У ГРЕБНЯ (только Перед): точка гребня через Proximity, "
        "шип UNION в Низ, паз DIFFERENCE из Верх",
        [probe_pt, prox, tongue_box, tongue_size, tongue_h, tongue_h2, tongue_sc,
         tongue_off_len, tongue_off, tongue_center, tongue_xf,
         groove_size, gap2, gap2v, gap2s, groove_box, groove_sc, groove_xf,
         joint_on, joint_on2, empty_g, tongue_sw, groove_sw, lowF_u, highF_d])

    # ------------------------------------------------------------------
    # 4. ВЫБОР: если сегмент не нужен - взять целую деталь / пусто
    # ------------------------------------------------------------------
    swFL = add_node(tree, "GeometryNodeSwitch", "5.17", "Перед_Низ: разрез?B(+шип), иначе целиком",
                     1150, 350, input_type='GEOMETRY')
    link(tree, n09, "Result", swFL, "Switch_001")  # GEOMETRY -> Switch_001, не Switch! (см. докстринг/докc)
    tree.links.new(GI("Перед"), in_sock(swFL, "False_006"))
    link(tree, lowF_u, "Mesh", swFL, "True_006")

    swFH = add_node(tree, "GeometryNodeSwitch", "5.18", "Перед_Верх: разрез?A(-паз), иначе пусто",
                     1150, 200, input_type='GEOMETRY')
    link(tree, n09, "Result", swFH, "Switch_001")  # GEOMETRY -> Switch_001, не Switch! (см. докстринг/докc)
    link(tree, highF_d, "Mesh", swFH, "True_006")
    # False_006 не подключаем - остаётся пустая геометрия

    swBL = add_node(tree, "GeometryNodeSwitch", "5.19", "Зад_Низ: разрез?B, иначе целиком",
                     1150, 50, input_type='GEOMETRY')
    link(tree, n09, "Result", swBL, "Switch_001")  # GEOMETRY -> Switch_001, не Switch! (см. докстринг/докc)
    tree.links.new(GI("Зад"), in_sock(swBL, "False_006"))
    tree.links.new(cutB.outputs["Часть_B"], in_sock(swBL, "True_006"))

    swBH = add_node(tree, "GeometryNodeSwitch", "5.20", "Зад_Верх: разрез?A, иначе пусто",
                     1150, -100, input_type='GEOMETRY')
    link(tree, n09, "Result", swBH, "Switch_001")  # GEOMETRY -> Switch_001, не Switch! (см. докстринг/докc)
    tree.links.new(cutB.outputs["Часть_A"], in_sock(swBH, "True_006"))

    frame4 = make_frame(tree, "4. ЕСЛИ РАЗРЕЗ НЕ НУЖЕН - ВЕРНУТЬ ЦЕЛИКОМ / ПУСТО",
                         [swFL, swFH, swBL, swBH])

    # ------------------------------------------------------------------
    # 5. ИТОГ: VIS + проверки + отчёт
    # ------------------------------------------------------------------
    vjoin = add_node(tree, "GeometryNodeJoinGeometry", "5.21", "VIS_Вместе", 1500, 150)
    for src in (swFL, swFH, swBL, swBH):
        tree.links.new(out_sock(src, "Output_006"), vjoin.inputs["Geometry"])

    def watertight_check(num, label, x, y, geo_socket):
        en = add_node(tree, "GeometryNodeInputMeshEdgeNeighbors", num + "a",
                       "кол-во граней/ребро", x, y)
        cmp = add_node(tree, "FunctionNodeCompare", num + "b", "ребро граничное?",
                        x + 260, y, data_type='INT', operation='NOT_EQUAL')
        link(tree, en, "Face Count", cmp, "A_INT")
        in_sock(cmp, "B_INT").default_value = 2
        stat = add_node(tree, "GeometryNodeAttributeStatistic", num + "c",
                         "сумма граничных рёбер", x + 520, y, domain='EDGE')
        tree.links.new(geo_socket, in_sock(stat, "Geometry"))
        link(tree, cmp, "Result", stat, "Attribute")
        ok = add_node(tree, "FunctionNodeCompare", num + "d", "== 0 ?", x + 780, y,
                       data_type='FLOAT', operation='EQUAL')
        link(tree, stat, "Sum", ok, "A")
        in_sock(ok, "B").default_value = 0.0
        return stat, ok

    stat_fl, ok_fl = watertight_check("V5.1", "wt", 1500, 700, out_sock(swFL, "Output_006"))
    stat_fh, ok_fh = watertight_check("V5.2", "wt", 1500, 500, out_sock(swFH, "Output_006"))
    stat_bl, ok_bl = watertight_check("V5.3", "wt", 1500, 300, out_sock(swBL, "Output_006"))
    stat_bh, ok_bh = watertight_check("V5.4", "wt", 1500, 100, out_sock(swBH, "Output_006"))

    a1 = add_node(tree, "FunctionNodeBooleanMath", "V5.5", "AND(fl,fh)", 2600, 600, operation='AND')
    link(tree, ok_fl, "Result", a1, "Boolean")
    link(tree, ok_fh, "Result", a1, "Boolean_001")
    a2 = add_node(tree, "FunctionNodeBooleanMath", "V5.6", "AND(bl,bh)", 2600, 400, operation='AND')
    link(tree, ok_bl, "Result", a2, "Boolean")
    link(tree, ok_bh, "Result", a2, "Boolean_001")
    a3 = add_node(tree, "FunctionNodeBooleanMath", "V5.7", "ИТОГ: все 4 сегмента замкнуты",
                  2860, 500, operation='AND')
    link(tree, a1, "Boolean", a3, "Boolean")
    link(tree, a2, "Boolean", a3, "Boolean_001")

    frame5 = make_frame(
        tree, "5. ПРОВЕРКА ЗАМКНУТОСТИ ВСЕХ 4 ВЫХОДОВ (пустые - тривиально проходят: sum(0 рёбер)=0)",
        [ok_fl, ok_fh, ok_bl, ok_bh, a1, a2, a3])

    rep1 = add_node(tree, "FunctionNodeValueToString", "5.22", "сегментов -> строка", 2600, 200)
    link(tree, n08, "Integer", rep1, "Value")
    in_sock(rep1, "Decimals").default_value = 0
    rep_join = add_node(tree, "GeometryNodeStringJoin", "5.23", "'сегментов: ' + N", 2860, 200)
    in_sock(rep_join, "Delimiter").default_value = ""
    strconst = add_node(tree, "FunctionNodeInputString", "5.22s", "'Сегментов на половину: '", 2600, 100)
    strconst.string = "Сегментов на половину: "
    tree.links.new(strconst.outputs["String"], rep_join.inputs["Strings"])
    tree.links.new(rep1.outputs["String"], rep_join.inputs["Strings"])

    tree.links.new(vjoin.outputs["Geometry"], gout.inputs["VIS_Вместе"])
    tree.links.new(out_sock(swFL, "Output_006"), gout.inputs["Перед_Низ"])
    tree.links.new(out_sock(swFH, "Output_006"), gout.inputs["Перед_Верх"])
    tree.links.new(out_sock(swBL, "Output_006"), gout.inputs["Зад_Низ"])
    tree.links.new(out_sock(swBH, "Output_006"), gout.inputs["Зад_Верх"])
    tree.links.new(n08.outputs["Integer"], gout.inputs["Число_сегментов"])
    tree.links.new(a3.outputs["Boolean"], gout.inputs["Провер_ВСЕ_OK"])
    tree.links.new(rep_join.outputs["String"], gout.inputs["Провер_Отчёт"])

    return tree


def build_all_groups():
    cap_tree = build_cap()
    cut_tree = build_cut(cap_tree)
    print_tree = build_print(cut_tree)
    return print_tree


if __name__ == "__main__":
    print_tree = build_all_groups()
    print("OK: '%s' собрана, узлов=%d" % (PRINT_NAME, len(print_tree.nodes)))
