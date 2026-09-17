# -*- coding: utf-8 -*-
"""
Общие вспомогательные функции для сборки Geometry Nodes скриптами (bpy).

Используются всеми build_*.py скриптами проекта "Накладка голени".
Все размеры в проекте — миллиметры (мм), заданные как обычные числа
(без юнит-подсистемы Blender). Смотри docs/00_overview.md, раздел
"Единицы измерения" — почему выбран именно такой подход.
"""

import bpy


def new_group(name):
    """Создать новую Geometry Nodes группу с указанным именем.
    Если группа с таким именем уже существует - удаляем старую версию,
    чтобы повторный запуск скрипта пересобирал граф с нуля (чистая сборка).
    """
    if name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name])
    tree = bpy.data.node_groups.new(name, "GeometryNodeTree")
    return tree


def add_input(tree, name, socket_type, default=None, min_value=None,
              max_value=None, description=""):
    """Добавить входной сокет в интерфейс группы (Group Input)."""
    s = tree.interface.new_socket(
        name=name, in_out='INPUT', socket_type=socket_type,
        description=description,
    )
    if default is not None:
        s.default_value = default
    if min_value is not None:
        s.min_value = min_value
    if max_value is not None:
        s.max_value = max_value
    return s


def add_output(tree, name, socket_type, description=""):
    """Добавить выходной сокет в интерфейс группы (Group Output)."""
    return tree.interface.new_socket(
        name=name, in_out='OUTPUT', socket_type=socket_type,
        description=description,
    )


def add_node(tree, bl_idname, num, label, x, y, **props):
    """Создать узел (ноду), присвоить ему номер+подпись, разместить
    в точке (x, y) в АБСОЛЮТНЫХ координатах редактора нод.

    num   - номер узла в схеме, например "1.05"
    label - короткое описание назначения узла
    props - дополнительные свойства ноды (operation=, data_type=, ...)
    """
    n = tree.nodes.new(bl_idname)
    full = f"{num} {label}"
    n.name = full
    n.label = full
    n.location = (x, y)
    for k, v in props.items():
        setattr(n, k, v)
    return n


def make_frame(tree, title, nodes, color=None):
    """Создать рамку (Frame) с заголовком и поместить в неё список узлов.
    Рамка сама подстраивается по размеру под узлы (shrink=True по умолчанию).
    ВАЖНО: location детей нужно задавать ДО присвоения .parent - Blender
    сам пересчитает их в локальные координаты рамки, сохранив то же
    видимое положение на экране.
    """
    f = tree.nodes.new("NodeFrame")
    f.label = title
    f.name = f"FRAME_{title}"
    if color is not None:
        f.use_custom_color = True
        f.color = color
    for n in nodes:
        n.parent = f
    return f


def out_sock(n, identifier):
    """Найти выходной сокет узла n по его identifier (не по name!).
    Нужно, т.к. у некоторых узлов (Compare, Mix, Switch...) несколько
    сокетов имеют одинаковое отображаемое имя ('A', 'Result'...),
    но разный identifier для разных типов данных.
    """
    for s in n.outputs:
        if s.identifier == identifier:
            return s
    raise KeyError(f"Нет выходного сокета '{identifier}' у узла {n.name}")


def in_sock(n, identifier):
    """Найти входной сокет узла n по его identifier (см. out_sock)."""
    for s in n.inputs:
        if s.identifier == identifier:
            return s
    raise KeyError(f"Нет входного сокета '{identifier}' у узла {n.name}")


def link(tree, from_node, from_id, to_node, to_id):
    """Соединить выход from_node[from_id] со входом to_node[to_id]."""
    tree.links.new(out_sock(from_node, from_id), in_sock(to_node, to_id))
