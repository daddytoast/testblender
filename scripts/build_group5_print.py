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
    # 4. ВЫБОР: если сегмент не нужен - взять целую деталь / пусто
    # ------------------------------------------------------------------
    swFL = add_node(tree, "GeometryNodeSwitch", "5.17", "Перед_Низ: разрез?B, иначе целиком",
                     1150, 350, input_type='GEOMETRY')
    link(tree, n09, "Result", swFL, "Switch_001")  # GEOMETRY -> Switch_001, не Switch! (см. докстринг/докc)
    tree.links.new(GI("Перед"), in_sock(swFL, "False_006"))
    tree.links.new(cutF.outputs["Часть_B"], in_sock(swFL, "True_006"))

    swFH = add_node(tree, "GeometryNodeSwitch", "5.18", "Перед_Верх: разрез?A, иначе пусто",
                     1150, 200, input_type='GEOMETRY')
    link(tree, n09, "Result", swFH, "Switch_001")  # GEOMETRY -> Switch_001, не Switch! (см. докстринг/докc)
    tree.links.new(cutF.outputs["Часть_A"], in_sock(swFH, "True_006"))
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
