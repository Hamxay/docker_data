import os
import json
import logging
from flask import Flask, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_cors import CORS
from datetime import datetime
import ast
from collections import deque, defaultdict
from itertools import product
from rich.console import Console
from rich.table import Table
from rich.progress import Progress
from rich.panel import Panel
from rich import box
import traceback

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)

# Initialize Flask app and database
db = SQLAlchemy()

def create_app():
    app = Flask(__name__)

    # Path to your database
    db_path = '/Users/im01zhas/Code/Schedule/backend/app/database/database.db'
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'  # Use your actual database path
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    CORS(app, resources={r"/*": {"origins": "*"}})

    return app

# Define Item model
class Item(db.Model):
    __tablename__ = 'items'
    id = db.Column(db.BigInteger, primary_key=True)
    display = db.Column(db.String)
    code_name = db.Column(db.String)
    units = db.Column(db.Float)
    predecessor = db.Column(db.String)
    simultaneous = db.Column(db.String)
    item_group_id = db.Column(db.String, index=True)
    terms = db.Column(db.String)
    standing = db.Column(db.String)

# Define Requirement model
class Requirement(db.Model):
    __tablename__ = 'requirements'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    code_name = db.Column(db.String, index=True)
    course_id = db.Column(db.String, index=True)
    course_name = db.Column(db.String)
    credit_hours = db.Column(db.Float)

    @classmethod
    def get_requirements_by_course_ids(cls, course_ids):
        requirements = cls.query.filter(cls.course_id.in_(course_ids)).all()
        return {req.course_id: [req.code_name for req in requirements] for req in requirements}

