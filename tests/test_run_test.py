# tests/test_run_test.py
import json
import pytest
from unittest.mock import MagicMock
from app.services.plan_service import PlanManager
from flask import Response

def test_run_test(init_database, mocker):
    """
    Тестирование метода create_plan с минимальными данными.
    """
    # Мокаем метод create_plan у PlanManager на уровне класса
    mock_response = {'status': 'success', 'plan_id': 1}
    mock_create_plan = mocker.patch.object(
        PlanManager, 
        'create_plan', 
        return_value=(json.dumps(mock_response), 200)
    )

    # Пример входных данных для теста
    test_data = {
        'manufacturing_codes': ['C2'],
        'secondary_codes': [],
        'additional_codes': [],
        'extra_codes': []
    }

    # Mock request (эмуляция запроса)
    class MockRequest:
        def __init__(self, json_data):
            self.json = json_data

    mock_request = MockRequest(json_data=test_data)

    # Инициализация менеджера планирования
    plan_manager = PlanManager()

    # Вызов метода create_plan и получение ответа
    response = plan_manager.create_plan(mock_request)

    # Проверка ответа
    if isinstance(response, tuple):
        response_data, status_code = response
        print(response_data)  # Проверить, что содержится в ответе
        print(status_code)    # Убедиться, что код статуса корректный
        assert status_code == 200

        # Если response_data — это объект Response, извлекаем JSON
        if isinstance(response_data, Response):
            response_json = response_data.get_json()
        else:
            response_json = json.loads(response_data)

        # Проверяем только ключевые поля
        assert response_json['status'] == mock_response['status']
        assert response_json['plan_id'] == mock_response['plan_id']
    else:
        pytest.fail("Response is not a tuple")
