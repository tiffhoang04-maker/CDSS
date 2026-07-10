# for purposes of testing server.py
from server import (
    get_current_patient_state,
    get_valid_options,
    submit_choice,
    get_kg_context_for_patient
)

print("\n=== CURRENT PATIENT STATE ===")
print(get_current_patient_state())

print("\n=== VALID OPTIONS ===")
valid_options = get_valid_options()
print(valid_options)

print("\n=== KG CONTEXT ===")
print(get_kg_context_for_patient(limit=10))

print("\n=== TEST INVALID ACTION ===")
print(submit_choice("action", "fake_action_id"))

if valid_options["valid_actions"]:
    first_action_id = valid_options["valid_actions"][0]["option_id"]

    print("\n=== TEST VALID ACTION ===")
    print("Submitting:", first_action_id)
    print(submit_choice("action", first_action_id))
else:
    print("\nNo valid actions returned from Neo4j.")