# Define PlanManager class
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
        data = request.json
        if not data:
            logging.error("No data provided in request.")
            return jsonify(status_code=400, result="error", message="No data provided"), 400

        # Get course codes from the request
        manufacturing_codes = data.get('manufacturing_codes', [])
        secondary_codes = data.get('secondary_codes', [])
        additional_codes = data.get('additional_codes', [])
        extra_codes = data.get('extra_codes', [])

        logging.debug(f"Received course codes: manufacturing_codes={manufacturing_codes}, secondary_codes={secondary_codes}, additional_codes={additional_codes}, extra_codes={extra_codes}")

        # Fetch items from the database
        items = []
        extra_items = []

        if manufacturing_codes:
            fetched_items = Item.query.filter(Item.item_group_id.in_(manufacturing_codes)).all()
            items.extend(fetched_items)
            logging.debug(f"Fetched manufacturing codes: {[item.code_name for item in fetched_items]}")

        if secondary_codes:
            fetched_items = Item.query.filter(Item.item_group_id.in_(secondary_codes)).all()
            items.extend(fetched_items)
            logging.debug(f"Fetched secondary codes: {[item.code_name for item in fetched_items]}")

        if additional_codes:
            fetched_items = Item.query.filter(Item.id.in_(additional_codes)).all()
            items.extend(fetched_items)
            logging.debug(f"Fetched additional codes: {[item.code_name for item in fetched_items]}")

        if extra_codes:
            fetched_items = Item.query.filter(Item.id.in_(extra_codes)).all()
            extra_items.extend(fetched_items)
            logging.debug(f"Fetched extra codes: {[item.code_name for item in fetched_items]}")

        # Remove duplicates based on id
        unique_items = {item.id: item for item in items}
        items = list(unique_items.values())
        logging.debug(f"Unique courses after removing duplicates: {[item.code_name for item in items]}")

        # Remove courses that are in extra_items
        extra_item_ids = {item.id for item in extra_items}
        items = [item for item in items if item.id not in extra_item_ids]
        logging.debug(f"Courses after removing extra_items: {[item.code_name for item in items]}")

        # Collect available code_names from current items
        available_code_names = {item.code_name for item in items}

        # Process dependencies and make copies of items
        processed_items = []

        for item in items:
            # Create a copy of the item to avoid modifying the original database object
            item_copy = self.copy_item(item)
            
            # Process dependencies
            processed = self.process_dependencies(item_copy, available_code_names)
            
            # Update the copy with processed dependencies
            item_copy.predecessor = str(processed['predecessor'])
            item_copy.simultaneous = str(processed['simultaneous'])
            
            # Process terms
            item_copy.available_terms = self.parse_terms(item_copy.terms)
            
            # Add the processed copy to the list
            processed_items.append(item_copy)

        items = processed_items

        # Check if all dependencies are present
        all_dependencies_present, missing_dependencies = self.check_all_dependencies_present(items)
        if not all_dependencies_present:
            missing_deps_str = ', '.join(missing_dependencies)
            logging.error(f"Missing necessary dependencies: {missing_deps_str}")
            return jsonify(status_code=400, result="error",
                        message=f"Missing necessary dependencies: {missing_deps_str}"), 400

        # Check for cyclic dependencies
        has_cycle, cycles = self.has_cyclic_dependencies(items)
        if has_cycle:
            # Formulate the error message with cycle details
            cycles_str_list = []
            for cycle in cycles:
                cycle.append(cycle[0])  # Close the cycle for visualization
                cycle_str = ' -> '.join(cycle)
                cycles_str_list.append(cycle_str)
            cycles_str = '; '.join(cycles_str_list)
            logging.error(f"Cyclic dependencies detected: {cycles_str}")
            return jsonify(status_code=400, result="error",
                           message=f"Cyclic dependencies detected: {cycles_str}"), 400

        # Call sort_courses before generate_plan
        sorted_items, cycles_str = self.sort_courses(items)
        if sorted_items is None:
            logging.error(f"Failed to sort courses due to cyclic dependencies. Cycles detected: {cycles_str}")
            return jsonify(status_code=400, result="error",
                           message=f"Failed to sort courses due to cyclic dependencies. Cycles detected: {cycles_str}"), 400

        # Generate the plan based on the sorted courses
        plan, error_details = self.generate_plan(sorted_items)
        if plan is None:
            logging.error(f"Failed to generate plan. Details: {error_details}")
            return jsonify(status_code=400, result="error", message=f"Failed to generate plan. Details: {error_details}"), 400

        # Format the plan for return
        formatted_plan = []
        semester_labels = self.get_semester_labels(len(plan))

        for idx, semester in enumerate(plan):
            semester_info = {
                "semester": idx + 1,
                "label_name": semester_labels[idx],
                "courses": [],
                "total_units": 0
            }
            for course in semester:
                semester_info["courses"].append({
                    "code_name": course.code_name,
                    "units": course.units,
                    "predecessors": eval(course.predecessor),
                    "simultaneous": eval(course.simultaneous),
                    "terms": course.terms
                })
                semester_info["total_units"] += course.units
            formatted_plan.append(semester_info)

        return jsonify(formatted_plan), 200

    def parse_terms(self, terms_str):
        """
        Parses the 'terms' string and returns a list of available seasons for the course.
        If terms_str is None, returns a list of all seasons.

        Args:
            terms_str (str): The terms string from the course.

        Returns:
            list: List of available seasons for the course.
        """
        if not terms_str or terms_str.strip() == '':
            # If terms are not specified, the course is available in all seasons
            return [season['name'] for season in self.quarters]
        terms = [term.strip() for term in terms_str.split(',')]
        seasons = [self.season_mapping.get(term, term) for term in terms]
        return seasons

    def check_all_dependencies_present(self, items):
        """
        Checks if all dependencies are present in the list of courses.

        Args:
            items (list): List of Item objects.

        Returns:
            tuple: (bool, set) True and None if all dependencies are present,
                   False and set of missing dependencies otherwise.
        """
        # Collect all code_names from courses
        item_code_names = set(item.code_name for item in items)

        # Collect all dependencies
        dependencies = set()
        for item in items:
            for field in ['predecessor', 'simultaneous']:
                field_value = getattr(item, field)
                if field_value:
                    try:
                        dep_lists = ast.literal_eval(field_value)
                        for group in dep_lists:
                            for code_name in group:
                                dependencies.add(code_name)
                    except (ValueError, SyntaxError) as e:
                        logging.error(f"Error parsing field '{field}' for course {item.code_name}: {e}")
                        continue

        # Find missing dependencies
        missing_dependencies = dependencies - item_code_names

        if missing_dependencies:
            return False, missing_dependencies
        else:
            return True, None

    def get_semester_labels(self, num_semesters):
        """
        Generates labels for semesters considering seasons and current date.

        Args:
            num_semesters (int): Total number of semesters in the plan.

        Returns:
            list: List of labels for each semester.
        """
        labels = []
        # Get current date
        current_date = datetime.now()

        # Determine current year and season
        current_year = current_date.year
        current_month = current_date.month

        # Determine the closest season
        if current_month >= 8 and current_month <= 12:
            # Current season is Fall
            season_index = 0  # Fall
        else:
            # Current season is Spring
            season_index = 1  # Spring
            if current_month >= 1 and current_month <= 7:
                current_year += 1  # Next year for the next season

        year = current_year
        for i in range(num_semesters):
            season = self.quarters[season_index % len(self.quarters)]
            labels.append(f"{season['name']} {year}")
            if season['name'] == 'Spring':
                year += 1  # Move to next year after Spring
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

    def process_dependencies(self, item, available_code_names):
        """
        Processes the 'predecessor' and 'simultaneous' fields of an Item object.

        Args:
            item (Item): The Item object to process.
            available_code_names (set): Set of code_names already loaded in items.

        Returns:
            dict: Dictionary with processed 'predecessor' and 'simultaneous' fields.
        """
        processed_fields = {}

        for field in ['predecessor', 'simultaneous']:
            field_str = getattr(item, field)
            if not field_str:
                processed_fields[field] = []
                logging.debug(f"Field '{field}' for course {item.code_name} is empty.")
                continue

            try:
                # Parse the string into a list
                parsed = ast.literal_eval(field_str)
                logging.debug(f"Parsing field '{field}' for course {item.code_name}: {parsed}")
            except (ValueError, SyntaxError) as e:
                logging.error(f"Error parsing field '{field}' for course {item.code_name}: {e}")
                processed_fields[field] = []
                continue

            processed = []

            for elem in parsed:
                if isinstance(elem, str):
                    if ',' in elem:
                        # Element contains multiple codes separated by commas
                        codes = [c.strip() for c in elem.split(',')]
                        new_codes = []
                        for code in codes:
                            # Find corresponding requirements by course_id
                            reqs = Requirement.query.filter_by(course_id=code).all()
                            if reqs:
                                # Replace course_id with list of code_names that exist in items
                                code_names = [r.code_name for r in reqs if r.code_name in available_code_names]
                                if code_names:
                                    new_codes.extend(code_names)
                                    logging.debug(f"Course '{code}' replaced with requirements: {code_names}")
                                else:
                                    if code in available_code_names:
                                        new_codes.append(code)
                                        logging.debug(f"Requirements for course '{code}' not found, but course exists in items. Added as ['{code}'].")
                            else:
                                # If no requirements, check if code is in items
                                if code in available_code_names:
                                    new_codes.append(code)
                                    logging.debug(f"Requirements for course '{code}' not found, but course exists in items. Added as ['{code}'].")
                        if new_codes:
                            # Add the processed sublist
                            processed.append(list(set(new_codes)))
                            logging.debug(f"Processed sublist: {list(set(new_codes))}")
                    else:
                        # Element contains one code
                        reqs = Requirement.query.filter_by(course_id=elem).all()
                        if reqs:
                            # Replace course_id with list of code_names that exist in items
                            code_names = [r.code_name for r in reqs if r.code_name in available_code_names]
                            if code_names:
                                processed.append(code_names)
                                logging.debug(f"Course '{elem}' replaced with requirements: {code_names}")
                            else:
                                if elem in available_code_names:
                                    processed.append([elem])  # Add as list
                                    logging.debug(f"Requirements for course '{elem}' not found, but course exists in items. Added as ['{elem}'].")
                        else:
                            # If no requirements, check if code is in items
                            if elem in available_code_names:
                                processed.append([elem])  # Add as list
                                logging.debug(f"Requirements for course '{elem}' not found, but course exists in items. Added as ['{elem}'].")
                else:
                    # If element is not a string, leave it unchanged
                    processed.append(elem)
                    logging.debug(f"Element is not a string and left unchanged: {elem}")
            
            logging.debug(f"Final processing: {processed}")
            processed_fields[field] = processed

        return processed_fields

    def has_cyclic_dependencies(self, items):
        """
        Checks for cyclic dependencies among courses.

        Args:
            items (list): List of Item objects.

        Returns:
            tuple: (bool, list) True and list of cycles if cycles are found,
                   False and empty list otherwise.
        """
        graph = {}
        for item in items:
            predecessors = eval(item.predecessor) if item.predecessor else []
            flat_predecessors = [code for group in predecessors for code in group]
            graph[item.code_name] = flat_predecessors

        visited = set()
        on_stack = set()
        cycles = []

        def dfs(node, path):
            if node in on_stack:
                # Cycle detected
                cycle_start_index = path.index(node)
                cycle = path[cycle_start_index:].copy()
                if cycle not in cycles:
                    cycles.append(cycle)
                return
            if node in visited:
                return
            visited.add(node)
            on_stack.add(node)
            path.append(node)
            for neighbor in graph.get(node, []):
                dfs(neighbor, path)
            on_stack.remove(node)
            path.pop()

        for node in graph:
            if node not in visited:
                dfs(node, [])

        if cycles:
            return True, cycles
        else:
            return False, []

    def sort_courses(self, items):
        """
        Sorts courses ensuring that predecessors come before dependents,
        and courses with simultaneous requirements are placed appropriately.

        Args:
            items (list): List of Item objects.

        Returns:
            tuple: (list, str) Sorted list of Item objects, or (None, cycles_str) if a cycle is detected.
        """
        # Build dependency graph
        graph = defaultdict(list)
        in_degree = defaultdict(int)
        course_dict = {item.code_name: item for item in items}

        # Initialize in-degree and graph
        for item in items:
            in_degree[item.code_name] = 0

        # Process predecessors
        for item in items:
            predecessors = eval(item.predecessor) if item.predecessor else []
            for group in predecessors:
                for pred_code in group:
                    if pred_code in course_dict:
                        graph[pred_code].append(item.code_name)
                        in_degree[item.code_name] += 1

        # Process simultaneous courses
        for item in items:
            simultaneous = eval(item.simultaneous) if item.simultaneous else []
            for group in simultaneous:
                for sim_code in group:
                    if sim_code in course_dict:
                        # Add edge from course to its simultaneous course to place it after
                        graph[item.code_name].append(sim_code)
                        in_degree[sim_code] += 1

        # Detect cycles using DFS
        visited = set()
        on_stack = set()
        cycles = []

        def dfs(node, path):
            if node in on_stack:
                # Cycle detected
                cycle_start_index = path.index(node)
                cycle = path[cycle_start_index:].copy()
                if cycle not in cycles:
                    cycles.append(cycle)
                return
            if node in visited:
                return
            visited.add(node)
            on_stack.add(node)
            path.append(node)
            for neighbor in graph[node]:
                dfs(neighbor, path)
            on_stack.remove(node)
            path.pop()

        for node in course_dict:
            if node not in visited:
                dfs(node, [])

        if cycles:
            # Cycle detected
            cycles_str_list = []
            for cycle in cycles:
                cycle.append(cycle[0])  # Close the cycle for visualization
                cycle_str = ' -> '.join(cycle)
                cycles_str_list.append(cycle_str)
            cycles_str = '; '.join(cycles_str_list)
            logging.error(f"Failed to perform topological sort. Cycles detected: {cycles_str}")
            return None, cycles_str

        # Perform topological sort
        queue = deque()
        sorted_courses = []
        for course_code in course_dict:
            if in_degree[course_code] == 0:
                queue.append(course_code)

        while queue:
            current_code = queue.popleft()
            sorted_courses.append(course_dict[current_code])
            for neighbor in graph[current_code]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        return sorted_courses, None

    def generate_plan(self, items):
        self.items = items  # Store items for access in other methods
        self.course_dict = {item.code_name: item for item in items}

        # Initialize scheduled status for each course
        for item in items:
            item.scheduled = False
            item.semester = None

        unscheduled_courses = set(item.code_name for item in items)
        completed_courses = set()

        plan = []
        semester_number = 0  # We'll use this as an index for quarters

        # While there are unscheduled courses
        while unscheduled_courses:
            # Determine the current quarter
            quarter = self.quarters[semester_number % len(self.quarters)]
            current_season = quarter['name']
            max_units = quarter['limit']
            logging.debug(f"Starting semester {semester_number + 1}: {current_season}")

            semester_courses = []
            semester_units = 0
            made_progress = False

            # Find courses that can be scheduled
            available_courses = []

            for item in items:
                if not item.scheduled:
                    # Check if course is available in the current season
                    if current_season not in item.available_terms:
                        continue  # Skip this course for this semester

                    # Check if all predecessors are completed
                    predecessors_satisfied = self.check_predecessors(item, completed_courses)
                    if predecessors_satisfied:
                        available_courses.append(item)

            logging.debug(f"Available courses for semester {semester_number + 1}: {[c.code_name for c in available_courses]}")

            # Try to schedule available courses
            for course in available_courses:
                if course.scheduled:
                    continue  # Just in case

                # Check if course can be scheduled in this semester
                # Check if we can schedule its simultaneous courses
                can_schedule, total_units, courses_to_add = self.can_schedule_course(course, semester_units, completed_courses, current_season)

                if can_schedule and (semester_units + total_units) <= max_units:
                    # Schedule the course and its simultaneous courses
                    for c in courses_to_add:
                        if not c.scheduled:
                            c.scheduled = True
                            c.semester = semester_number + 1
                            semester_courses.append(c)
                            unscheduled_courses.discard(c.code_name)
                            logging.debug(f"Scheduled course {c.code_name} in semester {semester_number + 1}")
                    semester_units += total_units
                    completed_courses.update(c.code_name for c in courses_to_add)
                    made_progress = True
                else:
                    logging.debug(f"Cannot schedule course {course.code_name} in semester {semester_number + 1}")

            if not made_progress:
                # Cannot schedule any more courses in this semester
                if not semester_courses:
                    # No courses could be scheduled at all in this semester
                    # Deadlock detected
                    # Collect details about the problems
                    unschedulable_courses = []
                    for item in items:
                        if not item.scheduled:
                            reasons = []
                            # Check availability in the current season
                            if current_season not in item.available_terms:
                                reasons.append(f"Not available in season {current_season}")
                            # Check unsatisfied predecessors
                            unsatisfied_predecessors = self.get_unsatisfied_predecessors(item, completed_courses)
                            if unsatisfied_predecessors:
                                reasons.append(f"Unsatisfied prerequisites: {', '.join(unsatisfied_predecessors)}")
                            # Check unsatisfied simultaneous courses
                            unsatisfied_simultaneous = self.get_unsatisfied_simultaneous(item, completed_courses, current_season)
                            if unsatisfied_simultaneous:
                                reasons.append(f"Unsatisfied corequisites: {', '.join(unsatisfied_simultaneous)}")
                            unschedulable_courses.append((item.code_name, reasons))

                    error_messages = [f"{code}: {'; '.join(reasons)}" for code, reasons in unschedulable_courses]
                    error_details = "; ".join(error_messages)

                    logging.error(f"Cannot schedule courses due to unsatisfied dependencies or term availability. Deadlock detected. Details: {error_details}")
                    return None, error_details

            if semester_courses:
                plan.append(semester_courses)
                logging.debug(f"Semester {semester_number + 1} courses: {[c.code_name for c in semester_courses]}")
                semester_number += 1
            else:
                break

        return plan, None

    def get_unsatisfied_predecessors(self, course, completed_courses):
        predecessors = eval(course.predecessor) if course.predecessor else []
        unsatisfied = []
        for group in predecessors:
            group_satisfied = False
            for code_name in group:
                if code_name in completed_courses:
                    group_satisfied = True
                    break
            if not group_satisfied:
                unsatisfied.extend(group)
        return unsatisfied

    def get_unsatisfied_simultaneous(self, course, completed_courses, current_season):
        simultaneous_groups = eval(course.simultaneous) if course.simultaneous else []
        unsatisfied = []
        for group in simultaneous_groups:
            group_satisfied = False
            for code_name in group:
                if code_name in completed_courses:
                    group_satisfied = True
                    break
                sim_course = self.get_course_by_code(code_name)
                if sim_course and current_season in sim_course.available_terms:
                    group_satisfied = True
                    break
            if not group_satisfied:
                unsatisfied.extend(group)
        return unsatisfied

    def check_predecessors(self, course, completed_courses):
        predecessors = eval(course.predecessor) if course.predecessor else []
        for group in predecessors:
            # Need at least one course from each group to be completed
            group_satisfied = False
            for code_name in group:
                if code_name in completed_courses:
                    group_satisfied = True
                    break
            if not group_satisfied:
                return False
        return True

    def can_schedule_course(self, course, semester_units, completed_courses, current_season):
        courses_to_add = [course]
        total_units = course.units

        # Check if adding course exceeds unit limit
        if total_units > 16:
            logging.debug(f"Cannot schedule course {course.code_name}: unit limit exceeded")
            return False, None, None

        # Process simultaneous courses
        simultaneous_groups = eval(course.simultaneous) if course.simultaneous else []

        if not simultaneous_groups:
            logging.debug(f"Course {course.code_name} has no simultaneous courses")
            return True, total_units, courses_to_add

        # For each group in simultaneous_groups, get available courses
        available_options_per_group = []
        for group in simultaneous_groups:
            available_courses_in_group = []
            for code_name in group:
                # Check if the course is already completed
                if code_name in completed_courses:
                    continue  # Already completed, no need to schedule again

                # Find the course object
                sim_course = self.get_course_by_code(code_name)
                if sim_course and not sim_course.scheduled:
                    # Check if course is available in the current season
                    if current_season not in sim_course.available_terms:
                        continue  # Skip this course for this semester

                    # Check if its predecessors are satisfied
                    if self.check_predecessors(sim_course, completed_courses):
                        available_courses_in_group.append(sim_course)
            if not available_courses_in_group:
                # If all courses in the group are already completed, the requirement is satisfied
                if any(code_name in completed_courses for code_name in group):
                    logging.debug(f"Group {group} for course {course.code_name} already satisfied by completed courses.")
                    continue
                else:
                    logging.debug(f"Cannot schedule course {course.code_name}: no available simultaneous courses in group {group}")
                    return False, None, None
            else:
                available_codes = [c.code_name for c in available_courses_in_group]
                logging.debug(f"Available simultaneous courses for group {group}: {available_codes}")
                available_options_per_group.append(available_courses_in_group)

        # Generate all possible combinations of one course from each group
        combinations = list(product(*available_options_per_group)) if available_options_per_group else [()]

        # For each combination, check if total units fit
        for combo in combinations:
            combo_courses = list(combo)
            combo_units = sum(c.units for c in combo_courses)
            total_combo_units = total_units + combo_units
            if semester_units + total_combo_units <= 16:
                logging.debug(f"Scheduling course {course.code_name} with simultaneous courses {[c.code_name for c in combo_courses]}")
                courses_to_add.extend(combo_courses)
                total_units += combo_units
                return True, total_units, courses_to_add
            else:
                logging.debug(f"Combination {[c.code_name for c in combo_courses]} with course {course.code_name} exceeds unit limit")

        # No combination fits
        logging.debug(f"Cannot schedule course {course.code_name}: no valid combinations of simultaneous courses fit within unit limit")
        return False, None, None

    def get_course_by_code(self, code_name):
        return self.course_dict.get(code_name)

    def print_plan(self, plan):
        """
        Prints the plan of courses per semester in a readable format.

        Args:
            plan (list): The plan of courses per semester.
        """
        semester_labels = self.get_semester_labels(len(plan))

        for idx, semester in enumerate(plan):
            print(f"\n{semester_labels[idx]}")
            total_units = 0
            for course in semester:
                predecessors = eval(course.predecessor)
                simultaneous = eval(course.simultaneous)
                print(f"Course: {course.code_name}, Units: {course.units}, Predecessors: {predecessors}, Simultaneous: {simultaneous}, Terms: {course.terms}")
                total_units += course.units
            print(f"Total units for the semester: {total_units}")

