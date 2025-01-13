import json

# Классы и функции для алгоритма пересортировки
def read_data(file_path):
    with open(file_path, 'r') as file:
        data = json.load(file)
    return data

class Course:
    def __init__(self, item_id, code_name, units, predecessors=[], simultaneous=None, term=None, locked=False, done=False, letter=None, standing=None):
        self.locked = locked
        self.done = done
        self.item_id = item_id
        self.code_name = code_name
        self.letter = letter
        self.units = units
        self.predecessors = predecessors
        self.simultaneous = simultaneous
        self.term = term
        self.standing = standing
        self.assigned = False

    def to_dict(self):
        # Преобразование предшественников обратно в строку JSON для соответствия исходному формату
        return {
            "locked": self.locked,
            "done": self.done,
            "item_id": self.item_id,
            "code_name": self.code_name,
            "letter": self.letter,
            "units": self.units,
            "predecessor": json.dumps(self.predecessors) if self.predecessors else None,
            "simultaneous": self.simultaneous,
            "term": self.term,
            "standing": self.standing
        }

class Semester:
    def __init__(self, label, max_units, quarter_num=None, quarter_year=None):
        self.label = label
        self.max_units = max_units
        self.courses = []
        self.current_units = 0
        self.quarter_num = quarter_num
        self.quarter_year = quarter_year

    def add_course(self, course):
        """Добавляет курс в семестр, если общее количество юнитов не превышает максимально допустимое."""
        if self.current_units + course.units <= self.max_units:
            self.courses.append(course)
            self.current_units += course.units
            return True
        else:
            return False

    def to_dict(self):
        return {
            "quarter_label": self.label,
            "quarter_num": self.quarter_num,
            "quarter_year": self.quarter_year,
            "total_units": self.max_units,
            "items": [course.to_dict() for course in self.courses]
        }


def create_courses_list(data):
    courses = []
    for quarter in data:
        for item in quarter["items"]:
            predecessors = json.loads(item["predecessor"]) if item["predecessor"] else []
            simultaneous = item["simultaneous"]
            courses.append(Course(item["item_id"], item["code_name"], item["units"], predecessors, simultaneous, item["term"]))
    return courses

def can_add_course(course, semesters, courses_dict, course_semester_mapping, current_semester_index, check_simultaneous=True):
    if course.assigned:
        return False
    for pred_code_name in course.predecessors:
        # Проверяем, есть ли предшественник в courses_dict и был ли он назначен
        if pred_code_name in courses_dict:
            pred_course = courses_dict[pred_code_name]
            # Проверяем, что предшественник назначен в семестр, который идет до текущего семестра
            if not (pred_course.assigned and course_semester_mapping[pred_code_name] < current_semester_index):
                return False
                
    # Проверяем, есть ли достаточно места для одновременного курса, если это необходимо
    if check_simultaneous and course.simultaneous and course.simultaneous in courses_dict:
        simultaneous_course = courses_dict[course.simultaneous]
        # Мы предполагаем, что одновременный курс будет добавлен в тот же семестр, поэтому проверяем его заранее
        if not simultaneous_course.assigned:
            return False
            
    return True

def assign_courses_to_semesters(courses, semesters, courses_dict):
    # Инициализируем словарь внутри функции для отслеживания семестра назначения каждого курса
    course_semester_mapping = {}

    for course in courses:
        if course.assigned:  # Если курс уже назначен, пропускаем его
            continue
        
        for semester_index, semester in enumerate(semesters, start=1):
            # Проверяем, можно ли добавить текущий курс в семестр
            if can_add_course(course, semesters, courses_dict, course_semester_mapping, semester_index, check_simultaneous=False):
                if semester.add_course(course):
                    course.assigned = True
                    course_semester_mapping[course.code_name] = semester_index  # Отмечаем семестр для курса

                    # Если у курса есть одновременный курс, обрабатываем его
                    if course.simultaneous and course.simultaneous in courses_dict:
                        simultaneous_course = courses_dict[course.simultaneous]
                        # Проверяем, можно ли добавить одновременный курс в этот же семестр
                        if can_add_course(simultaneous_course, semesters, courses_dict, course_semester_mapping, semester_index, check_simultaneous=True):
                            # Проверяем, хватит ли места в семестре для добавления одновременного курса
                            if semester.current_units + simultaneous_course.units <= semester.max_units:
                                semester.add_course(simultaneous_course)
                                simultaneous_course.assigned = True
                                course_semester_mapping[simultaneous_course.code_name] = semester_index
                    break  # Прекращаем поиск семестра для текущего курса после успешного добавления

    return course_semester_mapping

# Функции для проверки корректности распределения
def check_units_in_semesters(semesters):
    for semester in semesters:
        if semester.current_units > semester.max_units:
            return False, f"{semester.label} exceeds max units"
    return True, "Units check passed"

