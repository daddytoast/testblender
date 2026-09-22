# -*- coding: utf-8 -*-
"""
Общие вспомогательные функции для сборки Geometry Nodes скриптами (bpy).

Используются всеми build_*.py скриптами проекта "Накладка голени".
Все размеры в проекте — миллиметры (мм), заданные как обычные числа
(без юнит-подсистемы Blender). Смотри docs/00_overview.md, раздел
"Единицы измерения" — почему выбран именно такой подход.
"""

import re

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

    ВАЖНО (найдено при переходе на Blender 5.1): часть узлов, у которых
    в 4.x подобный параметр был СВОЙСТВОМ ноды (n.mode = 'COUNT'), в
    5.x мигрировали на ВХОДНОЙ СОКЕТ типа MENU (напр. ResampleCurve и
    FilletCurve - у обоих 'mode' стал сокетом "Mode", не свойством).
    Чтобы не чинить это в каждом месте кода по отдельности - здесь
    единая страховка: если setattr падает с AttributeError, ищем
    MENU-сокет с тем же именем (без учёта регистра/подчёркиваний) и
    пишем значение в его default_value вместо свойства.
    """
    n = tree.nodes.new(bl_idname)
    full = f"{num} {label}"
    n.name = full
    n.label = full
    n.location = (x, y)
    # ВАЖНО (найдено при переходе на Blender 5.1): у GeometryNodeMeshBoolean
    # свойство 'solver' по умолчанию сменилось с 'EXACT' (было в 4.x) на
    # 'FLOAT' - более быстрый, но заметно менее надёжный решатель. Весь
    # этот проект спроектирован и вручную вытюнен под конкретное поведение
    # именно EXACT-решателя (см. многочисленные комментарии по всему
    # коду про "точный Boolean-решатель") - на FLOAT-решателе количество
    # дырявых рёбер вырастает в разы на той же геометрии (проверено
    # эмпирически: ~5х больше дефектов в Группе 4 на дефолтном FLOAT).
    # Принудительно выставляем EXACT здесь, а не в каждом отдельном
    # месте кода, чтобы не искать все ~40+ узлов Boolean по всем файлам.
    if bl_idname == "GeometryNodeMeshBoolean" and "solver" not in props:
        n.solver = 'EXACT'
    for k, v in props.items():
        try:
            setattr(n, k, v)
        except AttributeError:
            target_key = k.replace('_', '').lower()
            menu_socks = [s for s in n.inputs if s.type == 'MENU']
            match = None
            for s in menu_socks:
                if s.name.replace(' ', '').lower() == target_key or s.identifier.lower() == target_key:
                    match = s
                    break
            if match is None and len(menu_socks) == 1:
                match = menu_socks[0]
            if match is None:
                raise
            # Значения самого enum'а на MENU-сокетах тоже сменили
            # написание при миграции (было 'NGONS', стало 'N-gons';
            # 'COUNT' стало 'Count' и т.п.) - простой .title() не всегда
            # попадает (Ngons != N-gons). Пробуем как есть, иначе
            # вытаскиваем реальный список допустимых вариантов прямо
            # из текста ошибки Blender (RNA не даёт их статически для
            # MENU-сокетов) и ищем ближайший без учёта регистра/
            # пробелов/дефисов/подчёркиваний.
            try:
                match.default_value = v
            except TypeError as e:
                opts = re.findall(r"'([^']*)'|\"([^\"]*)\"", str(e).split(" not found in ")[-1])
                opts = [a or b for a, b in opts]
                norm = lambda s: re.sub(r'[\s_-]', '', s).lower()
                target = norm(v) if isinstance(v, str) else v
                best = next((o for o in opts if norm(o) == target), None)
                if best is None:
                    raise
                match.default_value = best
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


def _base_identifier(identifier):
    """'Value_Float' -> 'Value', 'True_006' -> 'True', 'Switch_001' ->
    'Switch' - см. докстринг ниже про унификацию идентификаторов в 5.x.
    """
    return identifier.split('_', 1)[0]


def out_sock(n, identifier):
    """Найти выходной сокет узла n по его identifier (не по name!).
    Нужно, т.к. у некоторых узлов (Compare, Mix, Switch...) несколько
    сокетов имеют одинаковое отображаемое имя ('A', 'Result'...),
    но разный identifier для разных типов данных.

    ВАЖНО (найдено при переходе на Blender 5.1): многие такие
    типизированные identifier'ы (StoreNamedAttribute 'Value_Float',
    SampleIndex 'Value_Vector', Switch 'True_006'/'False_006'/
    'Output_006'/'Switch_001' и т.п.) в 5.x УНИФИЦИРОВАНЫ до базового
    имени без суффикса ('Value', 'True', 'False', 'Output', 'Switch') -
    сокет с прежним точным identifier'ом больше не существует. Если
    точное совпадение не найдено - пробуем базовое имя (часть до
    первого '_') как фолбэк, чтобы код 4.x-эры продолжал работать без
    правки каждого отдельного места.
    """
    for s in n.outputs:
        if s.identifier == identifier:
            return s
    base = _base_identifier(identifier)
    if base != identifier:
        for s in n.outputs:
            if s.identifier == base:
                return s
    raise KeyError(f"Нет выходного сокета '{identifier}' у узла {n.name}")


def in_sock(n, identifier):
    """Найти входной сокет узла n по его identifier (см. out_sock, та
    же 5.x-страховка про унифицированные идентификаторы)."""
    for s in n.inputs:
        if s.identifier == identifier:
            return s
    base = _base_identifier(identifier)
    if base != identifier:
        for s in n.inputs:
            if s.identifier == base:
                return s
    raise KeyError(f"Нет входного сокета '{identifier}' у узла {n.name}")


def link(tree, from_node, from_id, to_node, to_id):
    """Соединить выход from_node[from_id] со входом to_node[to_id]."""
    tree.links.new(out_sock(from_node, from_id), in_sock(to_node, to_id))
