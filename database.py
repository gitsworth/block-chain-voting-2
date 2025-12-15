import json
import os

VOTERS_FILE = 'voters.json'
CANDIDATES_FILE = 'candidates.json'

def load_data(file_path):
    if os.path.exists(file_path):
        try:
            with open(file_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []

def save_data(data, file_path):
    with open(file_path, 'w') as f:
        json.dump(data, f, indent=4)

def load_voters():
    return load_data(VOTERS_FILE)

def save_voters(voters_list):
    save_data(voters_list, VOTERS_FILE)

def load_candidates():
    return load_data(CANDIDATES_FILE)

def save_candidates(candidates_list):
    save_data(candidates_list, CANDIDATES_FILE)