def check_predecessors(courses, semesters):
    semester_course_mapping = {}
    for i, semester in enumerate(semesters, 1):
        for course in semester.courses:
            semester_course_mapping[course.code_name] = i

    for course in courses:
        if course.code_name == "EC-451":
            print()
        for pred in course.predecessors:
            if pred in courses_dict:
                if pred not in semester_course_mapping or semester_course_mapping[pred] >= semester_course_mapping[course.code_name]:
                    return False, f"Course {course.code_name} has predecessor {pred} in the wrong semester"
    return True, "Predecessors check passed"

def check_simultaneous_courses(courses, semesters):
    semester_course_mapping = {}
    for i, semester in enumerate(semesters, 1):
        for course in semester.courses:
            semester_course_mapping[course.code_name] = i
    
    for course in courses:
        
        if course.simultaneous in courses_dict and course.simultaneous and semester_course_mapping[course.code_name] != semester_course_mapping.get(course.simultaneous, -1):
            return False, f"Course {course.code_name} and its simultaneous course {course.simultaneous} are in different semesters"
    return True, "Simultaneous courses check passed"

def check_total_courses(courses, semesters):
    total_assigned_courses = sum(len(semester.courses) for semester in semesters)
    if total_assigned_courses != len(courses):
        return False, f"Mismatch in total courses: expected {len(courses)}, found {total_assigned_courses}"
    return True, "Total courses check passed"

def validate_sorted_courses(courses, semesters):
    checks = [check_units_in_semesters, check_predecessors, check_simultaneous_courses, check_total_courses]
    errors = []

    # Проверяем, что только check_units_in_semesters принимает один аргумент
    valid, message = check_units_in_semesters(semesters)
    if not valid:
        errors.append(message)

    # Остальные функции проверки принимают два аргумента
    for check_func in checks[1:]:
        valid, message = check_func(courses, semesters)
        if not valid:
            errors.append(message)

    if errors:
        return False, "Validation errors:\n" + "\n".join(errors)
    return True, "All checks passed"

def sort_courses_by_predecessors_and_simultaneous(courses, courses_dict):
    sorted_courses = []
    visited = set()
    simultaneous_markers = set()  # Для отслеживания помеченных simultaneous курсов

    def visit(course):
        if course.code_name not in visited:
            visited.add(course.code_name)
            # Сначала обрабатываем всех предшественников курса
            for pred_code_name in course.predecessors:
                if pred_code_name in courses_dict:
                    visit(courses_dict[pred_code_name])


            if course.code_name not in simultaneous_markers:
                # Добавляем текущий курс в отсортированный список
                sorted_courses.append(course)

                if course.simultaneous and course.simultaneous in courses_dict:
                    sorted_courses.append(courses_dict[course.simultaneous])

    for course in courses:
        if course.simultaneous and course.simultaneous in courses_dict:
            simultaneous_markers.add(course.simultaneous)
    
    for course in courses:
        visit(course)

    return sorted_courses

def create_courses_and_semesters(data):
    semesters = []
    courses = []
    courses_dict = {}

    # Перебираем все семестры в данных
    for quarter in data:
        semester = Semester(quarter['quarter_label'], quarter['total_units'], quarter.get('quarter_num'), quarter.get('quarter_year'))
        semesters.append(semester)

        # Перебираем все курсы в текущем семестре
        for item in quarter['items']:
            # Преобразуем строку предшественников в список, если она не пустая
            predecessors = json.loads(item['predecessor']) if item['predecessor'] else []
            # Создаем объект курса
            course = Course(
                item_id=item['item_id'],
                code_name=item['code_name'],
                units=item['units'],
                predecessors=predecessors,
                simultaneous=item.get('simultaneous'),  # Используем .get для обработки случая отсутствия ключа
                term=item.get('term'),
                locked=item.get('locked', False),  # Значение по умолчанию False, если ключ отсутствует
                done=item.get('done', False),
                letter=item.get('letter'),
                standing=item.get('standing')
            )
            # Добавляем курс в словарь и в текущий семестр
            courses_dict[course.code_name] = course
            courses.append(course)

    return courses_dict, semesters, courses

# Чтение данных из JSON в классы
def sort(data):
    courses_dict, semesters, courses = create_courses_and_semesters(data)

    sorted_courses = sort_courses_by_predecessors_and_simultaneous(courses, courses_dict)
    assign_courses_to_semesters(sorted_courses, semesters, courses_dict)

    # Преобразование объектов классов обратно в JSON
    final_data = [semester.to_dict() for semester in semesters]

    # Сериализация обратно в строку JSON
    final_json = json.dumps(final_data, indent=4)

    # Или сохраните в файл
    return final_json