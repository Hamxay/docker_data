from manage import app
from line_profiler import profile

@profile
def create_plan_profile():
    with app.test_client() as client:
        data = {
            "manufacturing_codes": ["C4"],
            "secondary_codes": [],
            "additional_codes": [],
            "extra_codes": []
        }
        client.post('/create-plan', json=data)

if __name__ == "__main__":
    create_plan_profile()