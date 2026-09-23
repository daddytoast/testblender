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
              description="1 = добавить шип/паз (трапециевидного или прямоугольного сечения) по "
                           "периметру разреза; 0 = обычный плоский срез без шипа.")
    add_input(tree, "Стык_высота_мм", "NodeSocketFloat", default=1.2, min_value=0.3, max_value=3.0,
              description="Высота шипа по нормали к плоскости разреза, мм.")
    add_input(tree, "Стык_ширина_мм", "NodeSocketFloat", default=2.0, min_value=0.5, max_value=6.0,
              description="Ширина ОСНОВАНИЯ шипа (широкий конец, на плоскости среза), мм.")
    add_input(tree, "Стык_скос_мм", "NodeSocketFloat", default=0.4, min_value=0.0, max_value=2.0,
              description="На сколько мм УЖЕ узкий конец шипа с каждой стороны относительно "
                           "основания - 0 = прямоугольное/квадратное сечение, >0 = трапециевидное "
                           "(лёгкий скос для самоцентровки при сборке).")
    add_input(tree, "Стык_зазор_мм", "NodeSocketFloat", default=0.1, min_value=0.0, max_value=1.0,
              description="Зазор паз<->шип (посадка под клей и допуски печати), мм.")
    add_input(tree, "Кромка_радиус_мм", "NodeSocketFloat", default=0.2, min_value=0.05, max_value=1.0,
              description="Скругление углов сечения шипа, мм - приближение через Fillet Curve.")
    add_input(tree, "Стык_сегменты_вкл", "NodeSocketFloat", default=0.0, min_value=0.0, max_value=1.0,
              description="0 = шип/паз сплошной на всю длину грани разреза; 1 = прерывистый "
                           "(чередование Стык_сегмент_мм шипа и Стык_промежуток_мм пропуска).")
    add_input(tree, "Стык_сегмент_мм", "NodeSocketFloat", default=10.0, min_value=3.0, max_value=40.0,
              description="Длина одного отрезка шипа/паза при прерывистом режиме, мм.")
    add_input(tree, "Стык_промежуток_мм", "NodeSocketFloat", default=10.0, min_value=3.0, max_value=40.0,
              description="Длина промежутка между отрезками при прерывистом режиме, мм.")
    add_input(tree, "Стык_ребро_вкл", "NodeSocketFloat", default=0.0, min_value=0.0, max_value=1.0,
              description="1 = добавить местное утолщение стенки (ребро жёсткости) вдоль шва с "
                           "внутренней стороны каждой детали, для усиления соединения.")
    add_input(tree, "Стык_ребро_высота_мм", "NodeSocketFloat", default=1.5, min_value=0.5, max_value=6.0,
              description="Глубина утолщения (ребра) вовнутрь детали от плоскости среза, мм "
                           "(небольшая - не должна приближаться к толщине стенки).")
    add_input(tree, "Стык_ребро_ширина_мм", "NodeSocketFloat", default=3.0, min_value=1.5, max_value=10.0,
              description="Ширина утолщения (ребра) поперёк шва, мм.")
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

    # -- трапециевидный/прямоугольный профиль шипа: используем встроенный
    # примитив GeometryNodeCurvePrimitiveQuadrilateral (mode=TRAPEZOID),
    # который в 5.1 напрямую даёт "Bottom Width"/"Top Width"/"Height" -
    # НАМНОГО проще самодельного построения через MeshCircle, как было
    # у прежнего треугольного профиля. Проверено отдельным тестом
    # (probe): донор кладёт НИЗ (широкое основание) на Y=-height/2, ВЕРХ
    # (узкий конец) на Y=+height/2, симметрично по X. Переворачиваем и
    # сдвигаем в конвенцию проекта (см. комментарий выше про профиль X/Y
    # у Curve to Mesh): основание -> Y=0 (на плоскости среза), узкий
    # конец -> Y=-height (в сторону нормали разреза, "выдавливается" в
    # соседнюю деталь). Скос=0 -> Top Width=Bottom Width -> прямоугольное
    # (квадратное) сечение; скос>0 -> трапеция.
    def trap_profile(num_prefix, base_w_socket, top_w_socket, height_socket, x, y, label_suffix=""):
        quad = add_node(tree, "GeometryNodeCurvePrimitiveQuadrilateral", num_prefix + "q",
                         "донор: трапеция/прямоугольник" + label_suffix, x, y, mode='TRAPEZOID')
        tree.links.new(base_w_socket, in_sock(quad, "Bottom Width"))
        tree.links.new(top_w_socket, in_sock(quad, "Top Width"))
        tree.links.new(height_socket, in_sock(quad, "Height"))
        in_sock(quad, "Offset").default_value = 0.0

        halfh = add_node(tree, "ShaderNodeMath", num_prefix + "hh", "height/2",
                          x + 260, y - 150, operation='MULTIPLY')
        tree.links.new(height_socket, in_sock(halfh, "Value"))
        in_sock(halfh, "Value_001").default_value = 0.5
        neg_halfh = add_node(tree, "ShaderNodeMath", num_prefix + "nh", "-height/2",
                              x + 520, y - 150, operation='MULTIPLY')
        link(tree, halfh, "Value", neg_halfh, "Value")
        in_sock(neg_halfh, "Value_001").default_value = -1.0
        tvec = add_node(tree, "ShaderNodeCombineXYZ", num_prefix + "tv",
                         "смещение = (0,-height/2,0)", x + 780, y - 150)
        link(tree, neg_halfh, "Value", tvec, "Y")

        xf = add_node(tree, "GeometryNodeTransform", num_prefix + "xf",
                       "перевернуть Y + сдвинуть (низ->Y=0, верх->Y=-height)" + label_suffix,
                       x + 1040, y)
        link(tree, quad, "Curve", xf, "Geometry")
        in_sock(xf, "Scale").default_value = (1.0, -1.0, 1.0)
        link(tree, tvec, "Vector", xf, "Translation")

        fillet = add_node(tree, "GeometryNodeFilletCurve", num_prefix + "fc",
                           "скругление углов профиля" + label_suffix, x + 1300, y, mode='POLY')
        link(tree, xf, "Geometry", fillet, "Curve")
        tree.links.new(GI("Кромка_радиус_мм"), in_sock(fillet, "Radius"))
        in_sock(fillet, "Count").default_value = 3

        nodes_list = [quad, halfh, neg_halfh, tvec, xf, fillet]
        return fillet, nodes_list

    # -- размеры: шип точный, паз = шип + зазор (по ширине с обеих
    # сторон и по высоте) --
    skew2 = add_node(tree, "ShaderNodeMath", "5a.sk2", "Стык_скос_мм * 2",
                      1600, -600, operation='MULTIPLY')
    tree.links.new(GI("Стык_скос_мм"), in_sock(skew2, "Value"))
    in_sock(skew2, "Value_001").default_value = 2.0

    ridge_top_w0 = add_node(tree, "ShaderNodeMath", "5a.rtw0",
                             "верх_шипа = ширина_основания - скос*2", 1860, -600,
                             operation='SUBTRACT')
    tree.links.new(GI("Стык_ширина_мм"), in_sock(ridge_top_w0, "Value"))
    link(tree, skew2, "Value", ridge_top_w0, "Value_001")
    ridge_top_w = add_node(tree, "ShaderNodeMath", "5a.rtw",
                            "верх_шипа = max(..., 0.3мм) - не даём выродиться",
                            2120, -600, operation='MAXIMUM')
    link(tree, ridge_top_w0, "Value", ridge_top_w, "Value")
    in_sock(ridge_top_w, "Value_001").default_value = 0.3

    zazor2 = add_node(tree, "ShaderNodeMath", "5a.zz2", "Стык_зазор_мм * 2",
                       1600, -750, operation='MULTIPLY')
    tree.links.new(GI("Стык_зазор_мм"), in_sock(zazor2, "Value"))
    in_sock(zazor2, "Value_001").default_value = 2.0

    groove_base_w = add_node(tree, "ShaderNodeMath", "5a.gbw",
                              "низ_паза = ширина_основания_шипа + зазор*2", 2380, -650,
                              operation='ADD')
    tree.links.new(GI("Стык_ширина_мм"), in_sock(groove_base_w, "Value"))
    link(tree, zazor2, "Value", groove_base_w, "Value_001")
    groove_top_w = add_node(tree, "ShaderNodeMath", "5a.gtw",
                             "верх_паза = верх_шипа + зазор*2", 2380, -800, operation='ADD')
    link(tree, ridge_top_w, "Value", groove_top_w, "Value")
    link(tree, zazor2, "Value", groove_top_w, "Value_001")
    groove_height = add_node(tree, "ShaderNodeMath", "5a.gh",
                              "высота_паза = высота_шипа + зазор", 2380, -950, operation='ADD')
    tree.links.new(GI("Стык_высота_мм"), in_sock(groove_height, "Value"))
    tree.links.new(GI("Стык_зазор_мм"), in_sock(groove_height, "Value_001"))

    frameW = make_frame(
        tree, "3b. РАЗМЕРЫ ПРОФИЛЯ (скос=0 -> прямоугольное/квадратное сечение, "
        "скос>0 -> трапеция; паз = шип + зазор)",
        [skew2, ridge_top_w0, ridge_top_w, zazor2, groove_base_w, groove_top_w, groove_height])

    ridge_fillet, ridge_nodes = trap_profile(
        "5a.rp", GI("Стык_ширина_мм"), out_sock(ridge_top_w, "Value"), GI("Стык_высота_мм"),
        1600, -1100, " (шип)")
    groove_fillet, groove_nodes = trap_profile(
        "5a.gp", out_sock(groove_base_w, "Value"), out_sock(groove_top_w, "Value"),
        out_sock(groove_height, "Value"), 1600, -1500, " (паз)")

    frameProfiles = make_frame(tree, "3c. ПРОФИЛИ (шип = точный размер, паз = шип+зазор)",
                                ridge_nodes + groove_nodes)

    # ------------------------------------------------------------------
    # 3d. СПЛОШНОЙ РЕЖИМ: выдавить профиль вдоль ВСЕГО контура разреза
    # (один целый замкнутый "бублик"-тело - НЕ Boolean по позициям,
    # поэтому нет риска "касательного" краевого дефекта).
    # ------------------------------------------------------------------
    c2m_ridge_cont = add_node(tree, "GeometryNodeCurveToMesh", "5a.c2mRc",
                               "шип (сплошной) = профиль x весь контур разреза", 2300, -1100)
    link(tree, b03, "Curve", c2m_ridge_cont, "Curve")
    link(tree, ridge_fillet, "Curve", c2m_ridge_cont, "Profile Curve")

    c2m_groove_cont = add_node(tree, "GeometryNodeCurveToMesh", "5a.c2mGc",
                                "паз (сплошной) = профиль x весь контур разреза", 2300, -1500)
    link(tree, b03, "Curve", c2m_groove_cont, "Curve")
    link(tree, groove_fillet, "Curve", c2m_groove_cont, "Profile Curve")

    frameSweepCont = make_frame(tree, "3d. СПЛОШНОЙ РЕЖИМ (Curve to Mesh по всему контуру)",
                                 [c2m_ridge_cont, c2m_groove_cont])

    # ------------------------------------------------------------------
    # 3e. ПРЕРЫВИСТЫЙ РЕЖИМ: сэмплируем точки вдоль контура с шагом
    # (сегмент+промежуток), в каждой точке ставим короткий (длина=
    # сегмент) отрезок-призму того же сечения, с закрытыми торцами
    # (Fill Caps) - т.к. точка отбора уже находится каждые (сегмент+
    # промежуток) мм, зазор между соседними отрезками получается сам
    # собой равным промежутку, без обрезки готового сплошного тела
    # (которая потребовала бы повторной "починки" открытых краёв - тот
    # самый ненадёжный приём, отвергнутый ранее в Группе 4).
    # ------------------------------------------------------------------
    period = add_node(tree, "ShaderNodeMath", "5a.per", "период = сегмент + промежуток",
                       1600, -1800, operation='ADD')
    tree.links.new(GI("Стык_сегмент_мм"), in_sock(period, "Value"))
    tree.links.new(GI("Стык_промежуток_мм"), in_sock(period, "Value_001"))

    pts = add_node(tree, "GeometryNodeCurveToPoints", "5a.pts",
                    "точки вдоль контура с шагом = период", 1860, -1800, mode='LENGTH')
    link(tree, b03, "Curve", pts, "Curve")
    link(tree, period, "Value", pts, "Length")

    half_seg = add_node(tree, "ShaderNodeMath", "5a.hs", "сегмент/2", 1600, -1950,
                         operation='MULTIPLY')
    tree.links.new(GI("Стык_сегмент_мм"), in_sock(half_seg, "Value"))
    in_sock(half_seg, "Value_001").default_value = 0.5
    neg_half_seg = add_node(tree, "ShaderNodeMath", "5a.nhs", "-сегмент/2", 1860, -1950,
                             operation='MULTIPLY')
    link(tree, half_seg, "Value", neg_half_seg, "Value")
    in_sock(neg_half_seg, "Value_001").default_value = -1.0
    seg_start = add_node(tree, "ShaderNodeCombineXYZ", "5a.ss", "(0,0,-сегмент/2)", 2120, -1950)
    link(tree, neg_half_seg, "Value", seg_start, "Z")
    seg_end = add_node(tree, "ShaderNodeCombineXYZ", "5a.se", "(0,0,+сегмент/2)", 2120, -2100)
    link(tree, half_seg, "Value", seg_end, "Z")
    seg_line = add_node(tree, "GeometryNodeCurvePrimitiveLine", "5a.sl",
                         "короткий прямой путь вдоль локальной оси Z, длина=сегмент",
                         2380, -2000)
    link(tree, seg_start, "Vector", seg_line, "Start")
    link(tree, seg_end, "Vector", seg_line, "End")

    ridge_prism = add_node(tree, "GeometryNodeCurveToMesh", "5a.rpr",
                            "отрезок шипа (с закрытыми торцами)", 2640, -1900)
    link(tree, seg_line, "Curve", ridge_prism, "Curve")
    link(tree, ridge_fillet, "Curve", ridge_prism, "Profile Curve")
    in_sock(ridge_prism, "Fill Caps").default_value = True

    groove_prism = add_node(tree, "GeometryNodeCurveToMesh", "5a.gpr",
                             "отрезок паза (с закрытыми торцами)", 2640, -2150)
    link(tree, seg_line, "Curve", groove_prism, "Curve")
    link(tree, groove_fillet, "Curve", groove_prism, "Profile Curve")
    in_sock(groove_prism, "Fill Caps").default_value = True

    ridge_inst = add_node(tree, "GeometryNodeInstanceOnPoints", "5a.ri",
                           "отрезки шипа на всех точках", 2900, -1900)
    link(tree, pts, "Points", ridge_inst, "Points")
    link(tree, ridge_prism, "Mesh", ridge_inst, "Instance")
    link(tree, pts, "Rotation", ridge_inst, "Rotation")
    ridge_real = add_node(tree, "GeometryNodeRealizeInstances", "5a.rr",
                           "реализовать отрезки шипа в единый меш", 3160, -1900)
    link(tree, ridge_inst, "Instances", ridge_real, "Geometry")

    groove_inst = add_node(tree, "GeometryNodeInstanceOnPoints", "5a.gi",
                            "отрезки паза на всех точках", 2900, -2150)
    link(tree, pts, "Points", groove_inst, "Points")
    link(tree, groove_prism, "Mesh", groove_inst, "Instance")
    link(tree, pts, "Rotation", groove_inst, "Rotation")
    groove_real = add_node(tree, "GeometryNodeRealizeInstances", "5a.gr",
                            "реализовать отрезки паза в единый меш", 3160, -2150)
    link(tree, groove_inst, "Instances", groove_real, "Geometry")

    frameSweepSeg = make_frame(
        tree, "3e. ПРЕРЫВИСТЫЙ РЕЖИМ (точки с шагом=период -> короткие капсулированные "
        "отрезки-инстансы, зазор между ними = сам шаг минус длина отрезка)",
        [period, pts, half_seg, neg_half_seg, seg_start, seg_end, seg_line,
         ridge_prism, groove_prism, ridge_inst, ridge_real, groove_inst, groove_real])

    # -- переключатель сплошной/прерывистый --
    segs_on = add_node(tree, "FunctionNodeCompare", "5a.sgon", "Стык_сегменты_вкл > 0.5?",
                        2380, -1650, data_type='FLOAT', operation='GREATER_THAN')
    tree.links.new(GI("Стык_сегменты_вкл"), in_sock(segs_on, "A"))
    in_sock(segs_on, "B").default_value = 0.5

    c2m_ridge_sw = add_node(tree, "GeometryNodeSwitch", "5a.rsw", "шип: сплошной или прерывистый?",
                             3420, -1300, input_type='GEOMETRY')
    link(tree, segs_on, "Result", c2m_ridge_sw, "Switch_001")
    link(tree, c2m_ridge_cont, "Mesh", c2m_ridge_sw, "False_006")
    link(tree, ridge_real, "Geometry", c2m_ridge_sw, "True_006")

    c2m_groove_sw = add_node(tree, "GeometryNodeSwitch", "5a.gsw", "паз: сплошной или прерывистый?",
                              3420, -1600, input_type='GEOMETRY')
    link(tree, segs_on, "Result", c2m_groove_sw, "Switch_001")
    link(tree, c2m_groove_cont, "Mesh", c2m_groove_sw, "False_006")
    link(tree, groove_real, "Geometry", c2m_groove_sw, "True_006")

    frameSwSeg = make_frame(tree, "3f. ВЫБОР: сплошной или прерывистый режим",
                             [segs_on, c2m_ridge_sw, c2m_groove_sw])

    c2m_ridge = out_sock(c2m_ridge_sw, "Output_006")
    c2m_groove = out_sock(c2m_groove_sw, "Output_006")

    # ------------------------------------------------------------------
    # 3g. РЕБРО ЖЁСТКОСТИ (опционально): местное утолщение стенки вдоль
    # шва С ВНУТРЕННЕЙ СТОРОНЫ каждой детали (не со стороны шипа/паза,
    # а В ГЛУБЬ детали, противоположно шипу) - шире шипа, но не заходит
    # на внешнюю (видимую) сторону разреза, добавляется симметрично
    # UNION-ом в ОБЕ детали (это не парная посадка шип<->паз, а
    # независимое усиление каждой стороны). Прямоугольный профиль:
    # Низ получает ребро в сторону от шипа (Y>0 в конвенции профиля),
    # Верх - глубже в свою сторону (Y<0, за пределы паза).
    # ------------------------------------------------------------------
    rib_w = GI("Стык_ребро_ширина_мм")
    rib_h = GI("Стык_ребро_высота_мм")

    # -- Низ: строим ребро в СТАНДАРТНОЙ конвенции trap_profile (основание
    # -> Y=0, узкий конец -> Y=-rib_h, как у шипа), затем ЯВНО переворачиваем
    # отдельным Transform (Scale Y=-1) в противоположную от шипа сторону
    # (Y=0..+rib_h) - вместо того, чтобы полагаться на непроверенное
    # поведение примитива Quadrilateral с ОТРИЦАТЕЛЬНЫМ Height (риск: могло
    # обрезаться/вырождаться по-другому, что и давало всплеск дефектов).
    rib_low_fillet0, rib_low_nodes0 = trap_profile(
        "5a.rlp", rib_w, rib_w, rib_h, 1600, -2450,
        " (ребро, Низ, база)")
    rib_low_flip = add_node(tree, "GeometryNodeTransform", "5a.rlf",
                             "развернуть ребро Низа в сторону от шипа (Y>0)", 1900, -2450)
    link(tree, rib_low_fillet0, "Curve", rib_low_flip, "Geometry")
    in_sock(rib_low_flip, "Scale").default_value = (1.0, -1.0, 1.0)
    rib_low_fillet = rib_low_flip
    rib_low_nodes = rib_low_nodes0 + [rib_low_flip]

    # -- Верх: ребро строим в той же стандартной конвенции (Y=0..-rib_h),
    # затем СДВИГАЕМ отдельным Transform на -groove_height, чтобы оно легло
    # ЗА пределами уже вырезанного паза (паз занимает Y=0..-groove_height),
    # а не поверх/внутри него - иначе UNION ребра заново "затыкал" бы
    # только что прорезанную DIFFERENCE-ом полость паза (само-пересечение).
    rib_high_fillet0, rib_high_nodes0 = trap_profile(
        "5a.rhp", rib_w, rib_w, rib_h, 1600, -2750, " (ребро, Верх, база)")
    neg_groove_h = add_node(tree, "ShaderNodeMath", "5a.ngh", "-высота_паза",
                             1900, -2650, operation='MULTIPLY')
    link(tree, groove_height, "Value", neg_groove_h, "Value")
    in_sock(neg_groove_h, "Value_001").default_value = -1.0
    rib_high_shift_vec = add_node(tree, "ShaderNodeCombineXYZ", "5a.rhsv",
                                   "сдвиг = (0,-высота_паза,0)", 2100, -2650)
    link(tree, neg_groove_h, "Value", rib_high_shift_vec, "Y")
    rib_high_shift = add_node(tree, "GeometryNodeTransform", "5a.rhs",
                               "сдвинуть ребро Верха за пределы паза", 2200, -2750)
    link(tree, rib_high_fillet0, "Curve", rib_high_shift, "Geometry")
    link(tree, rib_high_shift_vec, "Vector", rib_high_shift, "Translation")
    rib_high_fillet = rib_high_shift
    rib_high_nodes = rib_high_nodes0 + [neg_groove_h, rib_high_shift_vec, rib_high_shift]

    c2m_rib_low = add_node(tree, "GeometryNodeCurveToMesh", "5a.c2mRL",
                            "ребро Низ (сплошное, по контуру)", 2300, -2450)
    link(tree, b03, "Curve", c2m_rib_low, "Curve")
    link(tree, rib_low_fillet, "Geometry", c2m_rib_low, "Profile Curve")

    c2m_rib_high = add_node(tree, "GeometryNodeCurveToMesh", "5a.c2mRH",
                             "ребро Верх (сплошное, по контуру)", 2300, -2750)
    link(tree, b03, "Curve", c2m_rib_high, "Curve")
    link(tree, rib_high_fillet, "Geometry", c2m_rib_high, "Profile Curve")

    rib_on = add_node(tree, "FunctionNodeCompare", "5a.ribon", "Стык_ребро_вкл > 0.5?",
                       2600, -2600, data_type='FLOAT', operation='GREATER_THAN')
    tree.links.new(GI("Стык_ребро_вкл"), in_sock(rib_on, "A"))
    in_sock(rib_on, "B").default_value = 0.5
    empty_rib = add_node(tree, "GeometryNodeMeshCube", "5a.ribe", "пусто (ребро выкл.)",
                          2300, -2900)
    in_sock(empty_rib, "Size").default_value = (0.0, 0.0, 0.0)
    rib_low_sw = add_node(tree, "GeometryNodeSwitch", "5a.rlsw", "ребро Низ вкл?", 2900, -2450,
                           input_type='GEOMETRY')
    link(tree, rib_on, "Result", rib_low_sw, "Switch_001")
    link(tree, empty_rib, "Mesh", rib_low_sw, "False_006")
    link(tree, c2m_rib_low, "Mesh", rib_low_sw, "True_006")
    rib_high_sw = add_node(tree, "GeometryNodeSwitch", "5a.rhsw", "ребро Верх вкл?", 2900, -2750,
                            input_type='GEOMETRY')
    link(tree, rib_on, "Result", rib_high_sw, "Switch_001")
    link(tree, empty_rib, "Mesh", rib_high_sw, "False_006")
    link(tree, c2m_rib_high, "Mesh", rib_high_sw, "True_006")

    frameRib = make_frame(
        tree, "3g. РЕБРО ЖЁСТКОСТИ (опционально, Стык_ребро_вкл=0 отключает) - "
        "утолщение стенки с внутренней стороны шва, в обе детали симметрично",
        rib_low_nodes + rib_high_nodes +
        [c2m_rib_low, c2m_rib_high, rib_on, empty_rib, rib_low_sw, rib_high_sw])

    # -- Часть B (Низ) + шип + ребро (UNION); Часть A (Верх) - паз, + ребро (DIFFERENCE паза, UNION ребра) --
    # ВАЖНО: у GeometryNodeMeshBoolean сокет "Mesh 2" - МУЛЬТИ-ВХОД (list),
    # оба/все операнда UNION подаются раздельными линками именно в него
    # (см. n10/n11 выше) - это настоящий CSG-буллин, а НЕ Join+Merge By
    # Distance (тот годится только для сшивки НЕПЕРЕСЕКАЮЩИХСЯ кусков по
    # общему шву, как в Группе 3 - здесь же тела шипа/ребра ОБЪЁМНО
    # пересекаются с телом Низа, простое сваривание вершин оставило бы
    # внутренние задвоенные грани).
    unionB0 = add_node(tree, "GeometryNodeMeshBoolean", "5a.j2", "Низ UNION шип UNION ребро",
                        3420, -300, operation='UNION')
    tree.links.new(n13.outputs["Mesh"], in_sock(unionB0, "Mesh 2"))
    tree.links.new(c2m_ridge, in_sock(unionB0, "Mesh 2"))
    tree.links.new(out_sock(rib_low_sw, "Output_006"), in_sock(unionB0, "Mesh 2"))
    unionB = add_node(tree, "GeometryNodeMergeByDistance", "5a.j2m",
                       "сварить близкие вершины после буллина (0.01мм)", 3680, -300)
    link(tree, unionB0, "Mesh", unionB, "Geometry")
    in_sock(unionB, "Distance").default_value = 0.01

    diffA0 = add_node(tree, "GeometryNodeMeshBoolean", "5a.j3", "Верх DIFFERENCE паз",
                       3420, 250, operation='DIFFERENCE')
    tree.links.new(n12.outputs["Mesh"], in_sock(diffA0, "Mesh 1"))
    tree.links.new(c2m_groove, in_sock(diffA0, "Mesh 2"))
    diffA1 = add_node(tree, "GeometryNodeMeshBoolean", "5a.j3b", "+ ребро (UNION)",
                       3680, 250, operation='UNION')
    tree.links.new(diffA0.outputs["Mesh"], in_sock(diffA1, "Mesh 2"))
    tree.links.new(out_sock(rib_high_sw, "Output_006"), in_sock(diffA1, "Mesh 2"))
    diffA = add_node(tree, "GeometryNodeMergeByDistance", "5a.j3m",
                      "сварить близкие вершины после буллина (0.01мм)", 3940, 250)
    link(tree, diffA1, "Mesh", diffA, "Geometry")
    in_sock(diffA, "Distance").default_value = 0.01

    frameJoin = make_frame(tree, "3h. UNION шип+ребро в Низ / DIFFERENCE паза + UNION ребра из Верх + сварка",
                            [unionB0, unionB, diffA0, diffA1, diffA])

    # -- переключатель: Стык_вкл=0 -> обычный плоский срез (без шипа/паза/ребра) --
    swA = add_node(tree, "GeometryNodeSwitch", "5a.swA", "Часть_A: с пазом или плоская?",
                    3900, 250, input_type='GEOMETRY')
    joint_on = add_node(tree, "FunctionNodeCompare", "5a.jon", "Стык_вкл > 0.5?", 3420, 500,
                         data_type='FLOAT', operation='GREATER_THAN')
    tree.links.new(GI("Стык_вкл"), in_sock(joint_on, "A"))
    in_sock(joint_on, "B").default_value = 0.5
    link(tree, joint_on, "Result", swA, "Switch_001")
    tree.links.new(n12.outputs["Mesh"], in_sock(swA, "False_006"))
    link(tree, diffA, "Geometry", swA, "True_006")

    swB = add_node(tree, "GeometryNodeSwitch", "5a.swB", "Часть_B: с шипом или плоская?",
                    4180, -300, input_type='GEOMETRY')
    link(tree, joint_on, "Result", swB, "Switch_001")
    tree.links.new(n13.outputs["Mesh"], in_sock(swB, "False_006"))
    link(tree, unionB, "Geometry", swB, "True_006")

    frameSwitch = make_frame(tree, "3i. Стык_вкл=0 -> вернуть обычный плоский срез без шипа/паза",
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
              description="1 = шип/паз (трапециевидного или прямоугольного сечения) по периметру "
                           "разреза (и Перед, и Зад). 0 = обычный плоский срез без шипа.")
    add_input(tree, "Стык_высота_мм", "NodeSocketFloat", default=1.2, min_value=0.3, max_value=3.0,
              description="Высота шипа по нормали к плоскости разреза, мм.")
    add_input(tree, "Стык_ширина_мм", "NodeSocketFloat", default=2.0, min_value=0.5, max_value=6.0,
              description="Ширина основания шипа, мм.")
    add_input(tree, "Стык_скос_мм", "NodeSocketFloat", default=0.4, min_value=0.0, max_value=2.0,
              description="Скос с каждой стороны (0=прямоугольное/квадратное сечение, "
                           ">0=трапециевидное), мм.")
    add_input(tree, "Стык_зазор_мм", "NodeSocketFloat", default=0.1, min_value=0.0, max_value=1.0,
              description="Зазор паз<->шип (клей, допуски печати), мм.")
    add_input(tree, "Кромка_радиус_мм", "NodeSocketFloat", default=0.2, min_value=0.05, max_value=1.0,
              description="Скругление углов сечения шипа (Fillet Curve).")
    add_input(tree, "Стык_сегменты_вкл", "NodeSocketFloat", default=0.0, min_value=0.0, max_value=1.0,
              description="0 = шип/паз сплошной; 1 = прерывистый (Стык_сегмент_мм/"
                           "Стык_промежуток_мм).")
    add_input(tree, "Стык_сегмент_мм", "NodeSocketFloat", default=10.0, min_value=3.0, max_value=40.0)
    add_input(tree, "Стык_промежуток_мм", "NodeSocketFloat", default=10.0, min_value=3.0, max_value=40.0)
    add_input(tree, "Стык_ребро_вкл", "NodeSocketFloat", default=0.0, min_value=0.0, max_value=1.0,
              description="1 = добавить местное утолщение стенки (ребро жёсткости) вдоль шва.")
    add_input(tree, "Стык_ребро_высота_мм", "NodeSocketFloat", default=1.5, min_value=0.5, max_value=6.0)
    add_input(tree, "Стык_ребро_ширина_мм", "NodeSocketFloat", default=3.0, min_value=1.5, max_value=10.0)

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
    def wire_cut_joint(cut_grp):
        tree.links.new(GI("Стык_вкл"), cut_grp.inputs["Стык_вкл"])
        tree.links.new(GI("Стык_высота_мм"), cut_grp.inputs["Стык_высота_мм"])
        tree.links.new(GI("Стык_ширина_мм"), cut_grp.inputs["Стык_ширина_мм"])
        tree.links.new(GI("Стык_скос_мм"), cut_grp.inputs["Стык_скос_мм"])
        tree.links.new(GI("Стык_зазор_мм"), cut_grp.inputs["Стык_зазор_мм"])
        tree.links.new(GI("Кромка_радиус_мм"), cut_grp.inputs["Кромка_радиус_мм"])
        tree.links.new(GI("Стык_сегменты_вкл"), cut_grp.inputs["Стык_сегменты_вкл"])
        tree.links.new(GI("Стык_сегмент_мм"), cut_grp.inputs["Стык_сегмент_мм"])
        tree.links.new(GI("Стык_промежуток_мм"), cut_grp.inputs["Стык_промежуток_мм"])
        tree.links.new(GI("Стык_ребро_вкл"), cut_grp.inputs["Стык_ребро_вкл"])
        tree.links.new(GI("Стык_ребро_высота_мм"), cut_grp.inputs["Стык_ребро_высота_мм"])
        tree.links.new(GI("Стык_ребро_ширина_мм"), cut_grp.inputs["Стык_ребро_ширина_мм"])

    cutF = _grp(tree, cut_tree, "5.15", "Разрез: Перед", 800, 300)
    tree.links.new(GI("Перед"), cutF.inputs["Geometry"])
    tree.links.new(n11.outputs["Vector"], cutF.inputs["Точка_на_плоскости"])
    tree.links.new(n14.outputs["Vector"], cutF.inputs["Нормаль_плоскости"])
    wire_cut_joint(cutF)

    cutB = _grp(tree, cut_tree, "5.16", "Разрез: Зад", 800, 100)
    tree.links.new(GI("Зад"), cutB.inputs["Geometry"])
    tree.links.new(n11.outputs["Vector"], cutB.inputs["Точка_на_плоскости"])
    tree.links.new(n14.outputs["Vector"], cutB.inputs["Нормаль_плоскости"])
    wire_cut_joint(cutB)

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
