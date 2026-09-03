import importlib
import json
import os
import requests

# Must match the token the server checks in api/server.py's require_auth
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "test-token")
HEADERS = {"Authorization": f"Bearer {AUTH_TOKEN}"}

def run():
    print("Running tests...")
    for module_name, test_name in [
        ('tests.test_adapter', 'test_validate_input_and_execute'),
        ('tests.test_catala_adapter', 'test_validate_input_and_execute'),
        ('tests.test_catala_adapter', 'test_execute_matches_python_example'),
        ('tests.test_catala_adapter', 'test_missing_input_field_reports_failure_not_crash'),
    ]:
        mod = importlib.import_module(module_name)
        try:
            getattr(mod, test_name)()
            print(f"OK: {module_name}.{test_name} passed")
        except AssertionError as e:
            print(f"FAIL: {module_name}.{test_name}: AssertionError:", e)
        except Exception as e:
            print(f"ERROR: {module_name}.{test_name}:", type(e).__name__, e)

def run_register_a_test_manifest(manifest_path:str):
    with open(manifest_path, 'r') as file:
        data = json.load(file)
    response = requests.post('http://127.0.0.1:8000/catalog/register', json=data, headers=HEADERS)
    print(response.json())


def list_manifests():
    response = requests.get('http://127.0.0.1:8000/catalog', headers=HEADERS)
    print(response.json())
    return response.json()

def health_check():
    response = requests.get('http://127.0.0.1:8000/health', headers=HEADERS)
    print(response.json())
    return response.json()

def execute_pass_culture(manifest):
    test_data = {
        "date_naissance": "2026-01-01",
        "departement": "1",
    }
    response = requests.post(f'http://127.0.0.1:8000/execute/{manifest}', json=test_data, headers=HEADERS)
    print(response.status_code)
    print(response.json())

def execute_example(manifest):
    test_data = {
        "agent_revenu": 1200,
        "agent_enfants": 1,
    }
    response = requests.post(f'http://127.0.0.1:8000/execute/{manifest}', json=test_data, headers=HEADERS)
    print(response.status_code)
    print(response.json())

if __name__ == '__main__':
    health_check()
    run_register_a_test_manifest('examples/python/manifest.json')
    run_register_a_test_manifest('examples/pass-culture-package/manifest.json')
    manifests = list_manifests()
    # execute_example(manifests[0])
    execute_example(manifests[1])

