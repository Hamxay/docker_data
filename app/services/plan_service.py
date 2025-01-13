import sys
from flask import jsonify, current_app
from datetime import datetime
from app.models import User, Item, ManufacturingCode, SecondaryCode, Plan, Requirement
from app.utils.algo import sort
from app import db
import jwt
import json
import logging
from flask import Response
import traceback
import ast
from collections import defaultdict, deque
from itertools import product

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    level=logging.DEBUG
)

class PlanManager:
    def __init__(self):
        self.quarters = [
            {"name": 'Fall', "limit": 16},
            {"name": 'Spring', "limit": 16},
        ]
        self.season_mapping = {
            'Fa': 'Fall',
            'Sp': 'Spring',
        }

    def create_plan(self, request):
        data = request.jsonrequirements_map = self.create_requirements_map()
        if not data:
            logging.error("No data provided in request.")
            return jsonify(status_code=400, result="error", message="No data provided"), 400

        # Получаем коды курсов из запроса
        manufacturing_codes = data.get('manufacturing_codes', [])
        secondary_codes = data.get('secondary_codes', [])
        additional_codes = data.get('additional_codes', [])
        extra_codes = data.get('extra_codes', [])

        logging.debug(f"Получены коды курсов: manufacturing_codes={manufacturing_codes}, secondary_codes={secondary_codes}, additional_codes={additional_codes}, extra_codes={extra_codes}")

        # Получаем объекты курсов из базы данных
        items = []
        extra_items = []

        if manufacturing_codes:
            fetched_items = Item.query.filter(Item.item_group_id.in_(manufacturing_codes)).all()
            items.extend(fetched_items)
            logging.debug(f"Получены производственные коды: {[item.code_name for item in fetched_items]}")

        if secondary_codes:
            fetched_items = Item.query.filter(Item.item_group_id.in_(secondary_codes)).all()
            items.extend(fetched_items)
            logging.debug(f"Получены вторичные коды: {[item.code_name for item in fetched_items]}")

        if additional_codes:
            fetched_items = Item.query.filter(Item.id.in_(additional_codes)).all()
            items.extend(fetched_items)
            logging.debug(f"Получены дополнительные коды: {[item.code_name for item in fetched_items]}")

        if extra_codes:
            fetched_items = Item.query.filter(Item.id.in_(extra_codes)).all()
            extra_items.extend(fetched_items)
            logging.debug(f"Получены дополнительные коды (extra): {[item.code_name for item in fetched_items]}")

        # Удаляем дубликаты
        unique_items = {item.id: item for item in items}
        items = list(unique_items.values())
        logging.debug(f"Уникальные курсы после удаления дубликатов: {[item.code_name for item in items]}")

        # Удаляем курсы, которые есть в extra_items
        extra_item_ids = {item.id for item in extra_items}
        items = [item for item in items if item.id not in extra_item_ids]
        logging.debug(f"Курсы после удаления extra_items: {[item.code_name for item in items]}")

        available_code_names = {item.code_name for item in items}

        final_map = self.unify_requirements_with_plan(items)

        processed_items = []
        original_dependencies = {}

        for item in items:
            item_copy = self.copy_item(item)

            original_dependencies[item_copy.code_name] = {
                'predecessor': item_copy.predecessor,
                'simultaneous': item_copy.simultaneous
            }

            # 2) Вызываем process_dependencies, передавая final_map
            processed = self.process_dependencies(item_copy, available_code_names, final_map)

            item_copy.predecessor = str(processed['predecessor'])
            item_copy.simultaneous = str(processed['simultaneous'])
            item_copy.available_terms = self.parse_terms(item_copy.terms)
            processed_items.append(item_copy)

        items = processed_items

        ### NEW CODE START ###
        # Удаляем симметричные одновременные зависимости
        # Создадим словарь для быстрого поиска кто от кого одновременно зависит
        simultaneous_map = defaultdict(set)
        for it in items:
            sim = ast.literal_eval(it.simultaneous) if it.simultaneous else []
            for group in sim:
                # Каждая group - список курсов
                for code_name in group:
                    simultaneous_map[it.code_name].add(code_name)

        # Теперь проверяем симметрию
        for it in items:
            sim = ast.literal_eval(it.simultaneous) if it.simultaneous else []
            new_sim = []
            for group in sim:
                # Фильтруем группу, убирая симметричные зависимости, если найдены
                filtered_group = []
                for code_name in group:
                    # Проверяем симметрию: it.code_name требует code_name и code_name требует it.code_name?
                    if code_name in simultaneous_map and it.code_name in simultaneous_map[code_name]:
                        # Симметрия обнаружена!
                        # Удаляем из текущего курса ссылку на code_name, чтобы разорвать цикл
                        # Можно пропустить добавление этого code_name в filtered_group
                        logging.debug(f"Симметричная одновременная зависимость обнаружена между {it.code_name} и {code_name}. Удаляем зависимость из {it.code_name}.")
                        # Не добавляем code_name в filtered_group, тем самым разорвав симметрию.
                    else:
                        filtered_group.append(code_name)
                if filtered_group:
                    new_sim.append(filtered_group)
            it.simultaneous = str(new_sim)
        ### NEW CODE END ###

        # Теперь проверяем циклы
        if self.has_cyclic_dependencies(items):
            logging.error("Циклические зависимости обнаружены в курсах после попытки убрать симметрии.")
            return jsonify(status_code=400, result="error", message="Циклические зависимости обнаружены в курсах."), 400

        sorted_items = self.sort_courses(items)
        if sorted_items is None:
            logging.error("Не удалось отсортировать курсы из-за циклических зависимостей даже после снятия симметрии.")
            return jsonify(status_code=400, result="error", message="Не удалось отсортировать курсы due to cycles."), 400

        plan = self.generate_plan(sorted_items)
        if plan is None:
            logging.error("Не удалось сгенерировать план из-за ошибок в зависимостях.")
            return jsonify(status_code=400, result="error", message="Не удалось сгенерировать план из-за ошибок в зависимостях."), 400

        # Восстанавливаем оригинальные зависимости перед выводом
        for it in items:
            code_name = it.code_name
            original = original_dependencies.get(code_name)
            if original:
                it.predecessor = original['predecessor']
                it.simultaneous = original['simultaneous']

        semester_labels = self.get_semester_labels(len(plan))
        formatted_plan = []

        for idx, semester in enumerate(plan):
            data = {}
            data['quarter_label'] = semester_labels[idx]
            data['quarter_num'] = idx + 1
            data['quarter_year'] = 2020
            data['total_units'] = 0
            quarter_items = []
            for course in semester:
                item = {}
                item['locked'] = False
                item['done'] = False
                item['item_id'] = course.id
                item['code_name'] = course.code_name
                item['letter'] = course.display
                item['units'] = course.units

                item['predecessor'] = ast.literal_eval(course.predecessor) if course.predecessor else []
                item['simultaneous'] = ast.literal_eval(course.simultaneous) if course.simultaneous else []
                item['term'] = course.terms
                item['standing'] = course.standing
                quarter_items.append(item)
                data['total_units'] += course.units
            data['items'] = quarter_items
            formatted_plan.append(data)

        requirements = Requirement.get_required_fields()

        response_data = {
            "quarters": formatted_plan,
            "reqs": requirements
        }

        response_json = json.dumps(response_data, ensure_ascii=False)
        print(f"Size of response data: {sys.getsizeof(response_json)} bytes")

        return Response(response_json, mimetype='application/json')

    def unify_requirements_with_plan(self, items):
        """
        1) Собирает code_name, которые реально встречаются в планируемых курсах (items).
        2) Фильтрует Requirement.get_required_fields(), оставляя только записи, где code_name есть в плане.
        3) Построит промежуточные структуры:
            course_id -> {code_name1, code_name2, ...}
            code_name -> {course_id1, course_id2, ...}
        4) Разрешит конфликты «многие-к-одному»/«один-ко-многим», беря всегда первый из вариантов и
        логируя предупреждения. В итоге получаем final_map: {course_id: code_name}.
        5) Возвращает final_map для дальнейшей подмены зависимостей в process_dependencies.
        """
        from collections import defaultdict

        # 1. Собираем code_name из списка items (курсов в плане)
        plan_code_names = {item.code_name for item in items}
        logging.debug(f"[unify_requirements_with_plan] В плане участвуют code_name: {plan_code_names}")

        # 2. Фильтруем записи Requirement.get_required_fields() по code_name, которые есть в плане
        requirements = Requirement.get_required_fields()
        filtered = [r for r in requirements if r["code_name"] in plan_code_names]
        logging.debug(f"[unify_requirements_with_plan] Из {len(requirements)} записей Requirement "
                    f"оставили {len(filtered)}, относящиеся к плану (code_name в плане).")

        # 3. Построим промежуточные структуры
        course_id_to_code_names = defaultdict(set)
        code_name_to_course_ids = defaultdict(set)

        for row in filtered:
            cid = row["course_id"]
            cname = row["code_name"]
            course_id_to_code_names[cid].add(cname)
            code_name_to_course_ids[cname].add(cid)

        # 4. Разрешим конфликты, создавая final_map: {course_id: code_name}
        final_map = {}

        # (a) Обработка «course_id -> code_name»
        for cid, cnames in course_id_to_code_names.items():
            if len(cnames) > 1:
                logging.warning(
                    f"[unify_requirements_with_plan] course_id='{cid}' связан с несколькими code_name: {cnames}. "
                    f"Берём {list(cnames)[0]}, остальные игнорируем."
                )
            chosen_cname = list(cnames)[0]
            final_map[cid] = chosen_cname

        # (b) Проверяем «code_name -> course_id» (на случай дубликатов в другую сторону)
        for cname, cids in code_name_to_course_ids.items():
            if len(cids) > 1:
                logging.warning(
                    f"[unify_requirements_with_plan] code_name='{cname}' связан с несколькими course_id: {cids}. "
                    f"Берём {list(cids)[0]}, остальные игнорируем."
                )
            for cid in cids:
                if cid in final_map:
                    # Если уже привязали cid к какому-то code_name, проверяем конфликт
                    if final_map[cid] != cname:
                        logging.warning(
                            f"[unify_requirements_with_plan] Конфликт: course_id={cid} уже связан с {final_map[cid]}, "
                            f"а теперь cname={cname}. Игнорируем {cname}."
                        )
                    else:
                        logging.debug(f"[unify_requirements_with_plan] Подтверждаем связку {cid} -> {cname}.")
                else:
                    final_map[cid] = cname

        logging.debug(f"[unify_requirements_with_plan] Итоговое сопоставление course_id->code_name: {final_map}")
        return final_map

    def parse_terms(self, terms_str):
        if not terms_str or terms_str.strip() == '':
            # Если terms не указаны, курс доступен в любые сезоны
            return [season['name'] for season in self.quarters]
        terms = [term.strip() for term in terms_str.split(',')]
        seasons = [self.season_mapping.get(term, term) for term in terms]
        return seasons

    def get_semester_labels(self, num_semesters):
        labels = []
        current_date = datetime.now()
        current_year = current_date.year
        current_month = current_date.month

        # Определяем ближайший сезон
        if current_month >= 8 and current_month <= 12:
            season_index = 0  # Fall
        else:
            season_index = 1  # Spring
            if current_month >= 1 and current_month <= 7:
                current_year += 1

        year = current_year
        for i in range(num_semesters):
            season = self.quarters[season_index % len(self.quarters)]
            labels.append(f"{season['name']} {year}")
            if season['name'] == 'Spring':
                year += 1
            season_index += 1

        return labels

    def copy_item(self, item):
        return Item(
            id=item.id,
            display=item.display,
            code_name=item.code_name,
            units=item.units,
            predecessor=item.predecessor,
            simultaneous=item.simultaneous,
            item_group_id=item.item_group_id,
            terms=item.terms,
            standing=item.standing
        )

    def create_requirements_map(self):
        """
        Собирает все пары course_id -> code_name из Requirement.get_required_fields().
        Убирает дубли: если у одного course_id несколько code_name, берёт первый и логирует предупреждение.
        Возвращает словарь {course_id: code_name}.
        """
        from collections import defaultdict

        requirements = Requirement.get_required_fields()  # [{code_name, course_id}, ...]
        temp_map = defaultdict(set)

        # Составляем промежуточную структуру { course_id: {code_name1, code_name2, ...} }
        for r in requirements:
            cid = r['course_id']
            cname = r['code_name']
            temp_map[cid].add(cname)

        requirements_map = {}
        # Из множества code_name для одного course_id берём первый
        for cid, cnames in temp_map.items():
            if len(cnames) > 1:
                logging.warning(
                    f"[create_requirements_map] Для course_id='{cid}' найдено несколько code_name: {cnames}. "
                    f"Берём {list(cnames)[0]}, остальные игнорируем."
                )
            requirements_map[cid] = list(cnames)[0]

        logging.debug(f"[create_requirements_map] Итоговое сопоставление: {requirements_map}")
        return requirements_map
    
    def map_dependencies(self, parsed_dependencies, requirements_map):
        """
        Преобразует все course_id в списках зависимостей в code_name на основе requirements_map.
        parsed_dependencies: результат ast.literal_eval(...) — список списков/строк.
        requirements_map: словарь { course_id: code_name }.
        Возвращает тот же формат, только с заменёнными значениями.
        """
        mapped_result = []
        for group in parsed_dependencies:
            # Каждый group может быть списком ["EC-201", "ARE-201"] или строкой "EC-201, ARE-201"
            if isinstance(group, str):
                codes = [code.strip() for code in group.split(',')]
            else:
                # Считаем, что это уже список, например ["EC-201", "ARE-201"]
                codes = group

            new_group = []
            for code in codes:
                mapped_code = requirements_map.get(code, code)  # Подменяем, если есть в словаре
                new_group.append(mapped_code)
            mapped_result.append(new_group)
        return mapped_result

    def process_dependencies(self, item, available_code_names, final_map):
        """
        Обрабатывает поля predecessor / simultaneous для одного курса (item):
        1) Парсит строку (ast.literal_eval).
        2) Подменяет course_id -> code_name (через map_dependencies(..., final_map)).
        3) Удаляет коды, которых нет в available_code_names.
        """
        logging.debug(f"Начинаем обработку зависимостей для курса {item.code_name}. Доступные коды: {available_code_names}")
        processed_fields = {}

        for field in ['predecessor', 'simultaneous']:
            field_str = getattr(item, field)
            logging.debug(f"Обработка поля {field} для {item.code_name}. Исходное значение: {field_str}")

            if not field_str:
                processed_fields[field] = []
                logging.debug(f"Поле '{field}' для {item.code_name} пусто, устанавливаем в [].")
                continue

            try:
                parsed = ast.literal_eval(field_str)
                logging.debug(f"Успешно спарсили поле '{field}' для {item.code_name}: {parsed}")
            except (ValueError, SyntaxError) as e:
                logging.error(f"Ошибка при парсинге поля '{field}' для {item.code_name}: {e}. Устанавливаем в [].")
                processed_fields[field] = []
                continue

            # 1) Сначала заменяем course_id -> code_name
            mapped = self.map_dependencies(parsed, final_map)  # <-- тут используем final_map
            logging.debug(f"После map_dependencies для '{field}' => {mapped}")

            # 2) Теперь фильтруем те, что не входят в available_code_names
            final_processed = []
            for group in mapped:
                filtered_codes = []
                for code in group:
                    if code == item.code_name:
                        logging.warning(f"Самоссылка обнаружена: {code} в поле '{field}' курса {item.code_name}. Пропускаем.")
                        continue
                    if code not in available_code_names:
                        logging.warning(f"Код {code} не найден в available_code_names. Игнорируем для {item.code_name}.")
                        continue
                    filtered_codes.append(code)

                if filtered_codes:
                    final_processed.append(filtered_codes)
                else:
                    logging.debug(f"Все коды в группе {group} удалены, элемент игнорируем.")

            logging.debug(f"Итоговая обработка поля '{field}' для {item.code_name}: {final_processed}")
            processed_fields[field] = final_processed

        logging.debug(f"Завершили обработку зависимостей для {item.code_name}. Результат: {processed_fields}")
        return processed_fields
    
    
    def has_cyclic_dependencies(self, items):
        logging.debug("Начинаем проверку циклических зависимостей.")
        graph = {}
        for item in items:
            try:
                predecessors = ast.literal_eval(item.predecessor) if item.predecessor else []
                flat_predecessors = [code.strip() for group in predecessors for code in group]
                graph[item.code_name] = flat_predecessors
                logging.debug(f"Курс {item.code_name} имеет предшественников: {flat_predecessors}")
            except Exception as e:
                logging.error(f"Ошибка при разборе предшественников для курса {item.code_name}: {e}")
                graph[item.code_name] = []

        visited = set()
        stack = []
        cycle_found = False

        def visit(node):
            nonlocal cycle_found
            if node in stack:
                cycle_index = stack.index(node)
                cycle_path = stack[cycle_index:] + [node]
                logging.error(f"Циклическая зависимость обнаружена: {' -> '.join(cycle_path)}")
                cycle_found = True
                return
            if node in visited:
                return
            visited.add(node)
            stack.append(node)
            for neighbor in graph.get(node, []):
                if neighbor not in graph:
                    logging.warning(f"Курс {neighbor}, указанный как предшественник для {node}, отсутствует в списке курсов.")
                    continue
                visit(neighbor)
                if cycle_found:
                    return
            stack.pop()

        for node in graph:
            if cycle_found:
                break
            if node not in visited:
                visit(node)

        if cycle_found:
            logging.debug("Обнаружены циклические зависимости.")
        else:
            logging.debug("Циклических зависимостей не обнаружено.")

        return cycle_found

    def sort_courses(self, items):
        logging.debug("Начинаем сортировку курсов.")
        graph = defaultdict(list)
        in_degree = defaultdict(int)
        course_dict = {item.code_name: item for item in items}

        logging.debug(f"Построение графа для {len(items)} курсов.")

        for item in items:
            in_degree[item.code_name] = 0
            logging.debug(f"Устанавливаем in_degree[{item.code_name}] = 0")

        # Предшественники
        for item in items:
            try:
                predecessors = ast.literal_eval(item.predecessor) if item.predecessor else []
                logging.debug(f"Обрабатываем предшественников курса {item.code_name}: {predecessors}")
                for group in predecessors:
                    for pred_code in group:
                        if pred_code in course_dict:
                            graph[pred_code].append(item.code_name)
                            in_degree[item.code_name] += 1
                            logging.debug(f"Добавлено ребро {pred_code} -> {item.code_name}, увеличиваем in_degree[{item.code_name}] до {in_degree[item.code_name]}")
                        else:
                            logging.warning(f"Предшественник {pred_code} для курса {item.code_name} отсутствует в списке курсов.")
            except Exception as e:
                logging.error(f"Ошибка при обработке предшественников курса {item.code_name}: {e}")

        # Одновременные
        for item in items:
            try:
                simultaneous = ast.literal_eval(item.simultaneous) if item.simultaneous else []
                logging.debug(f"Обрабатываем одновременные курсы для {item.code_name}: {simultaneous}")
                for group in simultaneous:
                    for sim_code in group:
                        if sim_code in course_dict:
                            graph[item.code_name].append(sim_code)
                            in_degree[sim_code] += 1
                            logging.debug(f"Добавлено ребро {item.code_name} -> {sim_code}, in_degree[{sim_code}]={in_degree[sim_code]}")
                        else:
                            logging.warning(f"Одновременный курс {sim_code} для курса {item.code_name} отсутствует в списке курсов.")
            except Exception as e:
                logging.error(f"Ошибка при обработке одновременных курсов для {item.code_name}: {e}")

        queue = deque()
        for course_code in course_dict:
            if in_degree[course_code] == 0:
                queue.append(course_code)
                logging.debug(f"{course_code} добавлен в очередь, т.к. in_degree=0.")

        sorted_courses = []
        while queue:
            current_code = queue.popleft()
            logging.debug(f"Извлекаем {current_code} из очереди для добавления в отсортированный список.")
            sorted_courses.append(course_dict[current_code])
            for neighbor in graph[current_code]:
                in_degree[neighbor] -= 1
                logging.debug(f"Уменьшаем in_degree[{neighbor}] до {in_degree[neighbor]} после обработки {current_code}.")
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
                    logging.debug(f"{neighbor} имеет in_degree=0, добавляем в очередь.")

        if len(sorted_courses) != len(course_dict):
            logging.error("Cycle detected in course dependencies при сортировке: число отсортированных не совпадает с числом курсов.")
            logging.error(f"Отсортировано {len(sorted_courses)} из {len(course_dict)} курсов.")
            unsorted_courses = set(course_dict.keys()) - set(c.code_name for c in sorted_courses)
            logging.error(f"Неотсортированные курсы: {unsorted_courses}")
            return None

        logging.debug(f"Сортировка завершена. Отсортированный список: {[c.code_name for c in sorted_courses]}")
        return sorted_courses

    def generate_plan(self, items):
        self.items = items  # Храним для доступа в других методах
        self.course_dict = {item.code_name: item for item in items}
        logging.debug(f"Начинаем генерацию плана. Имеется {len(items)} курсов.")

        for item in items:
            item.scheduled = False
            item.semester = None
            logging.debug(f"Инициализируем курс {item.code_name}: scheduled=False, semester=None")

        unscheduled_courses = set(item.code_name for item in items)
        completed_courses = set()
        plan = []
        semester_number = 0

        while unscheduled_courses:
            quarter = self.quarters[semester_number % len(self.quarters)]
            current_season = quarter['name']
            max_units = quarter['limit']
            logging.debug(
                f"Семестр {semester_number + 1}, сезон: {current_season}, лимит юнитов: {max_units}"
            )

            semester_courses = []
            semester_units = 0
            made_progress = False

            # 1. Собираем доступные для этого семестра курсы
            available_courses = []
            for item in items:
                if not item.scheduled:
                    # Проверяем, доступен ли курс в данном сезоне
                    if current_season not in item.available_terms:
                        logging.debug(
                            f"Курс {item.code_name} недоступен в сезон {current_season}, пропускаем."
                        )
                        continue
                    # Проверяем, выполнены ли все предшественники
                    predecessors_satisfied = self.check_predecessors(item, completed_courses)
                    if predecessors_satisfied:
                        available_courses.append(item)

            logging.debug(
                f"Доступные курсы для семестра {semester_number + 1}: "
                f"{[c.code_name for c in available_courses]}"
            )

            # 2. Из доступных курсов пытаемся запланировать (учитывая лимиты и одновременные)
            for course in available_courses:
                if course.scheduled:
                    # Возможно, он уже добавлен ранее за этот проход
                    continue

                can_schedule, total_units, courses_to_add = self.can_schedule_course(
                    course, semester_units, completed_courses, current_season
                )
                logging.debug(
                    f"Результат can_schedule для {course.code_name}: "
                    f"can_schedule={can_schedule}, total_units={total_units}, "
                    f"courses_to_add={[c.code_name for c in (courses_to_add or [])]}"
                )

                if can_schedule and (semester_units + total_units) <= max_units:
                    # Добавляем все курсы из этой "группы" (сам курс + coreqs)
                    for c in courses_to_add:
                        if not c.scheduled:
                            c.scheduled = True
                            c.semester = semester_number + 1
                            semester_courses.append(c)
                            unscheduled_courses.discard(c.code_name)
                            logging.debug(
                                f"Запланирован курс {c.code_name} в семестре {semester_number + 1}."
                            )
                    semester_units += total_units
                    made_progress = True
                else:
                    logging.debug(
                        f"Курс {course.code_name} (или его группа) не может быть "
                        f"запланирован в этом семестре."
                    )

            # 3. Если мы вообще не смогли добавить ни одного курса – тупиковая ситуация
            if not made_progress:
                # Проверяем, действительно ли нет ни одного добавленного курса
                if not semester_courses:
                    logging.error(
                        "Не удалось запланировать никакие курсы в этом семестре. Возник тупик."
                    )
                    return None

            # 4. По завершении цикла семестра все курсы, добавленные в semester_courses,
            #    считаем "completed" (сданными) для следующих семестров
            completed_courses.update(c.code_name for c in semester_courses)

            # 5. Добавляем сформированный семестр в общий план
            if semester_courses:
                logging.debug(
                    f"Семестр {semester_number + 1} запланированные курсы: "
                    f"{[c.code_name for c in semester_courses]}"
                )
                plan.append(semester_courses)
                semester_number += 1
            else:
                # Если уже нет курсов для планирования, завершаем
                logging.debug("Не осталось курсов для планирования, завершаем.")
                break

        logging.debug("План успешно сгенерирован.")
        return plan
    
    def check_predecessors(self, course, completed_courses):
        logging.debug(f"Проверка предшественников для {course.code_name}. Завершенные курсы: {completed_courses}")
        predecessors = eval(course.predecessor) if course.predecessor else []
        for group in predecessors:
            logging.debug(f"Проверяем группу предшественников {group} для {course.code_name}")
            group_satisfied = any(code_name in completed_courses for code_name in group)
            if not group_satisfied:
                logging.debug(f"Группа {group} не удовлетворена для {course.code_name}.")
                return False
        logging.debug(f"Все предшественники для {course.code_name} удовлетворены.")
        return True

    def can_schedule_course(self, course, semester_units, completed_courses, current_season):
        logging.debug(f"Проверка возможности расписания курса {course.code_name} в сезон {current_season} при текущих юнитах: {semester_units}, завершенные курсы: {completed_courses}")
        courses_to_add = [course]
        total_units = course.units
        logging.debug(f"Базовые юниты курса {course.code_name}: {total_units}")

        if total_units > 16:
            logging.debug(f"Курс {course.code_name} превышает лимит в 16 юнитов.")
            return False, None, None

        simultaneous_groups = eval(course.simultaneous) if course.simultaneous else []
        logging.debug(f"Одновременные группы для {course.code_name}: {simultaneous_groups}")

        if not simultaneous_groups:
            logging.debug(f"У {course.code_name} нет одновременных курсов, планируем без дополнительных проверок.")
            return True, total_units, courses_to_add

        available_options_per_group = []
        for group in simultaneous_groups:
            logging.debug(f"Проверяем группу одновременных {group} для {course.code_name}")
            available_courses_in_group = []
            for code_name in group:
                if code_name in completed_courses:
                    logging.debug(f"Курс {code_name} уже завершен, пропускаем.")
                    continue
                sim_course = self.get_course_by_code(code_name)
                if sim_course and not sim_course.scheduled:
                    if current_season not in sim_course.available_terms:
                        logging.debug(f"Одновременный курс {sim_course.code_name} недоступен в сезон {current_season}, пропускаем.")
                        continue
                    if self.check_predecessors(sim_course, completed_courses):
                        available_courses_in_group.append(sim_course)
                        logging.debug(f"Одновременный курс {sim_course.code_name} доступен.")
            if not available_courses_in_group:
                if any(code_name in completed_courses for code_name in group):
                    logging.debug(f"Группа {group} уже удовлетворена за счет завершенных курсов.")
                    continue
                else:
                    logging.debug(f"Нет доступных курсов в группе {group} для {course.code_name}, планирование невозможно.")
                    return False, None, None
            else:
                logging.debug(f"Доступные варианты из группы {group}: {[c.code_name for c in available_courses_in_group]}")
                available_options_per_group.append(available_courses_in_group)

        combinations = list(product(*available_options_per_group)) if available_options_per_group else [()]
        logging.debug(f"Возможные комбинации: {[[c.code_name for c in combo] for combo in combinations]}")

        for combo in combinations:
            combo_courses = list(combo)
            combo_units = sum(c.units for c in combo_courses)
            total_combo_units = total_units + combo_units
            logging.debug(f"Проверяем комбинацию {[c.code_name for c in combo_courses]}: total_combo_units={total_combo_units}")
            if semester_units + total_combo_units <= 16:
                logging.debug(f"Комбинация подходит! Добавляем курсы {[c.code_name for c in combo_courses]} для {course.code_name}.")
                courses_to_add.extend(combo_courses)
                total_units += combo_units
                return True, total_units, courses_to_add

        logging.debug(f"Не удалось найти подходящую комбинацию для {course.code_name}.")
        return False, None, None

    def get_course_by_code(self, code_name):
        return self.course_dict.get(code_name)

    def print_plan(self, plan):
        semester_labels = self.get_semester_labels(len(plan))

        for idx, semester in enumerate(plan):
            print(f"\n{semester_labels[idx]}")
            total_units = 0
            for course in semester:
                predecessors = eval(course.predecessor)
                simultaneous = eval(course.simultaneous)
                print(f"Курс: {course.code_name}, Units: {course.units}, Predecessors: {predecessors}, Simultaneous: {simultaneous}, Terms: {course.terms}")
                total_units += course.units
            print(f"Итоговый units за семестр: {total_units}")

    def get_codes(self):
        manufacturing_codes_rows = ManufacturingCode.query.all()
        secondary_codes_rows = SecondaryCode.query.all()
        additional_codes_rows = db.session.query(Item.id, Item.code_name, Item.display).all()

        codes_objs = {}
        manufacturing_codes = []
        secondary_codes = []
        additional_codes = []
        extra_codes = []

        for code in manufacturing_codes_rows:
            data = {}
            data['label'] = code.code_name
            data['value'] = code.item_group_id
            manufacturing_codes.append(data)
            logging.debug(f"Добавлен производственный код: {data}")

        for code in secondary_codes_rows:
            data = {}
            data['label'] = code.code_name
            data['value'] = code.item_group_id
            secondary_codes.append(data)
            logging.debug(f"Добавлен вторичный код: {data}")

        seen_code_names = set()
        for code in additional_codes_rows:
            if code.code_name not in seen_code_names:
                data = {
                    'label': f"({code.code_name}) {code.display}",
                    'value': code.id
                }
                additional_codes.append(data)
                extra_codes.append(data)
                seen_code_names.add(code.code_name)
                logging.debug(f"Добавлен дополнительный код: {data}")

        codes_objs['manufacturing_codes'] = manufacturing_codes
        codes_objs['secondary_codes'] = secondary_codes
        codes_objs['additional_codes'] = additional_codes
        codes_objs['extra_codes'] = extra_codes

        # logging.debug(f"Получены все коды: {codes_objs}")
        return json.dumps(codes_objs)

    def get_plans(self, request):
        token = None
        if "Authorization" in request.headers:
            token = request.headers["Authorization"].split(" ")[1]
            logging.debug("Токен авторизации получен из заголовков.")
        else:
            logging.error("Токен авторизации не найден в заголовках.")
            return jsonify(status_code=401, result='error', message='Authorization token is missing'), 401

        try:
            current_user = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
            logging.debug(f"Декодирован JWT для пользователя: {current_user['user_email']}")
        except jwt.ExpiredSignatureError:
            logging.error("Token has expired.")
            return jsonify(status_code=401, result='error', message='Token has expired'), 401
        except jwt.InvalidTokenError:
            logging.error("Invalid token.")
            return jsonify(status_code=401, result='error', message='Invalid token'), 401

        user = User.query.filter_by(email=current_user["user_email"]).first()
        if not user:
            logging.error(f"User with email {current_user['user_email']} not found.")
            return jsonify(status_code=404, result='error', message='User not found'), 404

        plans = Plan.query.filter_by(user_id=user.id).all()
        logging.debug(f"Найдено {len(plans)} планов для пользователя {user.email}.")

        plans_arr = []
        for plan in plans:
            plan_obj = {}
            plan_obj['label'] = plan.plan_name
            plan_obj['value'] = plan.id
            plan_obj['checked'] = False
            plans_arr.append(plan_obj)
            logging.debug(f"Добавлен план: {plan_obj}")

        logging.debug(f"Получены планы для пользователя {user.email}: {[plan.plan_name for plan in plans]}")
        return json.dumps(plans_arr)

    def get_single_plan(self, request):
        data = request.form
        planId = data.get('id')

        if not planId:
            logging.error("Plan ID is required.")
            return jsonify({"error": "Plan ID is required"}), 400

        plan = Plan.query.filter_by(id=planId).first()
        if not plan:
            logging.error(f"Plan with ID {planId} not found.")
            return jsonify({"error": "Plan not found"}), 404

        def extract_code_names(items):
            code_names = []
            for quarter in items:
                for item in quarter['items']:
                    code_names.append(item['code_name'])
            return code_names

        code_names = extract_code_names(plan.items)
        logging.debug(f"Code names extracted from plan {planId}: {code_names}")

        # Requirements are not included in the response as per user request
        items = Item.query.filter(~Item.code_name.in_(code_names)).all()
        logging.debug(f"Дополнительные курсы, не включенные в план: {[item.code_name for item in items]}")

        quarter_items = []
        added_code_names = set()

        for item in items:
            code_name = item.code_name
            if code_name not in added_code_names:
                quarter_item = {
                    'locked': False,
                    'done': False,
                    'item_id': item.id,
                    'code_name': code_name,
                    'letter': item.display,
                    'units': item.units,
                    'predecessor': item.original_predecessor,
                    'simultaneous': item.original_simultaneous,
                    'term': item.terms
                }
                quarter_items.append(quarter_item)
                added_code_names.add(code_name)
                logging.debug(f"Добавлен дополнительный курс для плана: {quarter_item}")
        requirements = Requirement.get_required_fields()
        plan_obj = {
            'id': plan.id,
            'plan_name': plan.plan_name,
            'items': plan.items,
            'additional_items': quarter_items,
            'requirements': requirements
        }

        logging.debug(f"Получен план: {plan_obj}")
        return jsonify(plan_obj)

    def save_plan(self, request):
        data = request.form
        planName = data.get('planName')
        items = json.loads(data.get('items', '[]'))  # Deserialize the items if it's JSON
        logging.debug(f"Получен запрос на сохранение плана. Имя плана: {planName}, Items: {items}")

        if "Authorization" in request.headers:
            token = request.headers["Authorization"].split(" ")[1]
            logging.debug("Токен авторизации получен из заголовков.")
        else:
            logging.error("Authorization token not found in headers.")
            return jsonify(status_code=401, result='error', message='Authorization token is missing'), 401

        try:
            current_user = jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=["HS256"])
            logging.debug(f"Декодирован JWT для пользователя: {current_user['user_email']}")
        except jwt.ExpiredSignatureError:
            logging.warning("Token has expired.")
            return jsonify(status_code=401, result='error', message='Token has expired'), 401
        except jwt.InvalidTokenError:
            logging.warning("Invalid token.")
            return jsonify(status_code=401, result='error', message='Invalid token'), 401

        user = User.query.filter_by(email=current_user["user_email"]).first()
        if not user:
            logging.error(f"User with email {current_user['user_email']} not found.")
            return jsonify(status_code=404, result='error', message='User not found'), 404

        rows = Plan.query.filter_by(user_id=user.id, plan_name=planName).all()
        if rows:
            logging.warning(f"Plan name '{planName}' уже существует для пользователя {user.email}.")
            return jsonify(status_code=409, result='error', message='Plan name already exists'), 409

        try:
            items = json.loads(data.get('items'))
            logging.debug(f"Десериализованы items для сохранения: {items}")
        except json.JSONDecodeError:
            logging.error("Invalid JSON for items.")
            return jsonify(status_code=400, result='error', message='Invalid JSON for items'), 400

        new_plan = Plan(user_id=user.id, plan_name=planName, items=items)
        db.session.add(new_plan)
        db.session.commit()

        logging.info(f"Создан новый план '{planName}' для пользователя {user.email}.")
        return jsonify(status_code=201, result='success', message='Plan created'), 201

    def update_plan(self, request):
        data = request.form
        plan_id = data.get('id')
        plan = Plan.query.filter_by(id=plan_id).first()

        if not plan:
            logging.error(f"Plan with ID {plan_id} не найден.")
            return jsonify(status_code=404, result='error', message='Plan not found'), 404

        try:
            items = json.loads(data.get('items'))
            logging.debug(f"Обновленные items для плана {plan_id}: {items}")
        except json.JSONDecodeError:
            logging.error("Invalid JSON for items.")
            return jsonify(status_code=400, result='error', message='Invalid JSON for items'), 400

        plan.items = items
        db.session.commit()

        logging.info(f"План с ID {plan_id} обновлен.")
        return jsonify(status_code=201, result='success', message='Plan updated'), 201

    def delete_plans(self, request):
        data = request.form
        plans = json.loads(data.get('plans', '[]'))
        logging.debug(f"Удаление планов с ID: {plans}")

        if not plans:
            logging.warning("Нет планов для удаления.")
            return jsonify(status_code=400, result='error', message='No plans provided to delete'), 400

        Plan.query.filter(Plan.id.in_(plans)).delete(synchronize_session='fetch')
        db.session.commit()

        logging.info(f"Удалены планы с ID: {plans}")
        return jsonify(status_code=201, result='success', message='Plans deleted'), 201

    def recalculate_plan(self, request):
        data = request.form
        quarters = json.loads(data.get('quarters', '[]'))
        done = json.loads(data.get('done', '[]'))
        done_codes = [d["item"]["code_name"] for d in done]
        logging.debug(f"Recalculating plan. Quarters: {quarters}, Done codes: {done_codes}")
        return self._recalculate_plan(quarters, done_codes, done)[0]

    def check_plan(self, request):
        try:
            def str_or(input_list):
                return ' OR '.join(input_list)

            def process_dependency(dependency):
                if not dependency:
                    return []
                course_codes = set()
                if isinstance(dependency, str):
                    # Try to parse as JSON
                    try:
                        dependency = json.loads(dependency)
                    except json.JSONDecodeError:
                        # If JSON parsing fails, assume it's a string that may contain commas
                        dependency = [dependency]
                if isinstance(dependency, list):
                    for item in dependency:
                        if isinstance(item, str):
                            # Split by commas
                            codes = [code.strip() for code in item.split(',')]
                            course_codes.update(codes)
                        elif isinstance(item, list):
                            for subitem in item:
                                if isinstance(subitem, str):
                                    codes = [code.strip() for code in subitem.split(',')]
                                    course_codes.update(codes)
                                else:
                                    raise ValueError("Invalid dependency format: expected string in list.")
                        else:
                            raise ValueError("Invalid dependency format: expected string or list.")
                else:
                    raise ValueError("Invalid dependency format: expected string or list.")
                return list(course_codes)

            items_json = request.form.get("items", "[]")
            quarters = json.loads(items_json)
            logging.debug(f"Plan validation. Quarters: {quarters}")

            errors = []

            # Collect all course codes in the plan
            courses_in_plan = set()
            for quarter in quarters:
                items = quarter.get("items", [])
                for item in items:
                    courses_in_plan.add(item.get('code_name'))

            # Initialize completed courses with courses marked as 'done'
            completed_courses = set()
            for quarter in quarters:
                items = quarter.get("items", [])
                for item in items:
                    if item.get('done', False):
                        completed_courses.add(item.get('code_name'))

            # Process each semester
            for semester_index, quarter in enumerate(quarters):
                semester_courses = quarter.get("items", [])
                total_units = 0
                semester_course_codes = set()
                for item in semester_courses:
                    code_name = item.get('code_name')
                    units = item.get('units', 0)
                    total_units += units
                    semester_course_codes.add(code_name)
                if total_units > 16:
                    errors.append(f"Semester {semester_index + 1} exceeds the unit limit of 16 with {total_units} units.")

                # Validate each course in the semester
                for item in semester_courses:
                    code_name = item.get('code_name')
                    if item.get('locked', False):
                        logging.debug(f"Course {code_name} is locked. Skipping validation.")
                        continue
                    if item.get('done', False):
                        logging.debug(f"Course {code_name} is already completed. Skipping validation.")
                        continue

                    # Validate prerequisites
                    predecessor = item.get('predecessor', [])
                    try:
                        predecessor_courses = process_dependency(predecessor)
                        logging.debug(f"Validating prerequisites for {code_name}: {predecessor_courses}")
                    except ValueError as e:
                        errors.append(f"Invalid prerequisites for course {code_name}: {e}")
                        continue

                    if predecessor_courses:
                        # Check if any of the predecessor courses have been completed
                        if not any(course in completed_courses for course in predecessor_courses):
                            formatted_courses = str_or(predecessor_courses)
                            errors.append(f"Course {code_name} has unmet prerequisites: {formatted_courses}.")

                    # Validate corequisites
                    simultaneous = item.get('simultaneous', [])
                    try:
                        simultaneous_courses = process_dependency(simultaneous)
                        logging.debug(f"Validating corequisites for {code_name}: {simultaneous_courses}")
                    except ValueError as e:
                        errors.append(f"Invalid corequisites for course {code_name}: {e}")
                        continue

                    if simultaneous_courses:
                        # Check if any of the corequisite courses are in the same semester
                        if not any(course in semester_course_codes and course != code_name for course in simultaneous_courses):
                            formatted_courses = str_or(simultaneous_courses)
                            errors.append(f"Course {code_name} requires corequisite(s): {formatted_courses} in the same semester.")

                    # After validation, add the course to completed_courses
                    completed_courses.add(code_name)

            errors = list(set(errors))
            if errors:
                response_json = json.dumps({
                    "status_code": 401,
                    "result": "error",
                    "message": errors
                })
                logging.debug(f"Errors during plan validation: {errors}")
                return Response(response_json, mimetype='application/json'), 401
            else:
                response_json = json.dumps({
                    "status_code": 201,
                    "result": "success"
                })
                logging.debug("Plan successfully validated without errors.")
                return Response(response_json, mimetype='application/json'), 201

        except Exception as e:
            error_message = traceback.format_exc()
            print(error_message)
            logging.error(f"Unhandled exception: {error_message}")
            return jsonify(status_code=500, result='error', message=str(e), details=error_message), 500
