import json
import pytest
from collections import defaultdict
from app.services.plan_service import PlanManager
from app.models import Item
from flask import Response
from app import db
from rich.console import Console
from rich.progress import Progress
from rich.table import Table
from rich.panel import Panel
from rich import box


@pytest.fixture(scope='module')
def console():
    """Fixture for Console from rich."""
    return Console()


def test_run_full_test(init_database):
    """
    Интеграционный тест для PlanManager для всех уникальных item_group_ids.
    """
    console = Console()

    # Получение уникальных group_ids из базы данных
    unique_group_ids = db.session.query(Item.item_group_id).distinct().all()
    unique_group_ids = [gid[0] for gid in unique_group_ids if gid[0]]

    total_groups = len(unique_group_ids)
    success_count = 0
    failure_details = []

    console.print(f"Запуск тестов для [bold]{total_groups}[/bold] уникальных item_group_ids...")

    # Создание прогресс-бара
    with Progress() as progress:
        task = progress.add_task("[cyan]Тестирование...", total=total_groups)

        for group_id in unique_group_ids:
            try:
                test_data = {
                    'manufacturing_codes': [group_id],
                    'secondary_codes': [],
                    'additional_codes': [],
                    'extra_codes': []
                }

                # Мок для request
                class MockRequest:
                    def __init__(self, json_data):
                        self.json = json_data

                mock_request = MockRequest(json_data=test_data)
                response = PlanManager().create_plan(mock_request)

                # Обработка ответа
                if isinstance(response, Response):
                    response_json = response.get_json()
                elif isinstance(response, tuple):
                    response_json, status_code = response
                    if isinstance(response_json, Response):
                        response_json = response_json.get_json()
                    elif isinstance(response_json, str):
                        response_json = json.loads(response_json)
                else:
                    raise ValueError("Неверный формат ответа")

                # Проверка структуры ответа
                if "quarters" in response_json and "reqs" in response_json:
                    success_count += 1
                else:
                    failure_details.append((group_id, "Неполный ответ от сервера"))

            except json.JSONDecodeError as e:
                failure_details.append((group_id, f"Ошибка декодирования JSON: {str(e)}"))
            except Exception as e:
                failure_details.append((group_id, f"Неожиданная ошибка: {str(e)}"))

            # Обновляем прогресс
            progress.update(task, advance=1)

    failure_count = len(failure_details)

    # Печать итогов
    console.print("\n[bold green]Тестирование завершено[/bold green].")
    console.print(f"Успешных: {success_count}, Неудачных: {failure_count}")

    # Формирование таблицы с результатами
    table = Table(title="Результаты тестов")
    table.add_column("Group ID", justify="left")
    table.add_column("Статус", justify="left")
    table.add_column("Описание", justify="left")

    for group_id in unique_group_ids:
        if group_id in [failure[0] for failure in failure_details]:
            # Ищем описание ошибки
            error_detail = next(
                (detail for gid, detail in failure_details if gid == group_id), "Неизвестная ошибка"
            )
            table.add_row(group_id, "[red]Неудача[/red]", error_detail)
        else:
            table.add_row(group_id, "[green]Успех[/green]", "-")

    console.print(table)

    # Убедиться, что хотя бы один тест прошел
    assert success_count > 0, f"Ни один из {total_groups} тестов не прошел успешно"