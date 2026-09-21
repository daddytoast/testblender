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
    add_input(tree, "Стык_вкл", "NodeSocketFloat", default=1.0, min_value=0.0, max_value=1.0,
              description="1 = добавить треугольный гребень/впадину по ВСЕМУ периметру разреза "
                           "(шпунтовое соединение); 0 = обычный плоский срез без гребня.")
    add_input(tree, "Стык_высота_мм", "NodeSocketFloat", default=1.0, min_value=0.2, max_value=3.0,
              description="Высота треугольного гребня по нормали к плоскости разреза, мм.")
    add_input(tree, "Стык_угол_град", "NodeSocketFloat", default=60.0, min_value=20.0, max_value=100.0,
              description="Угол при вершине треугольного профиля гребня (широкое основание, "
                           "узкая вершина), градусы.")
    add_input(tree, "Стык_зазор_мм", "NodeSocketFloat", default=0.1, min_value=0.0, max_value=1.0,
              description="Зазор впадина<->гребень (посадка под клей и допуски печати), мм.")
    add_input(tree, "Кромка_радиус_мм", "NodeSocketFloat", default=0.2, min_value=0.05, max_value=1.0,
              description="Скругление кромок треугольного профиля (основание и вершина), мм - "
                           "приближение через Fillet Curve, единый радиус на весь профиль "
                           "(отдельный радиус вершины 0.15мм из ТЗ не выделяется отдельно, т.к. "
                           "обе величины меньше ширины линии сопла FDM ~0.4мм).")
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

    # ------------------------------------------------------------------
    # 3. ТРЕУГОЛЬНЫЙ ГРЕБЕНЬ/ВПАДИНА ПО ВСЕМУ ПЕРИМЕТРУ РАЗРЕЗА (шпунт)
    # Контур разреза = открытые (граничные) рёбра ЕЩЁ НЕ закрытой части B
    # (тот же контур, что у части A - это одна и та же линия разреза,
    # просто с двух сторон). Превращаем его в замкнутую кривую(ые) и
    # "выдавливаем" вдоль неё треугольный профиль (Curve to Mesh) - это
    # НЕ Boolean по позициям (в отличие от старого прямоугольного шипа
    # только у гребня кости), а один целый замкнутый "бублик"-тело,
    # поэтому he'т риска "касательного" краевого дефекта, характерного
    # для одиночных бобышек на органической поверхности (см. Группа 4).
    # ------------------------------------------------------------------
    # ВАЖНО (эмпирически проверено, см. diag_g5*.py): GeometryNodeMeshBoolean
    # с operation=INTERSECT - это НАСТОЯЩИЙ CSG-буллин, а не простое
    # "отрезание половины" - для манифолд-входов он САМ уже строит
    # закрытую (capped) грань на плоскости среза. Поэтому классический
    # приём "Edge Neighbors != 2" (используемый в NK.5b_Крышка_среза для
    # ПОСТ-фактум починки открытых рёбер) здесь находит 0 рёбер - грань
    # разреза уже цельная, открытого контура попросту нет. Вместо этого
    # находим кольцо шва ГЕОМЕТРИЧЕСКИ: ребро принадлежит контуру среза,
    # если ОБЕ его вершины лежат точно на плоскости разреза.
    b01 = add_node(tree, "GeometryNodeInputMeshEdgeVertices", "5a.b01",
                    "позиции обеих вершин каждого ребра", 1080, -150)

    b_d1 = add_node(tree, "ShaderNodeVectorMath", "5a.bd1",
                     "v1 - точка_на_плоскости", 1340, -100, operation='SUBTRACT')
    tree.links.new(out_sock(b01, "Position 1"), in_sock(b_d1, "Vector"))
    tree.links.new(GI("Точка_на_плоскости"), in_sock(b_d1, "Vector_001"))
    b_dot1 = add_node(tree, "ShaderNodeVectorMath", "5a.bdo1",
                       "dot(v1-точка, нормаль)", 1600, -100, operation='DOT_PRODUCT')
    link(tree, b_d1, "Vector", b_dot1, "Vector")
    tree.links.new(GI("Нормаль_плоскости"), in_sock(b_dot1, "Vector_001"))
    b_abs1 = add_node(tree, "ShaderNodeMath", "5a.babs1", "|dot1|", 1860, -100,
                       operation='ABSOLUTE')
    link(tree, b_dot1, "Value", b_abs1, "Value")
    b_on1 = add_node(tree, "FunctionNodeCompare", "5a.bon1",
                      "вершина 1 на плоскости? (<0.01мм)", 2120, -100,
                      data_type='FLOAT', operation='LESS_THAN')
    link(tree, b_abs1, "Value", b_on1, "A")
    in_sock(b_on1, "B").default_value = 0.01

    b_d2 = add_node(tree, "ShaderNodeVectorMath", "5a.bd2",
                     "v2 - точка_на_плоскости", 1340, -250, operation='SUBTRACT')
    tree.links.new(out_sock(b01, "Position 2"), in_sock(b_d2, "Vector"))
    tree.links.new(GI("Точка_на_плоскости"), in_sock(b_d2, "Vector_001"))
    b_dot2 = add_node(tree, "ShaderNodeVectorMath", "5a.bdo2",
                       "dot(v2-точка, нормаль)", 1600, -250, operation='DOT_PRODUCT')
    link(tree, b_d2, "Vector", b_dot2, "Vector")
    tree.links.new(GI("Нормаль_плоскости"), in_sock(b_dot2, "Vector_001"))
    b_abs2 = add_node(tree, "ShaderNodeMath", "5a.babs2", "|dot2|", 1860, -250,
                       operation='ABSOLUTE')
    link(tree, b_dot2, "Value", b_abs2, "Value")
    b_on2 = add_node(tree, "FunctionNodeCompare", "5a.bon2",
                      "вершина 2 на плоскости? (<0.01мм)", 2120, -250,
                      data_type='FLOAT', operation='LESS_THAN')
    link(tree, b_abs2, "Value", b_on2, "A")
    in_sock(b_on2, "B").default_value = 0.01

    b02 = add_node(tree, "FunctionNodeBooleanMath", "5a.b02",
                    "ребро на шве? (обе вершины на плоскости)", 2380, -175, operation='AND')
    link(tree, b_on1, "Result", b02, "Boolean")
    link(tree, b_on2, "Result", b02, "Boolean_001")

    b03 = add_node(tree, "GeometryNodeMeshToCurve", "5a.b03",
                    "контур разреза -> кривая(ые) (обычно 1 замкнутый контур на половину)",
                    2640, -150)
    link(tree, n11, "Mesh", b03, "Mesh")
    link(tree, b02, "Boolean", b03, "Selection")

    frameB = make_frame(
        tree, "3a. КОНТУР РАЗРЕЗА (рёбра, ОБЕ вершины которых лежат точно на "
        "плоскости среза - НЕ 'открытые рёбра', т.к. Boolean INTERSECT уже "
        "сам закрывает срез) -> кривая",
        [b01, b_d1, b_dot1, b_abs1, b_on1, b_d2, b_dot2, b_abs2, b_on2, b02, b03])

    # -- треугольный профиль: MeshCircle(3 верш.) даёт равносторонний
    # треугольник (вершина 0 = "апекс" наверху, 1,2 = основание) - меняем
    # позиции по индексу на точный несимметричный профиль нужных
    # размеров, затем скругляем углы (Fillet Curve).
    # Экспериментально проверено (probe_curve2mesh.py): для Curve to
    # Mesh с путём вдоль касательной T локальная ось профиля X ->
    # ПОПЕРЕЧНОЕ (радиальное, в плоскости среза) направление, а
    # локальная ось Y (со знаком МИНУС) -> направление НОРМАЛИ плоскости
    # среза - т.е. апекс с отрицательным Y "выдавливается" в сторону
    # normal_of_cut, а основание с Y=0 остаётся точно на плоскости среза.
    def tri_profile(num_prefix, halfwidth_mm, height_mm, x, y, label_suffix=""):
        circ = add_node(tree, "GeometryNodeMeshCircle", num_prefix + "a",
                         "донор: равносторонний треугольник (3 верш.)" + label_suffix,
                         x, y)
        circ.fill_type = 'NONE'
        in_sock(circ, "Vertices").default_value = 3
        in_sock(circ, "Radius").default_value = 1.0

        idx = add_node(tree, "GeometryNodeInputIndex", num_prefix + "b", "индекс вершины",
                        x, y - 150)
        is_apex = add_node(tree, "FunctionNodeCompare", num_prefix + "c", "вершина 0 = апекс?",
                            x + 200, y - 150, data_type='INT', operation='EQUAL')
        link(tree, idx, "Index", is_apex, "A_INT")
        in_sock(is_apex, "B_INT").default_value = 0

        # ВАЖНО (эмпирически проверено, см. diag_g5g.py): 3-вершинный
        # MeshCircle кладёт вершины на углах 0°/120°/240° - т.е. вершины
        # 1 и 2 (основание) имеют ОДИНАКОВЫЙ знак X (обе -0.5), это НЕ
        # зеркальная пара относительно X - поэтому знак берём не из
        # исходной позиции донора, а прямо из ИНДЕКСА вершины
        # (детерминировано, не зависит от условности раскладки круга):
        # индекс1 -> -1, индекс2 -> +1 (апекс, индекс0, всё равно
        # переопределяется отдельно ниже).
        signraw = add_node(tree, "ShaderNodeMath", num_prefix + "sr",
                            "index - 1.5", x + 200, y - 450, operation='SUBTRACT')
        link(tree, idx, "Index", signraw, "Value")
        in_sock(signraw, "Value_001").default_value = 1.5
        sign = add_node(tree, "ShaderNodeMath", num_prefix + "sgn",
                         "sign(index-1.5): индекс1->-1, индекс2->+1", x + 460, y - 450,
                         operation='SIGN')
        link(tree, signraw, "Value", sign, "Value")

        newx = add_node(tree, "ShaderNodeMath", num_prefix + "nx", "новый X = sign(X)*halfwidth",
                         x + 720, y - 450, operation='MULTIPLY')
        link(tree, sign, "Value", newx, "Value")
        in_sock(newx, "Value_001").default_value = halfwidth_mm

        newy_base = add_node(tree, "ShaderNodeMath", num_prefix + "nyb",
                              "новый Y (основание) = 0", x + 460, y - 600, operation='MULTIPLY')
        in_sock(newy_base, "Value").default_value = 0.0
        in_sock(newy_base, "Value_001").default_value = 0.0
        newy_apex = add_node(tree, "ShaderNodeMath", num_prefix + "nya",
                              "новый Y (апекс) = -height", x + 460, y - 700, operation='MULTIPLY')
        in_sock(newy_apex, "Value").default_value = -1.0
        in_sock(newy_apex, "Value_001").default_value = height_mm

        newy = add_node(tree, "ShaderNodeMix", num_prefix + "ny", "Y = апекс?newy_apex:newy_base",
                         x + 720, y - 600, data_type='FLOAT')
        link(tree, is_apex, "Result", newy, "Factor_Float")
        link(tree, newy_base, "Value", newy, "A_Float")
        link(tree, newy_apex, "Value", newy, "B_Float")

        newx_final = add_node(tree, "ShaderNodeMix", num_prefix + "nxf",
                               "X = апекс?0:newx", x + 980, y - 450, data_type='FLOAT')
        link(tree, is_apex, "Result", newx_final, "Factor_Float")
        link(tree, newx, "Value", newx_final, "A_Float")
        in_sock(newx_final, "B_Float").default_value = 0.0

        combine = add_node(tree, "ShaderNodeCombineXYZ", num_prefix + "cxyz",
                            "новая позиция (X,Y,0)", x + 1240, y - 500)
        link(tree, newx_final, "Result_Float", combine, "X")
        link(tree, newy, "Result_Float", combine, "Y")

        setpos = add_node(tree, "GeometryNodeSetPosition", num_prefix + "sp",
                           "записать новую позицию (профиль готов)", x + 1500, y - 300)
        link(tree, circ, "Mesh", setpos, "Geometry")
        link(tree, combine, "Vector", setpos, "Position")

        curve = add_node(tree, "GeometryNodeMeshToCurve", num_prefix + "mc",
                          "профиль-меш -> кривая (замкнутая)", x + 1760, y - 300)
        link(tree, setpos, "Geometry", curve, "Mesh")

        fillet = add_node(tree, "GeometryNodeFilletCurve", num_prefix + "fc",
                           "скругление углов профиля" + label_suffix, x + 2020, y - 300,
                           mode='POLY')
        link(tree, curve, "Curve", fillet, "Curve")
        tree.links.new(GI("Кромка_радиус_мм"), in_sock(fillet, "Radius"))
        in_sock(fillet, "Count").default_value = 4

        nodes_list = [circ, idx, is_apex, signraw, sign, newx, newy_base,
                      newy_apex, newy, newx_final, combine, setpos, curve, fillet]
        return fillet, nodes_list

    # ширина = height*tan(угол/2)*2 (полная), т.е. halfwidth = height*tan(угол/2)
    halfw_rad = add_node(tree, "ShaderNodeMath", "5a.hw0", "угол/2 -> рад", 1600, -700,
                          operation='RADIANS')
    halfw_deg2 = add_node(tree, "ShaderNodeMath", "5a.hw0b", "угол/2", 1600, -600,
                           operation='DIVIDE')
    tree.links.new(GI("Стык_угол_град"), in_sock(halfw_deg2, "Value"))
    in_sock(halfw_deg2, "Value_001").default_value = 2.0
    link(tree, halfw_deg2, "Value", halfw_rad, "Value")
    halfw_tan = add_node(tree, "ShaderNodeMath", "5a.hw1", "tan(угол/2)", 1860, -700,
                          operation='TANGENT')
    link(tree, halfw_rad, "Value", halfw_tan, "Value")
    halfw_mm = add_node(tree, "ShaderNodeMath", "5a.hw2",
                         "halfwidth_гребень_мм = высота * tan(угол/2)", 2120, -700,
                         operation='MULTIPLY')
    tree.links.new(GI("Стык_высота_мм"), in_sock(halfw_mm, "Value"))
    link(tree, halfw_tan, "Value", halfw_mm, "Value_001")

    # впадина крупнее гребня на зазор (по ширине и по высоте) - гребень
    # входит с зазором Стык_зазор_мм со всех сторон.
    halfw_groove = add_node(tree, "ShaderNodeMath", "5a.hw3",
                             "halfwidth_впадина_мм = halfwidth_гребень + зазор", 2380, -700,
                             operation='ADD')
    link(tree, halfw_mm, "Value", halfw_groove, "Value")
    tree.links.new(GI("Стык_зазор_мм"), in_sock(halfw_groove, "Value_001"))
    height_groove = add_node(tree, "ShaderNodeMath", "5a.hw4",
                              "высота_впадина_мм = высота_гребень + зазор", 2380, -850,
                              operation='ADD')
    tree.links.new(GI("Стык_высота_мм"), in_sock(height_groove, "Value"))
    tree.links.new(GI("Стык_зазор_мм"), in_sock(height_groove, "Value_001"))

    frameW = make_frame(tree, "3b. РАЗМЕРЫ ТРЕУГОЛЬНОГО ПРОФИЛЯ (из угла при вершине + зазор)",
                         [halfw_rad, halfw_deg2, halfw_tan, halfw_mm, halfw_groove, height_groove])

    # NB: halfwidth/height профиля задаются КОНСТАНТАМИ узлов, но реально
    # зависят от входов Стык_высота_мм/Стык_угол_град/Стык_зазор_мм -
    # передаём их напрямую через default_value сокетов внутри tri_profile
    # нельзя (это функция создаёт статичные Math-узлы) - поэтому строим
    # профиль с УЖЕ вычисленными полями напрямую, минуя параметры функции
    # (см. ниже: подменяем default_value у newx/newy_apex через отдельные
    # линки к вычисленным halfw_mm/Стык_высота_мм).
    def _find(nodes_list, num_prefix, suffix):
        target = num_prefix + suffix
        for n in nodes_list:
            if n.name.startswith(target + " "):
                return n
        raise KeyError(target)

    ridge_fillet, ridge_nodes = tri_profile("5a.rp", 0.0, 0.0, 1600, -1100, " (гребень)")
    # Подключаем реальные вычисленные размеры вместо временных заглушек:
    ridge_newx = _find(ridge_nodes, "5a.rp", "nx")
    ridge_newya = _find(ridge_nodes, "5a.rp", "nya")
    tree.links.new(out_sock(halfw_mm, "Value"), in_sock(ridge_newx, "Value_001"))
    tree.links.new(GI("Стык_высота_мм"), in_sock(ridge_newya, "Value_001"))

    groove_fillet, groove_nodes = tri_profile("5a.gp", 0.0, 0.0, 1600, -1700, " (впадина)")
    groove_newx = _find(groove_nodes, "5a.gp", "nx")
    groove_newya = _find(groove_nodes, "5a.gp", "nya")
    tree.links.new(out_sock(halfw_groove, "Value"), in_sock(groove_newx, "Value_001"))
    tree.links.new(out_sock(height_groove, "Value"), in_sock(groove_newya, "Value_001"))

    frameProfiles = make_frame(tree, "3c. ПРОФИЛИ (гребень = точный размер, впадина = гребень+зазор)",
                                ridge_nodes + groove_nodes)

    # -- выдавить профиль вдоль контура разреза --
    c2m_ridge = add_node(tree, "GeometryNodeCurveToMesh", "5a.c2mR",
                          "гребень (тело) = профиль x контур разреза", 2300, -1100)
    link(tree, b03, "Curve", c2m_ridge, "Curve")
    link(tree, ridge_fillet, "Curve", c2m_ridge, "Profile Curve")

    c2m_groove = add_node(tree, "GeometryNodeCurveToMesh", "5a.c2mG",
                           "впадина (тело) = профиль x контур разреза", 2300, -1700)
    link(tree, b03, "Curve", c2m_groove, "Curve")
    link(tree, groove_fillet, "Curve", c2m_groove, "Profile Curve")

    frameSweep = make_frame(tree, "3d. CURVE TO MESH: замкнутые тела гребня и впадины по всему контуру",
                             [c2m_ridge, c2m_groove])

    # -- Часть B (Низ) + гребень (UNION); Часть A (Верх) - впадина (DIFFERENCE) --
    # ВАЖНО: у GeometryNodeMeshBoolean сокет "Mesh 2" - МУЛЬТИ-ВХОД (list),
    # оба операнда UNION/INTERSECT подаются раздельными линками именно в
    # него (см. n10/n11 выше) - это настоящий CSG-буллин, а НЕ
    # Join+Merge By Distance (тот годится только для сшивки НЕПЕРЕСЕКАЮЩИХСЯ
    # кусков по общему шву, как в Группе 3 - здесь же тело гребня
    # ОБЪЁМНО пересекается с телом Низа, простое сваривание вершин
    # оставило бы внутренние задвоенные грани).
    unionB0 = add_node(tree, "GeometryNodeMeshBoolean", "5a.j2", "Низ UNION гребень",
                        2600, -300, operation='UNION')
    tree.links.new(n13.outputs["Mesh"], in_sock(unionB0, "Mesh 2"))
    tree.links.new(c2m_ridge.outputs["Mesh"], in_sock(unionB0, "Mesh 2"))
    unionB = add_node(tree, "GeometryNodeMergeByDistance", "5a.j2m",
                       "сварить близкие вершины после буллина (0.01мм)", 2860, -300)
    link(tree, unionB0, "Mesh", unionB, "Geometry")
    in_sock(unionB, "Distance").default_value = 0.01

    diffA0 = add_node(tree, "GeometryNodeMeshBoolean", "5a.j3", "Верх DIFFERENCE впадина",
                       2600, 250, operation='DIFFERENCE')
    tree.links.new(n12.outputs["Mesh"], in_sock(diffA0, "Mesh 1"))
    tree.links.new(c2m_groove.outputs["Mesh"], in_sock(diffA0, "Mesh 2"))
    diffA = add_node(tree, "GeometryNodeMergeByDistance", "5a.j3m",
                      "сварить близкие вершины после буллина (0.01мм)", 2860, 250)
    link(tree, diffA0, "Mesh", diffA, "Geometry")
    in_sock(diffA, "Distance").default_value = 0.01

    frameJoin = make_frame(tree, "3e. UNION гребня в Низ / DIFFERENCE впадины из Верх + сварка",
                            [unionB0, unionB, diffA0, diffA])

    # -- переключатель: Стык_вкл=0 -> обычный плоский срез (без гребня) --
    swA = add_node(tree, "GeometryNodeSwitch", "5a.swA", "Часть_A: со впадиной или плоская?",
                    2900, 250, input_type='GEOMETRY')
    joint_on = add_node(tree, "FunctionNodeCompare", "5a.jon", "Стык_вкл > 0.5?", 2600, 500,
                         data_type='FLOAT', operation='GREATER_THAN')
    tree.links.new(GI("Стык_вкл"), in_sock(joint_on, "A"))
    in_sock(joint_on, "B").default_value = 0.5
    link(tree, joint_on, "Result", swA, "Switch_001")
    tree.links.new(n12.outputs["Mesh"], in_sock(swA, "False_006"))
    link(tree, diffA, "Geometry", swA, "True_006")

    swB = add_node(tree, "GeometryNodeSwitch", "5a.swB", "Часть_B: с гребнем или плоская?",
                    3380, -300, input_type='GEOMETRY')
    link(tree, joint_on, "Result", swB, "Switch_001")
    tree.links.new(n13.outputs["Mesh"], in_sock(swB, "False_006"))
    link(tree, unionB, "Geometry", swB, "True_006")

    frameSwitch = make_frame(tree, "3f. Стык_вкл=0 -> вернуть обычный плоский срез без гребня",
                              [joint_on, swA, swB])

    tree.links.new(out_sock(swA, "Output_006"), gout.inputs["Часть_A"])
    tree.links.new(out_sock(swB, "Output_006"), gout.inputs["Часть_B"])
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
    add_input(tree, "Стык_вкл", "NodeSocketFloat", default=1.0, min_value=0.0, max_value=1.0,
              description="1 = треугольный гребень/впадина по ВСЕМУ периметру разреза (и Перед, "
                           "и Зад). 0 = обычный плоский срез без гребня.")
    add_input(tree, "Стык_высота_мм", "NodeSocketFloat", default=1.0, min_value=0.2, max_value=3.0,
              description="Высота треугольного гребня по нормали к плоскости разреза, мм.")
    add_input(tree, "Стык_угол_град", "NodeSocketFloat", default=60.0, min_value=20.0, max_value=100.0,
              description="Угол при вершине треугольного профиля гребня, градусы.")
    add_input(tree, "Стык_зазор_мм", "NodeSocketFloat", default=0.1, min_value=0.0, max_value=1.0,
              description="Зазор впадина<->гребень (клей, допуски печати), мм.")
    add_input(tree, "Кромка_радиус_мм", "NodeSocketFloat", default=0.2, min_value=0.05, max_value=1.0,
              description="Скругление кромок треугольного профиля (Fillet Curve, единый радиус).")

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
    tree.links.new(GI("Стык_вкл"), cutF.inputs["Стык_вкл"])
    tree.links.new(GI("Стык_высота_мм"), cutF.inputs["Стык_высота_мм"])
    tree.links.new(GI("Стык_угол_град"), cutF.inputs["Стык_угол_град"])
    tree.links.new(GI("Стык_зазор_мм"), cutF.inputs["Стык_зазор_мм"])
    tree.links.new(GI("Кромка_радиус_мм"), cutF.inputs["Кромка_радиус_мм"])

    cutB = _grp(tree, cut_tree, "5.16", "Разрез: Зад", 800, 100)
    tree.links.new(GI("Зад"), cutB.inputs["Geometry"])
    tree.links.new(n11.outputs["Vector"], cutB.inputs["Точка_на_плоскости"])
    tree.links.new(n14.outputs["Vector"], cutB.inputs["Нормаль_плоскости"])
    tree.links.new(GI("Стык_вкл"), cutB.inputs["Стык_вкл"])
    tree.links.new(GI("Стык_высота_мм"), cutB.inputs["Стык_высота_мм"])
    tree.links.new(GI("Стык_угол_град"), cutB.inputs["Стык_угол_град"])
    tree.links.new(GI("Стык_зазор_мм"), cutB.inputs["Стык_зазор_мм"])
    tree.links.new(GI("Кромка_радиус_мм"), cutB.inputs["Кромка_радиус_мм"])

    frame3 = make_frame(
        tree, "3. РАЗРЕЗ ПЕРЕД И ЗАД, С ТРЕУГОЛЬНЫМ ГРЕБНЕМ/ВПАДИНОЙ ПО ВСЕМУ ПЕРИМЕТРУ "
        "(Group: NK.5a_Разрез_с_крышкой - см. её внутреннюю логику 3a-3f)", [cutF, cutB])

    # ------------------------------------------------------------------
    # 4. ВЫБОР: если сегмент не нужен - взять целую деталь / пусто
    # ------------------------------------------------------------------
    swFL = add_node(tree, "GeometryNodeSwitch", "5.17", "Перед_Низ: разрез?B(+гребень), иначе целиком",
                     1150, 350, input_type='GEOMETRY')
    link(tree, n09, "Result", swFL, "Switch_001")  # GEOMETRY -> Switch_001, не Switch! (см. докстринг/докc)
    tree.links.new(GI("Перед"), in_sock(swFL, "False_006"))
    tree.links.new(cutF.outputs["Часть_B"], in_sock(swFL, "True_006"))

    swFH = add_node(tree, "GeometryNodeSwitch", "5.18", "Перед_Верх: разрез?A(-впадина), иначе пусто",
                     1150, 200, input_type='GEOMETRY')
    link(tree, n09, "Result", swFH, "Switch_001")  # GEOMETRY -> Switch_001, не Switch! (см. докстринг/докc)
    tree.links.new(cutF.outputs["Часть_A"], in_sock(swFH, "True_006"))
    # False_006 не подключаем - остаётся пустая геометрия

    swBL = add_node(tree, "GeometryNodeSwitch", "5.19", "Зад_Низ: разрез?B(+гребень), иначе целиком",
                     1150, 50, input_type='GEOMETRY')
    link(tree, n09, "Result", swBL, "Switch_001")  # GEOMETRY -> Switch_001, не Switch! (см. докстринг/докc)
    tree.links.new(GI("Зад"), in_sock(swBL, "False_006"))
    tree.links.new(cutB.outputs["Часть_B"], in_sock(swBL, "True_006"))

    swBH = add_node(tree, "GeometryNodeSwitch", "5.20", "Зад_Верх: разрез?A(-впадина), иначе пусто",
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