# Function to run full test
def run_full_test():
    app = create_app()

    with app.app_context():
        plan_manager = PlanManager()
        console = Console()

        # Disable logging during run_full_test
        logging.disable(logging.CRITICAL)

        try:
            unique_group_ids = db.session.query(Item.item_group_id).distinct().all()
            unique_group_ids = [gid[0] for gid in unique_group_ids if gid[0]]

            total_groups = len(unique_group_ids)
            success_count = 0
            failure_details = []

            # Open file to save summary results
            with open('test_results.txt', 'w', encoding='utf-8') as result_file:
                file_console = Console(file=result_file)

                console.print(f"Starting tests for {total_groups} unique item_group_id...")
                file_console.print(f"Starting tests for {total_groups} unique item_group_id...")

                progress = Progress(
                    "[progress.description]{task.description}",
                    "[progress.percentage]{task.percentage:>3.0f}%",
                    transient=True,
                )
                progress.start()
                task = progress.add_task("[cyan]Testing...", total=total_groups)

                for idx, group_id in enumerate(unique_group_ids, start=1):
                    try:
                        test_data = {
                            'manufacturing_codes': [group_id],
                            'secondary_codes': [],
                            'additional_codes': [],
                            'extra_codes': []
                        }

                        class MockRequest:
                            def __init__(self, json_data):
                                self.json = json_data

                        mock_request = MockRequest(json_data=test_data)
                        response = plan_manager.create_plan(mock_request)

                        if isinstance(response, tuple):
                            response_data, status_code = response
                            if status_code == 200:
                                success_count += 1
                            else:
                                message = response_data.get_json().get('message', 'Unknown error')
                                failure_details.append((group_id, message))
                        else:
                            failure_details.append((group_id, "Unknown error"))

                    except Exception as e:
                        error_trace = traceback.format_exc()
                        failure_details.append((group_id, f"{str(e)}\n{error_trace}"))

                    progress.update(task, advance=1)

                progress.stop()

                failure_count = len(failure_details)

                # Print statistics
                console.print("\nTesting completed.")
                file_console.print("\nTesting completed.")
                table = Table(title="Testing Statistics", box=box.MINIMAL_DOUBLE_HEAD)
                table.add_column("Parameter", style="cyan")
                table.add_column("Value", style="magenta")

                table.add_row("Total groups", str(total_groups))
                table.add_row("Plans successfully generated", str(success_count))
                table.add_row("Plans failed to generate", str(failure_count))
                console.print(table)
                file_console.print(table)

                # Success vs Failure bar chart
                console.print("\n[bold green]Success[/bold green] vs [bold red]Failure[/bold red]:")
                file_console.print("\n[bold green]Success[/bold green] vs [bold red]Failure[/bold red]:")
                max_bar_length = 50  # Maximum length of the bar
                success_bar_length = int((success_count / total_groups) * max_bar_length)
                failure_bar_length = int((failure_count / total_groups) * max_bar_length)
                success_bar = '█' * success_bar_length
                failure_bar = '█' * failure_bar_length
                console.print(Panel.fit(
                    f"[green]{success_count}[/green] | {success_bar}\n"
                    f"[red]{failure_count}[/red] | {failure_bar}",
                    border_style="white"
                ))
                file_console.print(Panel.fit(
                    f"[green]{success_count}[/green] | {success_bar}\n"
                    f"[red]{failure_count}[/red] | {failure_bar}",
                    border_style="white"
                ))

                # Error details table
                if failure_count > 0:
                    error_table = Table(title="Error Details", box=box.SIMPLE_HEAVY)
                    error_table.add_column("item_group_id", style="white")
                    error_table.add_column("Error Message", style="red")

                    for group_id, message in failure_details:
                        error_table.add_row(group_id, message)

                    console.print(error_table)
                    file_console.print(error_table)

        finally:
            # Re-enable logging
            logging.disable(logging.NOTSET)

if __name__ == '__main__':
    run_full_test()
