# -*- coding: utf-8 -*-
"""
ГРУППА 3 — «NK.3_Оболочка» (Shell / Loft / Split)
====================================================
Превращает облако точек-сечений из Группы 2 в сплошную ПЕЧАТАЕМУЮ
оболочку заданной толщины стенки, с подрезкой по высоте и делением
на переднюю/заднюю половины.

Состоит из 4 вложенных groups (снизу вверх):

  NK.3z_Сетка_по_индексам  - переиспользуемый "конструктор сетки":
      берёт прямоугольный диапазон (строки х столбцы) из облака точек
      N-колец х M-точек и строит меш-сетку той же формы, где позиция
      каждой вершины взята из облака по вычисленному индексу
      (Sample Index). Столбец автоматически "заворачивается" по
      модулю M - это даёт возможность как замкнуть кольцо целиком,
      так и вырезать открытую полосу для половины оболочки.

  NK.3y_Мост - переиспользуемый "мостик": берёт два одинаковых по
      длине набора точек (контур A и контур B) и строит между ними
      полосу quad-граней - ровно один шов оболочки (верх/низ/бок).

  NK.3a_Половина_оболочки - одна половина (перед ИЛИ зад): внешняя
      поверхность + внутренняя (смещённая внутрь на толщину стенки,
      с перевёрнутыми нормалями) + 4 моста (низ, верх, левый шов,
      правый шов) сшивают их в ЗАМКНУТЫЙ (watertight) объём -
      корректный вход для 3D-печати.

  NK.3_Оболочка - верхний уровень: подрезка колец по высоте (Group
      Input Профиль_точки из Группы 2), расчёт внутренних точек,
      два вызова NK.3a_Половина_оболочки (перёд/зад).

ВАЖНО про толщину: внутренняя поверхность = внешняя точка минус
направление 'dir' (то самое единичное радиальное направление из
Группы 2), умноженное на толщину. Это НЕ идеальная эквидистанта
(строгий offset-surface), а её лёгкое приближение вдоль радиуса -
для тонкой стенки (2-4мм) на плавной форме голени разница
пренебрежимо мала. Подробности - в docs/03_group3_shell.md.

Запуск:
    blender --background --python scripts/build_group3_shell.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from nodes_common import (
    new_group, add_input, add_output, add_node, make_frame, link,
    out_sock, in_sock,
)

SAMPLER_NAME = "NK.3z_Сетка_по_индексам"
BRIDGE_NAME = "NK.3y_Мост"
HALF_NAME = "NK.3a_Половина_оболочки"
SHELL_NAME = "NK.3_Оболочка"


def named_attr(tree, num, label, x, y, attr_name, data_type):
    n = add_node(tree, "GeometryNodeInputNamedAttribute", num, label, x, y,
                 data_type=data_type)
    in_sock(n, "Name").default_value = attr_name
    return n


# ----------------------------------------------------------------------
# 1) NK.3z_Сетка_по_индексам
# ----------------------------------------------------------------------
def build_sampler():
    tree = new_group(SAMPLER_NAME)
    add_input(tree, "Точки", "NodeSocketGeometry",
              description="Источник: облако из N рядов x M_источника колонок, "
                           "индекс точки = ряд*M_источника + колонка.")
    add_input(tree, "M_источника", "NodeSocketInt", default=32, min_value=3, max_value=256)
    add_input(tree, "Row_от", "NodeSocketInt", default=0, min_value=0, max_value=4096)
    add_input(tree, "Row_до", "NodeSocketInt", default=0, min_value=0, max_value=4096)
    add_input(tree, "Col_от", "NodeSocketInt", default=0, min_value=-4096, max_value=4096)
    add_input(tree, "Col_до", "NodeSocketInt", default=0, min_value=-4096, max_value=4096)
    add_output(tree, "Mesh", "NodeSocketGeometry",
               "Сетка (Row_до-Row_от+1) x (Col_до-Col_от+1), позиции из 'Точки'.")

    gin = tree.nodes.new("NodeGroupInput")
    gin.name = "3z.01 Вход"; gin.label = "3z.01 Входные параметры"; gin.location = (-300, 0)
    gout = tree.nodes.new("NodeGroupOutput")
    gout.name = "3z.99 Выход"; gout.label = "3z.99 Выход"; gout.location = (2400, 0)

    def GI(name):
        return gin.outputs[name]

    n02 = add_node(tree, "ShaderNodeMath", "3z.02", "colspan = Col_до-Col_от",
                    0, 300, operation='SUBTRACT')
    tree.links.new(GI("Col_до"), in_sock(n02, "Value"))
    tree.links.new(GI("Col_от"), in_sock(n02, "Value_001"))

    n03 = add_node(tree, "ShaderNodeMath", "3z.03", "num_cols = colspan+1",
                    260, 300, operation='ADD')
    link(tree, n02, "Value", n03, "Value")
    in_sock(n03, "Value_001").default_value = 1.0

    n04 = add_node(tree, "FunctionNodeFloatToInt", "3z.04", "num_cols -> Int", 520, 300)
    link(tree, n03, "Value", n04, "Float")

    n05 = add_node(tree, "ShaderNodeMath", "3z.05", "rowspan = Row_до-Row_от",
                    0, 150, operation='SUBTRACT')
    tree.links.new(GI("Row_до"), in_sock(n05, "Value"))
    tree.links.new(GI("Row_от"), in_sock(n05, "Value_001"))

    n06 = add_node(tree, "ShaderNodeMath", "3z.06", "num_rows = rowspan+1",
                    260, 150, operation='ADD')
    link(tree, n05, "Value", n06, "Value")
    in_sock(n06, "Value_001").default_value = 1.0

    n07 = add_node(tree, "FunctionNodeFloatToInt", "3z.07", "num_rows -> Int", 520, 150)
    link(tree, n06, "Value", n07, "Float")

    n08 = add_node(tree, "GeometryNodeMeshGrid", "3z.08",
                    "Сетка-донор топологии (Verts X=num_rows, Y=num_cols)", 780, 250)
    link(tree, n07, "Integer", n08, "Vertices X")
    link(tree, n04, "Integer", n08, "Vertices Y")
    in_sock(n08, "Size X").default_value = 1.0
    in_sock(n08, "Size Y").default_value = 1.0

    frameA = make_frame(tree, "A. РАЗМЕР СЕТКИ-ДОНОРА", [n02, n03, n04, n05, n06, n07, n08])

    n09 = add_node(tree, "GeometryNodeInputIndex", "3z.09", "index каждой вершины сетки", 0, -100)

    n10 = add_node(tree, "ShaderNodeMath", "3z.10", "index / num_cols", 260, -100, operation='DIVIDE')
    link(tree, n09, "Index", n10, "Value")
    link(tree, n04, "Integer", n10, "Value_001")

    n11 = add_node(tree, "ShaderNodeMath", "3z.11", "local_row = floor(...)", 520, -100, operation='FLOOR')
    link(tree, n10, "Value", n11, "Value")

    n12 = add_node(tree, "ShaderNodeMath", "3z.12", "local_row * num_cols", 780, -180, operation='MULTIPLY')
    link(tree, n11, "Value", n12, "Value")
    link(tree, n04, "Integer", n12, "Value_001")

    n13 = add_node(tree, "ShaderNodeMath", "3z.13", "local_col = index - local_row*num_cols",
                    1040, -100, operation='SUBTRACT')
    link(tree, n09, "Index", n13, "Value")
    link(tree, n12, "Value", n13, "Value_001")

    frameB = make_frame(tree, "B. (local_row, local_col) ИЗ ИНДЕКСА ВЕРШИНЫ ДОНОРА",
                         [n09, n10, n11, n12, n13])

    n14 = add_node(tree, "ShaderNodeMath", "3z.14", "src_row = Row_от + local_row",
                    1300, 0, operation='ADD')
    tree.links.new(GI("Row_от"), in_sock(n14, "Value"))
    link(tree, n11, "Value", n14, "Value_001")

    n15 = add_node(tree, "ShaderNodeMath", "3z.15", "src_col_raw = Col_от + local_col",
                    1300, -150, operation='ADD')
    tree.links.new(GI("Col_от"), in_sock(n15, "Value"))
    link(tree, n13, "Value", n15, "Value_001")

    n16 = add_node(tree, "ShaderNodeMath", "3z.16", "src_col = src_col_raw mod M_источника "
                    "(заворот по кольцу)", 1560, -150, operation='MODULO')
    link(tree, n15, "Value", n16, "Value")
    tree.links.new(GI("M_источника"), in_sock(n16, "Value_001"))

    n17 = add_node(tree, "ShaderNodeMath", "3z.17", "src_row * M_источника",
                    1560, 0, operation='MULTIPLY')
    link(tree, n14, "Value", n17, "Value")
    tree.links.new(GI("M_источника"), in_sock(n17, "Value_001"))

    n18 = add_node(tree, "ShaderNodeMath", "3z.18", "src_index = src_row*M + src_col",
                    1820, -50, operation='ADD')
    link(tree, n17, "Value", n18, "Value")
    link(tree, n16, "Value", n18, "Value_001")

    n19 = add_node(tree, "FunctionNodeFloatToInt", "3z.19", "src_index -> Int", 2080, -50)
    link(tree, n18, "Value", n19, "Float")

    frameC = make_frame(tree, "C. (local_row, local_col) -> ИНДЕКС В ИСТОЧНИКЕ (с заворотом колонки)",
                         [n14, n15, n16, n17, n18, n19])

    n20 = add_node(tree, "GeometryNodeSampleIndex", "3z.20",
                    "Взять позицию точки-источника по индексу", 2080, 200, data_type='FLOAT_VECTOR')
    tree.links.new(GI("Точки"), in_sock(n20, "Geometry"))
    n20p = add_node(tree, "GeometryNodeInputPosition", "3z.20p", "Position (в контексте 'Точки')",
                     1820, 300)
    link(tree, n20p, "Position", n20, "Value_Vector")
    link(tree, n19, "Integer", n20, "Index")

    n21 = add_node(tree, "GeometryNodeSetPosition", "3z.21",
                    "Записать позицию на сетку-донор -> Mesh", 2400, 150)
    link(tree, n08, "Mesh", n21, "Geometry")
    link(tree, n20, "Value_Vector", n21, "Position")

    frameD = make_frame(tree, "D. САМПЛИНГ ПОЗИЦИИ И ЗАПИСЬ НА СЕТКУ", [n20, n20p, n21])

    tree.links.new(n21.outputs["Geometry"], gout.inputs["Mesh"])
    return tree


# ----------------------------------------------------------------------
# 2) NK.3y_Мост
# ----------------------------------------------------------------------
def build_bridge():
    tree = new_group(BRIDGE_NAME)
    add_input(tree, "Точки_A", "NodeSocketGeometry", description="Контур A (K точек), напр. внешний край.")
    add_input(tree, "Точки_B", "NodeSocketGeometry", description="Контур B (K точек), тот же порядок, напр. внутренний край.")
    add_input(tree, "K", "NodeSocketInt", default=4, min_value=2, max_value=4096)
    add_output(tree, "Mesh", "NodeSocketGeometry", "Полоса 2xK, сшивающая контур A с контуром B.")

    gin = tree.nodes.new("NodeGroupInput")
    gin.name = "3y.01 Вход"; gin.label = "3y.01 Входные параметры"; gin.location = (-300, 0)
    gout = tree.nodes.new("NodeGroupOutput")
    gout.name = "3y.99 Выход"; gout.label = "3y.99 Выход"; gout.location = (1600, 0)

    def GI(name):
        return gin.outputs[name]

    n02 = add_node(tree, "GeometryNodeMeshGrid", "3y.02",
                    "Сетка-донор 2 x K (2 ряда: A и B)", 0, 200)
    in_sock(n02, "Vertices X").default_value = 2
    tree.links.new(GI("K"), in_sock(n02, "Vertices Y"))
    in_sock(n02, "Size X").default_value = 1.0
    in_sock(n02, "Size Y").default_value = 1.0

    n03 = add_node(tree, "GeometryNodeInputIndex", "3y.03", "index вершины донора", 0, -50)

    n04 = add_node(tree, "ShaderNodeMath", "3y.04", "index / K", 260, -50, operation='DIVIDE')
    link(tree, n03, "Index", n04, "Value")
    tree.links.new(GI("K"), in_sock(n04, "Value_001"))

    n05 = add_node(tree, "ShaderNodeMath", "3y.05", "which = floor(index/K): 0->A, 1->B",
                    520, -50, operation='FLOOR')
    link(tree, n04, "Value", n05, "Value")

    n06 = add_node(tree, "ShaderNodeMath", "3y.06", "which*K", 780, -130, operation='MULTIPLY')
    link(tree, n05, "Value", n06, "Value")
    tree.links.new(GI("K"), in_sock(n06, "Value_001"))

    n07 = add_node(tree, "ShaderNodeMath", "3y.07", "local_idx = index - which*K",
                    1040, -50, operation='SUBTRACT')
    link(tree, n03, "Index", n07, "Value")
    link(tree, n06, "Value", n07, "Value_001")

    n08 = add_node(tree, "FunctionNodeFloatToInt", "3y.08", "local_idx -> Int", 1300, -50)
    link(tree, n07, "Value", n08, "Float")

    frameA = make_frame(tree, "A. (which_loop, local_idx) ИЗ ИНДЕКСА ВЕРШИНЫ ДОНОРА",
                         [n03, n04, n05, n06, n07, n08])

    n09 = add_node(tree, "GeometryNodeSampleIndex", "3y.09", "Позиция из контура A",
                    1300, 250, data_type='FLOAT_VECTOR')
    tree.links.new(GI("Точки_A"), in_sock(n09, "Geometry"))
    n09p = add_node(tree, "GeometryNodeInputPosition", "3y.09p", "Position (A)", 1040, 350)
    link(tree, n09p, "Position", n09, "Value_Vector")
    link(tree, n08, "Integer", n09, "Index")

    n10 = add_node(tree, "GeometryNodeSampleIndex", "3y.10", "Позиция из контура B",
                    1300, 100, data_type='FLOAT_VECTOR')
    tree.links.new(GI("Точки_B"), in_sock(n10, "Geometry"))
    n10p = add_node(tree, "GeometryNodeInputPosition", "3y.10p", "Position (B)", 1040, 50)
    link(tree, n10p, "Position", n10, "Value_Vector")
    link(tree, n08, "Integer", n10, "Index")

    n11 = add_node(tree, "ShaderNodeMath", "3y.11", "which == 0 ? (это ряд A)",
                    1560, -200, operation='LESS_THAN')
    link(tree, n05, "Value", n11, "Value")
    in_sock(n11, "Value_001").default_value = 0.5

    n12 = add_node(tree, "GeometryNodeSwitch", "3y.12",
                    "Выбор: which==A -> позиция A, иначе -> позиция B",
                    1820, 150, input_type='VECTOR')
    link(tree, n11, "Value", n12, "Switch")
    link(tree, n09, "Value_Vector", n12, "True_003")
    link(tree, n10, "Value_Vector", n12, "False_003")

    frameB = make_frame(tree, "B. ВЫБОР ПОЗИЦИИ ИЗ A ИЛИ B ПО РЯДУ", [n09, n09p, n10, n10p, n11, n12])

    n13 = add_node(tree, "GeometryNodeSetPosition", "3y.13",
                    "Записать позицию на сетку-донор -> Mesh", 2100, 150)
    link(tree, n02, "Mesh", n13, "Geometry")
    link(tree, n12, "Output_003", n13, "Position")

    tree.links.new(n13.outputs["Geometry"], gout.inputs["Mesh"])
    return tree


# ----------------------------------------------------------------------
# 3) NK.3a_Половина_оболочки
# ----------------------------------------------------------------------
def _grp(tree, tpl_tree, num, label, x, y):
    n = add_node(tree, "GeometryNodeGroup", num, label, x, y)
    n.node_tree = tpl_tree
    return n


def build_half_shell(sampler_tree, bridge_tree):
    tree = new_group(HALF_NAME)
    add_input(tree, "Внешние_точки", "NodeSocketGeometry",
              description="Облако N рядов x M колонок - внешняя поверхность (из Группы 2/подрезки).")
    add_input(tree, "Внутренние_точки", "NodeSocketGeometry",
              description="То же облако, точки смещены внутрь на толщину стенки.")
    add_input(tree, "M", "NodeSocketInt", default=32, min_value=3, max_value=256)
    add_input(tree, "N", "NodeSocketInt", default=48, min_value=2, max_value=4096)
    add_input(tree, "Колонка_от", "NodeSocketInt", default=0, min_value=0, max_value=256)
    add_input(tree, "Колонка_до", "NodeSocketInt", default=16, min_value=0, max_value=256)
    add_output(tree, "Mesh", "NodeSocketGeometry", "Замкнутая (watertight) половина оболочки.")
    add_output(tree, "Провер_Замкнуто_OK", "NodeSocketBool",
               "True, если у результата нет открытых (граничных) рёбер.")
    add_output(tree, "Провер_Отчёт", "NodeSocketString")

    gin = tree.nodes.new("NodeGroupInput")
    gin.name = "3a.01 Вход"; gin.label = "3a.01 Входные параметры"; gin.location = (-400, 300)
    gout = tree.nodes.new("NodeGroupOutput")
    gout.name = "3a.99 Выход"; gout.label = "3a.99 Выход"; gout.location = (3200, 300)

    def GI(name):
        return gin.outputs[name]

    n02 = add_node(tree, "ShaderNodeMath", "3a.02", "Nm1 = N-1", -100, 550, operation='SUBTRACT')
    tree.links.new(GI("N"), in_sock(n02, "Value"))
    in_sock(n02, "Value_001").default_value = 1.0
    n02i = add_node(tree, "FunctionNodeFloatToInt", "3a.02i", "Nm1 -> Int", 150, 550)
    link(tree, n02, "Value", n02i, "Float")

    n03k = add_node(tree, "ShaderNodeMath", "3a.03k", "K = Колонка_до-Колонка_от+1",
                     -100, 700, operation='SUBTRACT')
    tree.links.new(GI("Колонка_до"), in_sock(n03k, "Value"))
    tree.links.new(GI("Колонка_от"), in_sock(n03k, "Value_001"))
    n03k2 = add_node(tree, "ShaderNodeMath", "3a.03k2", "+1", 150, 700, operation='ADD')
    link(tree, n03k, "Value", n03k2, "Value")
    in_sock(n03k2, "Value_001").default_value = 1.0
    n03ki = add_node(tree, "FunctionNodeFloatToInt", "3a.03ki", "K -> Int", 400, 700)
    link(tree, n03k2, "Value", n03ki, "Float")

    frame0 = make_frame(tree, "0. ВСПОМОГАТЕЛЬНЫЕ ВЕЛИЧИНЫ (Nm1, K)",
                         [n02, n02i, n03k, n03k2, n03ki])

    # -- outer/inner main strip (вся высота, диапазон колонок половины) --
    n04 = _grp(tree, sampler_tree, "3a.04", "outer_main: Row[0..Nm1] Col[от..до]", 700, 900)
    tree.links.new(GI("Внешние_точки"), n04.inputs["Точки"])
    tree.links.new(GI("M"), n04.inputs["M_источника"])
    n04.inputs["Row_от"].default_value = 0
    tree.links.new(out_sock(n02i, "Integer"), n04.inputs["Row_до"])
    tree.links.new(GI("Колонка_от"), n04.inputs["Col_от"])
    tree.links.new(GI("Колонка_до"), n04.inputs["Col_до"])

    n05 = _grp(tree, sampler_tree, "3a.05", "inner_main_raw: то же по Внутренние_точки", 700, 700)
    tree.links.new(GI("Внутренние_точки"), n05.inputs["Точки"])
    tree.links.new(GI("M"), n05.inputs["M_источника"])
    n05.inputs["Row_от"].default_value = 0
    tree.links.new(out_sock(n02i, "Integer"), n05.inputs["Row_до"])
    tree.links.new(GI("Колонка_от"), n05.inputs["Col_от"])
    tree.links.new(GI("Колонка_до"), n05.inputs["Col_до"])

    n06 = add_node(tree, "GeometryNodeFlipFaces", "3a.06",
                    "inner_main: перевернуть нормали внутрь", 1000, 700)
    tree.links.new(n05.outputs["Mesh"], in_sock(n06, "Mesh"))

    frame1 = make_frame(tree, "1. ОСНОВНЫЕ ПОЛОСЫ: ВНЕШНЯЯ И ВНУТРЕННЯЯ (col от..до, все ряды)",
                         [n04, n05, n06])

    # -- bottom bridge (row=0) --
    n07 = _grp(tree, sampler_tree, "3a.07", "outer_row0: Row[0,0] Col[от..до]", 700, 450)
    tree.links.new(GI("Внешние_точки"), n07.inputs["Точки"])
    tree.links.new(GI("M"), n07.inputs["M_источника"])
    n07.inputs["Row_от"].default_value = 0
    n07.inputs["Row_до"].default_value = 0
    tree.links.new(GI("Колонка_от"), n07.inputs["Col_от"])
    tree.links.new(GI("Колонка_до"), n07.inputs["Col_до"])

    n08 = _grp(tree, sampler_tree, "3a.08", "inner_row0: Row[0,0] Col[от..до]", 700, 320)
    tree.links.new(GI("Внутренние_точки"), n08.inputs["Точки"])
    tree.links.new(GI("M"), n08.inputs["M_источника"])
    n08.inputs["Row_от"].default_value = 0
    n08.inputs["Row_до"].default_value = 0
    tree.links.new(GI("Колонка_от"), n08.inputs["Col_от"])
    tree.links.new(GI("Колонка_до"), n08.inputs["Col_до"])

    n09 = _grp(tree, bridge_tree, "3a.09", "bottom_bridge = Мост(outer_row0, inner_row0)", 1000, 380)
    tree.links.new(n07.outputs["Mesh"], n09.inputs["Точки_A"])
    tree.links.new(n08.outputs["Mesh"], n09.inputs["Точки_B"])
    tree.links.new(out_sock(n03ki, "Integer"), n09.inputs["K"])

    frame2 = make_frame(tree, "2. МОСТ СНИЗУ (row=0): закрывает нижнюю подрезку",
                         [n07, n08, n09])

    # -- top bridge (row=Nm1) --
    n10 = _grp(tree, sampler_tree, "3a.10", "outer_rowTop: Row[Nm1,Nm1] Col[от..до]", 700, 100)
    tree.links.new(GI("Внешние_точки"), n10.inputs["Точки"])
    tree.links.new(GI("M"), n10.inputs["M_источника"])
    tree.links.new(out_sock(n02i, "Integer"), n10.inputs["Row_от"])
    tree.links.new(out_sock(n02i, "Integer"), n10.inputs["Row_до"])
    tree.links.new(GI("Колонка_от"), n10.inputs["Col_от"])
    tree.links.new(GI("Колонка_до"), n10.inputs["Col_до"])

    n11 = _grp(tree, sampler_tree, "3a.11", "inner_rowTop: Row[Nm1,Nm1] Col[от..до]", 700, -30)
    tree.links.new(GI("Внутренние_точки"), n11.inputs["Точки"])
    tree.links.new(GI("M"), n11.inputs["M_источника"])
    tree.links.new(out_sock(n02i, "Integer"), n11.inputs["Row_от"])
    tree.links.new(out_sock(n02i, "Integer"), n11.inputs["Row_до"])
    tree.links.new(GI("Колонка_от"), n11.inputs["Col_от"])
    tree.links.new(GI("Колонка_до"), n11.inputs["Col_до"])

    n12 = _grp(tree, bridge_tree, "3a.12", "top_bridge = Мост(outer_rowTop, inner_rowTop)", 1000, 30)
    tree.links.new(n10.outputs["Mesh"], n12.inputs["Точки_A"])
    tree.links.new(n11.outputs["Mesh"], n12.inputs["Точки_B"])
    tree.links.new(out_sock(n03ki, "Integer"), n12.inputs["K"])

    frame3 = make_frame(tree, "3. МОСТ СВЕРХУ (row=N-1): закрывает верхнюю подрезку",
                         [n10, n11, n12])

    # -- seam at Колонка_от (весь диапазон рядов) --
    n13 = _grp(tree, sampler_tree, "3a.13", "outer_colStart: Row[0..Nm1] Col[от,от]", 1300, 900)
    tree.links.new(GI("Внешние_точки"), n13.inputs["Точки"])
    tree.links.new(GI("M"), n13.inputs["M_источника"])
    n13.inputs["Row_от"].default_value = 0
    tree.links.new(out_sock(n02i, "Integer"), n13.inputs["Row_до"])
    tree.links.new(GI("Колонка_от"), n13.inputs["Col_от"])
    tree.links.new(GI("Колонка_от"), n13.inputs["Col_до"])

    n14 = _grp(tree, sampler_tree, "3a.14", "inner_colStart: Row[0..Nm1] Col[от,от]", 1300, 750)
    tree.links.new(GI("Внутренние_точки"), n14.inputs["Точки"])
    tree.links.new(GI("M"), n14.inputs["M_источника"])
    n14.inputs["Row_от"].default_value = 0
    tree.links.new(out_sock(n02i, "Integer"), n14.inputs["Row_до"])
    tree.links.new(GI("Колонка_от"), n14.inputs["Col_от"])
    tree.links.new(GI("Колонка_от"), n14.inputs["Col_до"])

    n15 = _grp(tree, bridge_tree, "3a.15",
               "seamStart_bridge = Мост(outer_colStart, inner_colStart)", 1600, 820)
    tree.links.new(n13.outputs["Mesh"], n15.inputs["Точки_A"])
    tree.links.new(n14.outputs["Mesh"], n15.inputs["Точки_B"])
    tree.links.new(GI("N"), n15.inputs["K"])  # K точек по этому шву = N (весь диапазон рядов)

    frame4 = make_frame(tree, "4. ШОВ 'КОЛОНКА_ОТ' (по всей высоте)", [n13, n14, n15])

    # -- seam at Колонка_до --
    n16 = _grp(tree, sampler_tree, "3a.16", "outer_colEnd: Row[0..Nm1] Col[до,до]", 1300, 500)
    tree.links.new(GI("Внешние_точки"), n16.inputs["Точки"])
    tree.links.new(GI("M"), n16.inputs["M_источника"])
    n16.inputs["Row_от"].default_value = 0
    tree.links.new(out_sock(n02i, "Integer"), n16.inputs["Row_до"])
    tree.links.new(GI("Колонка_до"), n16.inputs["Col_от"])
    tree.links.new(GI("Колонка_до"), n16.inputs["Col_до"])

    n17 = _grp(tree, sampler_tree, "3a.17", "inner_colEnd: Row[0..Nm1] Col[до,до]", 1300, 350)
    tree.links.new(GI("Внутренние_точки"), n17.inputs["Точки"])
    tree.links.new(GI("M"), n17.inputs["M_источника"])
    n17.inputs["Row_от"].default_value = 0
    tree.links.new(out_sock(n02i, "Integer"), n17.inputs["Row_до"])
    tree.links.new(GI("Колонка_до"), n17.inputs["Col_от"])
    tree.links.new(GI("Колонка_до"), n17.inputs["Col_до"])

    n18 = _grp(tree, bridge_tree, "3a.18",
               "seamEnd_bridge = Мост(outer_colEnd, inner_colEnd)", 1600, 420)
    tree.links.new(n16.outputs["Mesh"], n18.inputs["Точки_A"])
    tree.links.new(n17.outputs["Mesh"], n18.inputs["Точки_B"])
    tree.links.new(GI("N"), n18.inputs["K"])

    frame5 = make_frame(tree, "5. ШОВ 'КОЛОНКА_ДО' (по всей высоте)", [n16, n17, n18])

    # -- сборка --
    n19 = add_node(tree, "GeometryNodeJoinGeometry", "3a.19",
                    "Join: outer+inner+4 моста = замкнутая половина", 1900, 500)
    for src, sock in [(n04, "Mesh"), (n06, "Mesh"), (n09, "Mesh"), (n12, "Mesh"),
                       (n15, "Mesh"), (n18, "Mesh")]:
        tree.links.new(src.outputs[sock], n19.inputs["Geometry"])

    # ВАЖНО: Join Geometry НЕ сваривает совпадающие по позиции вершины
    # разных кусков (внешняя полоса, внутренняя, 4 мостика были
    # построены независимо через Sample Index, поэтому в одной и той
    # же точке пространства оказываются РАЗНЫЕ вершины меша). Без
    # сварки каждый шов формально остаётся "дырой" (рёбра с 1 гранью).
    # Merge by Distance с маленьким порогом схлопывает такие дубликаты
    # в общие вершины - и тогда швы становятся настоящими закрытыми
    # рёбрами с 2 гранями.
    n19b = add_node(tree, "GeometryNodeMergeByDistance", "3a.19b",
                     "Сварить совпадающие вершины швов (Distance=0.01мм)",
                     2100, 500)
    link(tree, n19, "Geometry", n19b, "Geometry")
    in_sock(n19b, "Distance").default_value = 0.01

    # ВАЖНО (ещё одни грабли, обнаруженные при сборке Группы 4 - буленовы
    # UNION/DIFFERENCE с этой оболочкой давали "дырявые" края даже когда
    # обе фигуры сами по себе были корректны). Проверка через
    # bmesh.calc_volume(signed=True) показала ОТРИЦАТЕЛЬНЫЙ объём - все
    # нормали половины оболочки были развёрнуты ВНУТРЬ. Замкнутость
    # (0 граничных рёбер) и характеристика Эйлера на это не реагируют
    # (это топологические, а не ориентационные инварианты) - баг
    # оставался незаметен, пока Группа 4 не начала делать Boolean
    # UNION/DIFFERENCE, для которых согласованное направление нормалей
    # критично. Разворачиваем нормали целиком одним узлом.
    n19c = add_node(tree, "GeometryNodeFlipFaces", "3a.19c",
                     "Развернуть нормали наружу (были инвертированы)",
                     2300, 500)
    link(tree, n19b, "Geometry", n19c, "Mesh")

    frame6 = make_frame(tree, "6. СБОРКА ПОЛОВИНЫ ОБОЛОЧКИ + СВАРКА ШВОВ + РАЗВОРОТ НОРМАЛЕЙ",
                         [n19, n19b, n19c])

    # -- проверка замкнутости --
    v01 = add_node(tree, "GeometryNodeInputMeshEdgeNeighbors", "V3a.1",
                    "Кол-во граней на каждом ребре", 2400, 200)

    v02 = add_node(tree, "FunctionNodeCompare", "V3a.2",
                    "ребро граничное? (соседей != 2)", 2660, 200,
                    data_type='INT', operation='NOT_EQUAL')
    link(tree, v01, "Face Count", v02, "A_INT")
    in_sock(v02, "B_INT").default_value = 2

    v03 = add_node(tree, "GeometryNodeAttributeStatistic", "V3a.3",
                    "Сумма граничных рёбер по всему мешу",
                    2920, 200, domain='EDGE')
    link(tree, n19c, "Mesh", v03, "Geometry")
    link(tree, v02, "Result", v03, "Attribute")

    v04 = add_node(tree, "FunctionNodeCompare", "V3a.4",
                    "Граничных рёбер == 0 ? (полностью замкнуто)",
                    3180, 200, data_type='FLOAT', operation='EQUAL')
    link(tree, v03, "Sum", v04, "A")
    in_sock(v04, "B").default_value = 0.0

    frame7 = make_frame(tree, "7. ПРОВЕРКА: ОБОЛОЧКА ПОЛНОСТЬЮ ЗАМКНУТА (watertight)",
                         [v01, v02, v03, v04])

    n20 = add_node(tree, "FunctionNodeValueToString", "3a.20",
                    "Граничных рёбер -> строка", 3180, 50)
    link(tree, v03, "Sum", n20, "Value")
    in_sock(n20, "Decimals").default_value = 0

    tree.links.new(n19c.outputs["Mesh"], gout.inputs["Mesh"])
    tree.links.new(v04.outputs["Result"], gout.inputs["Провер_Замкнуто_OK"])
    tree.links.new(n20.outputs["String"], gout.inputs["Провер_Отчёт"])

    return tree


# ----------------------------------------------------------------------
# 4) NK.3_Оболочка (верхний уровень)
# ----------------------------------------------------------------------
def build_shell(half_tree):
    tree = new_group(SHELL_NAME)
    add_input(tree, "Профиль_точки", "NodeSocketGeometry",
              description="Выход 'Профиль_точки' Группы 2 (NK.2_Профиль).")
    add_input(tree, "Точек_в_кольце", "NodeSocketInt", default=32, min_value=3, max_value=256,
              description="= выход 'Точек_в_кольце' Группы 2.")
    add_input(tree, "Подрезка_снизу_доля", "NodeSocketFloat", default=0.0,
              min_value=0.0, max_value=0.35,
              description="Убрать кольца ниже этой доли высоты (0=не подрезать снизу). "
                           "Пригодится, если стык со стопой нестандартный.")
    add_input(tree, "Подрезка_сверху_доля", "NodeSocketFloat", default=0.0,
              min_value=0.0, max_value=0.35,
              description="Убрать кольца выше этой доли от верха (0=не подрезать сверху). "
                           "Зависит от приёмной гильзы/коленного модуля.")
    add_input(tree, "Толщина_стенки_мм", "NodeSocketFloat", default=2.4,
              min_value=1.2, max_value=4.0,
              description="Толщина стенки накладки, мм (2-3 стенки при сопле 0.4мм для PETG).")
    add_input(tree, "Расширение_верхней_мм", "NodeSocketFloat", default=3.0,
              min_value=0.0, max_value=15.0,
              description="Плавное расширение кольца НАРУЖУ у самого верхнего края (после "
                           "подрезки) - для более мягкого перехода к приёмной гильзе, мм.")
    add_input(tree, "Расширение_протяжённость_доля", "NodeSocketFloat", default=0.12,
              min_value=0.02, max_value=0.4,
              description="Доля высоты (в T) от верхнего края, на которой расширение плавно "
                           "сходит на нет вниз.")
    add_output(tree, "VIS_Вместе", "NodeSocketGeometry", "Перед+зад соединены, для общего просмотра.")
    add_output(tree, "Перед", "NodeSocketGeometry", "Передняя половина оболочки.")
    add_output(tree, "Зад", "NodeSocketGeometry", "Задняя половина оболочки.")
    add_output(tree, "Колец_после_подрезки", "NodeSocketInt")
    add_output(tree, "Провер_ВСЕ_OK", "NodeSocketBool")
    add_output(tree, "Провер_Отчёт", "NodeSocketString")

    gin = tree.nodes.new("NodeGroupInput")
    gin.name = "3.01 Вход"; gin.label = "3.01 Входные параметры"; gin.location = (-400, 300)
    gout = tree.nodes.new("NodeGroupOutput")
    gout.name = "3.99 Выход"; gout.label = "3.99 Выход"; gout.location = (3400, 300)

    def GI(name):
        return gin.outputs[name]

    # ------------------------------------------------------------------
    # 1. ПОДРЕЗКА КОЛЕЦ ПО ВЫСОТЕ
    # ------------------------------------------------------------------
    n02 = named_attr(tree, "3.02", "Читаем 'ring_T'", 0, 500, "ring_T", 'FLOAT')

    n03 = add_node(tree, "FunctionNodeCompare", "3.03",
                    "ring_T >= Подрезка_снизу_доля ?", 260, 550,
                    data_type='FLOAT', operation='GREATER_EQUAL')
    link(tree, n02, "Attribute_Float", n03, "A")
    tree.links.new(GI("Подрезка_снизу_доля"), in_sock(n03, "B"))

    n04 = add_node(tree, "ShaderNodeMath", "3.04", "верх. предел = 1 - Подрезка_сверху_доля",
                    260, 400, operation='SUBTRACT')
    in_sock(n04, "Value").default_value = 1.0
    tree.links.new(GI("Подрезка_сверху_доля"), in_sock(n04, "Value_001"))

    n05 = add_node(tree, "FunctionNodeCompare", "3.05",
                    "ring_T <= верх. предел ?", 520, 400,
                    data_type='FLOAT', operation='LESS_EQUAL')
    link(tree, n02, "Attribute_Float", n05, "A")
    link(tree, n04, "Value", n05, "B")

    n06 = add_node(tree, "FunctionNodeBooleanMath", "3.06",
                    "оставить точку? = (снизу OK) И (сверху OK)", 780, 480, operation='AND')
    link(tree, n03, "Result", n06, "Boolean")
    link(tree, n05, "Result", n06, "Boolean_001")

    n06b = add_node(tree, "FunctionNodeBooleanMath", "3.06b",
                     "удалить точку? = НЕ(оставить)", 1040, 480, operation='NOT')
    link(tree, n06, "Boolean", n06b, "Boolean")

    n07 = add_node(tree, "GeometryNodeDeleteGeometry", "3.07",
                    "Удалить точки вне диапазона подрезки", 1300, 550, domain='POINT')
    tree.links.new(GI("Профиль_точки"), in_sock(n07, "Geometry"))
    link(tree, n06b, "Boolean", n07, "Selection")

    frame1 = make_frame(tree, "1. ПОДРЕЗКА КОЛЕЦ ПО ВЫСОТЕ (ring_T вне диапазона -> удалить)",
                         [n02, n03, n04, n05, n06, n06b, n07])

    # ------------------------------------------------------------------
    # 1b. РАСШИРЕНИЕ ВЕРХНЕЙ ЧАСТИ (плавный переход к гильзе)
    # falloff(T) = гладкий колокол, 1 у самого верхнего края (T=верх.предел),
    # 0 ниже по Расширение_протяжённость_доля - та же техника, что и
    # икра/овальность в Группе 2 (cos-колокол, C1-непрерывно).
    # ------------------------------------------------------------------
    n07f1 = add_node(tree, "ShaderNodeMath", "3.07f1", "diff = верх.предел - ring_T",
                      1300, 850, operation='SUBTRACT')
    link(tree, n04, "Value", n07f1, "Value")
    link(tree, n02, "Attribute_Float", n07f1, "Value_001")

    n07f2 = add_node(tree, "ShaderNodeMath", "3.07f2", "diff = max(diff, 0)",
                      1560, 850, operation='MAXIMUM')
    link(tree, n07f1, "Value", n07f2, "Value")
    in_sock(n07f2, "Value_001").default_value = 0.0

    n07f3 = add_node(tree, "ShaderNodeMath", "3.07f3", "норм. = diff / Расширение_протяжённость_доля",
                      1820, 850, operation='DIVIDE')
    link(tree, n07f2, "Value", n07f3, "Value")
    tree.links.new(GI("Расширение_протяжённость_доля"), in_sock(n07f3, "Value_001"))

    n07f4 = add_node(tree, "ShaderNodeMath", "3.07f4", "min(норм., 1)",
                      2080, 850, operation='MINIMUM')
    link(tree, n07f3, "Value", n07f4, "Value")
    in_sock(n07f4, "Value_001").default_value = 1.0

    n07f5 = add_node(tree, "ShaderNodeMath", "3.07f5", "* пи",
                      2340, 850, operation='MULTIPLY')
    link(tree, n07f4, "Value", n07f5, "Value")
    in_sock(n07f5, "Value_001").default_value = 3.14159265358979

    n07f6 = add_node(tree, "ShaderNodeMath", "3.07f6", "cos(...)",
                      2600, 850, operation='COSINE')
    link(tree, n07f5, "Value", n07f6, "Value")

    n07f7 = add_node(tree, "ShaderNodeMath", "3.07f7", "+1",
                      2860, 850, operation='ADD')
    link(tree, n07f6, "Value", n07f7, "Value")
    in_sock(n07f7, "Value_001").default_value = 1.0

    n07f8 = add_node(tree, "ShaderNodeMath", "3.07f8",
                      "falloff_верх(T) = *0.5 (1 у края, гладко к 0 ниже)",
                      3120, 850, operation='MULTIPLY')
    link(tree, n07f7, "Value", n07f8, "Value")
    in_sock(n07f8, "Value_001").default_value = 0.5

    n07f9 = add_node(tree, "ShaderNodeMath", "3.07f9",
                      "offset_расш = falloff_верх(T) * Расширение_верхней_мм",
                      3380, 850, operation='MULTIPLY')
    link(tree, n07f8, "Value", n07f9, "Value")
    tree.links.new(GI("Расширение_верхней_мм"), in_sock(n07f9, "Value_001"))

    n07fdir = named_attr(tree, "3.07fdir", "Читаем 'dir' (для расширения)", 1300, 700, "dir", 'FLOAT_VECTOR')

    n07fvec = add_node(tree, "ShaderNodeVectorMath", "3.07fvec",
                        "смещение_расш = dir * offset_расш", 3640, 750, operation='SCALE')
    link(tree, n07fdir, "Attribute_Vector", n07fvec, "Vector")
    link(tree, n07f9, "Value", n07fvec, "Scale")

    n07fpos = add_node(tree, "GeometryNodeInputPosition", "3.07fpos",
                        "Position (после подрезки)", 1300, 550)

    n07fnewpos = add_node(tree, "ShaderNodeVectorMath", "3.07fnewpos",
                           "новая позиция = позиция + смещение_расш", 3900, 650, operation='ADD')
    link(tree, n07fpos, "Position", n07fnewpos, "Vector")
    link(tree, n07fvec, "Vector", n07fnewpos, "Vector_001")

    n07b = add_node(tree, "GeometryNodeSetPosition", "3.07b",
                     "Записать -> Внешние_точки (расширенные у верха)", 4160, 650)
    link(tree, n07, "Geometry", n07b, "Geometry")
    link(tree, n07fnewpos, "Vector", n07b, "Position")

    frame1b = make_frame(
        tree, "1b. РАСШИРЕНИЕ ВЕРХНЕЙ ЧАСТИ (плавный переход к гильзе, гладкий колокол)",
        [n07f1, n07f2, n07f3, n07f4, n07f5, n07f6, n07f7, n07f8, n07f9,
         n07fdir, n07fvec, n07fpos, n07fnewpos, n07b])

    # ------------------------------------------------------------------
    # 2. ЧИСЛО ОСТАВШИХСЯ КОЛЕЦ (N) + ПРОВЕРКА ДЕЛИМОСТИ
    # ------------------------------------------------------------------
    v1a = add_node(tree, "GeometryNodeAttributeDomainSize", "V3.1a",
                    "Точек после подрезки", 1600, 750, component='MESH')
    link(tree, n07, "Geometry", v1a, "Geometry")

    n08 = add_node(tree, "ShaderNodeMath", "3.08", "N = точек / Точек_в_кольце",
                    1900, 750, operation='DIVIDE')
    link(tree, v1a, "Point Count", n08, "Value")
    tree.links.new(GI("Точек_в_кольце"), in_sock(n08, "Value_001"))

    n09 = add_node(tree, "FunctionNodeFloatToInt", "3.09", "N -> Int", 2160, 750)
    link(tree, n08, "Value", n09, "Float")

    v1b = add_node(tree, "ShaderNodeMath", "V3.1b",
                    "остаток = точек mod Точек_в_кольце", 1900, 600, operation='MODULO')
    link(tree, v1a, "Point Count", v1b, "Value")
    tree.links.new(GI("Точек_в_кольце"), in_sock(v1b, "Value_001"))

    v1 = add_node(tree, "FunctionNodeCompare", "V3.1",
                  "остаток == 0 ? (подрезка не разрывает кольца)", 2160, 600,
                  data_type='FLOAT', operation='EQUAL')
    link(tree, v1b, "Value", v1, "A")
    in_sock(v1, "B").default_value = 0.0

    frame2 = make_frame(tree, "2. N = ЧИСЛО ОСТАВШИХСЯ КОЛЕЦ + ПРОВЕРКА ДЕЛИМОСТИ",
                         [v1a, n08, n09, v1b, v1])

    # ------------------------------------------------------------------
    # 3. ВНУТРЕННИЕ ТОЧКИ (смещение внутрь на толщину стенки, от РАСШИРЕННОЙ
    # внешней поверхности n07b - чтобы толщина стенки оставалась постоянной
    # и после расширения верха)
    # ------------------------------------------------------------------
    n10 = named_attr(tree, "3.10", "Читаем 'dir'", 1600, 350, "dir", 'FLOAT_VECTOR')

    n11 = add_node(tree, "ShaderNodeVectorMath", "3.11",
                    "смещение = dir * Толщина_стенки_мм", 1900, 350, operation='SCALE')
    link(tree, n10, "Attribute_Vector", n11, "Vector")
    tree.links.new(GI("Толщина_стенки_мм"), in_sock(n11, "Scale"))

    n12p = add_node(tree, "GeometryNodeInputPosition", "3.12p", "Position (внешняя точка, расширенная)",
                     1600, 200)

    n12 = add_node(tree, "ShaderNodeVectorMath", "3.12",
                    "внутр. позиция = позиция - смещение", 2160, 280, operation='SUBTRACT')
    link(tree, n12p, "Position", n12, "Vector")
    link(tree, n11, "Vector", n12, "Vector_001")

    n13 = add_node(tree, "GeometryNodeSetPosition", "3.13",
                    "Записать -> Внутренние_точки (номинальные)", 2420, 280)
    link(tree, n07b, "Geometry", n13, "Geometry")
    link(tree, n12, "Vector", n13, "Position")

    frame3 = make_frame(tree, "3. ВНУТРЕННИЕ ТОЧКИ = ВНЕШНИЕ(расшир.) - dir*ТОЛЩИНА",
                         [n10, n11, n12p, n12, n13])

    # ------------------------------------------------------------------
    # 4. M/2 (граница между передней и задней половиной)
    # ------------------------------------------------------------------
    n14 = add_node(tree, "ShaderNodeMath", "3.14", "M/2", 1600, 50, operation='DIVIDE')
    tree.links.new(GI("Точек_в_кольце"), in_sock(n14, "Value"))
    in_sock(n14, "Value_001").default_value = 2.0
    n15 = add_node(tree, "FunctionNodeFloatToInt", "3.15", "M/2 -> Int", 1900, 50)
    link(tree, n14, "Value", n15, "Float")

    frame4 = make_frame(tree, "4. M/2 - ГРАНИЦА ПЕРЕД/ЗАД (боковые швы)", [n14, n15])

    # ------------------------------------------------------------------
    # 5. ДВЕ ПОЛОВИНЫ (Перед и Зад - одинаковая номинальная геометрия
    # шва, без фальца/паза - см. правки 220926, "убери пазы для
    # соединения деталей")
    # ------------------------------------------------------------------
    n16 = _grp(tree, half_tree, "3.16", "Перед = Половина(Col 0..M/2)", 2700, 550)
    tree.links.new(out_sock(n07b, "Geometry"), n16.inputs["Внешние_точки"])
    tree.links.new(out_sock(n13, "Geometry"), n16.inputs["Внутренние_точки"])
    tree.links.new(GI("Точек_в_кольце"), n16.inputs["M"])
    tree.links.new(out_sock(n09, "Integer"), n16.inputs["N"])
    n16.inputs["Колонка_от"].default_value = 0
    tree.links.new(out_sock(n15, "Integer"), n16.inputs["Колонка_до"])

    n17 = _grp(tree, half_tree, "3.17", "Зад = Половина(Col M/2..M)", 2700, 200)
    tree.links.new(out_sock(n07b, "Geometry"), n17.inputs["Внешние_точки"])
    tree.links.new(out_sock(n13, "Geometry"), n17.inputs["Внутренние_точки"])
    tree.links.new(GI("Точек_в_кольце"), n17.inputs["M"])
    tree.links.new(out_sock(n09, "Integer"), n17.inputs["N"])
    tree.links.new(out_sock(n15, "Integer"), n17.inputs["Колонка_от"])
    tree.links.new(GI("Точек_в_кольце"), n17.inputs["Колонка_до"])

    frame5 = make_frame(tree, "5. ПЕРЕДНЯЯ И ЗАДНЯЯ ПОЛОВИНЫ (Group: NK.3a_Половина_оболочки)",
                         [n16, n17])

    # ------------------------------------------------------------------
    # 6. ИТОГ: VIS, проверки, отчёт
    # ------------------------------------------------------------------
    n18 = add_node(tree, "GeometryNodeJoinGeometry", "3.18",
                    "VIS_Вместе = Перед + Зад", 3000, 500)
    tree.links.new(n16.outputs["Mesh"], n18.inputs["Geometry"])
    tree.links.new(n17.outputs["Mesh"], n18.inputs["Geometry"])

    v2 = add_node(tree, "FunctionNodeBooleanMath", "V3.2",
                  "Перед замкнут И Зад замкнут", 3000, 300, operation='AND')
    tree.links.new(n16.outputs["Провер_Замкнуто_OK"], in_sock(v2, "Boolean"))
    tree.links.new(n17.outputs["Провер_Замкнуто_OK"], in_sock(v2, "Boolean_001"))

    v3 = add_node(tree, "FunctionNodeBooleanMath", "V3.3",
                  "ИТОГ: делимость OK И обе половины замкнуты", 3260, 400, operation='AND')
    link(tree, v1, "Result", v3, "Boolean")
    link(tree, v2, "Boolean", v3, "Boolean_001")

    n19 = add_node(tree, "GeometryNodeStringJoin", "3.19",
                    "Отчёт: перед | зад", 3000, 100)
    in_sock(n19, "Delimiter").default_value = " | зад:"
    tree.links.new(n16.outputs["Провер_Отчёт"], n19.inputs["Strings"])
    tree.links.new(n17.outputs["Провер_Отчёт"], n19.inputs["Strings"])

    frame6 = make_frame(tree, "6. ИТОГ", [n18, v2, v3, n19])

    tree.links.new(n18.outputs["Geometry"], gout.inputs["VIS_Вместе"])
    tree.links.new(n16.outputs["Mesh"], gout.inputs["Перед"])
    tree.links.new(n17.outputs["Mesh"], gout.inputs["Зад"])
    tree.links.new(n09.outputs["Integer"], gout.inputs["Колец_после_подрезки"])
    tree.links.new(v3.outputs["Boolean"], gout.inputs["Провер_ВСЕ_OK"])
    tree.links.new(n19.outputs["String"], gout.inputs["Провер_Отчёт"])

    return tree


def build_all_groups():
    """Собирает все 4 под-группы Группы 3 и возвращает верхнюю (NK.3_Оболочка)."""
    sampler_tree = build_sampler()
    bridge_tree = build_bridge()
    half_tree = build_half_shell(sampler_tree, bridge_tree)
    shell_tree = build_shell(half_tree)
    return shell_tree


def build_demo_object(axis_tree, profile_tree, shell_tree):
    """Демо-объект: Группа1 -> Группа2 -> Группа3 в одном модификаторе."""
    name = "NK_Group3_Demo"
    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    mesh = bpy.data.meshes.new(name + "_mesh")
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)

    mod = obj.modifiers.new("NK_Master_preview", "NODES")
    master = bpy.data.node_groups.new("NK.Master_preview_g3", "GeometryNodeTree")
    master.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    mod.node_group = master

    gout = master.nodes.new("NodeGroupOutput")
    gout.location = (900, 0)

    g1 = master.nodes.new("GeometryNodeGroup")
    g1.node_tree = axis_tree
    g1.location = (-400, 0)
    g1.name = "M.1 Группа 1 (Ось)"; g1.label = "M.1 Группа 1 (Ось)"

    g2 = master.nodes.new("GeometryNodeGroup")
    g2.node_tree = profile_tree
    g2.location = (0, 0)
    g2.name = "M.2 Группа 2 (Профиль)"; g2.label = "M.2 Группа 2 (Профиль)"

    g3 = master.nodes.new("GeometryNodeGroup")
    g3.node_tree = shell_tree
    g3.location = (400, 0)
    g3.name = "M.3 Группа 3 (Оболочка)"; g3.label = "M.3 Группа 3 (Оболочка)"

    master.links.new(g1.outputs["Ось_кривая"], g2.inputs["Ось_кривая"])
    master.links.new(g1.outputs["Факт_длина_дуги_мм"], g2.inputs["Длина_сегмента_мм"])
    master.links.new(g1.outputs["Сторона_ноги"], g2.inputs["Сторона_ноги"])
    master.links.new(g2.outputs["Профиль_точки"], g3.inputs["Профиль_точки"])
    master.links.new(g2.outputs["Точек_в_кольце"], g3.inputs["Точек_в_кольце"])
    master.links.new(g3.outputs["VIS_Вместе"], gout.inputs["Geometry"])

    return obj, mod, master, g1, g2, g3


if __name__ == "__main__":
    from build_group1_axis import build as build_axis
    from build_group2_profile import build as build_profile

    axis_tree = build_axis()
    profile_tree = build_profile()
    shell_tree = build_all_groups()
    obj, mod, master, g1, g2, g3 = build_demo_object(axis_tree, profile_tree, shell_tree)
    print("OK: собраны все группы, демо-объект '%s' создан" % obj.name)
