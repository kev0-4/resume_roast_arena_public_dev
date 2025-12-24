'''
used for logging into open telemetry, currently will write to a json dumb 
TOdo: connect to azure analytics later in phase 6
'''
from typing import Optional
import json
from datetime import datetime
from uuid import UUID
import os


def emit_event(event_name: str, payload: dict):
    timestamp = datetime.now().isoformat()

    firebase_uid = str(payload.get("firebase_uid", " "))

    
    log_entry = {
        "timestamp": timestamp,
        "event_name":event_name,
        "level" : payload.get("status", "UNKNOWN"),
        "route": payload.get("route", "/"),
        "trace_id":  payload.get("trace_id", 00),
        "firebase_uid": firebase_uid
    }
    serializable_payload = {k: str(v) if isinstance(v, UUID) else v 
                           for k, v in payload.items()}
    log_entry.update(serializable_payload)
    filename = 'log_entry.json'

    try:
        # Read existing data
        if os.path.exists(filename):
            with open(filename, 'r') as f:
                try:
                    data = json.load(f)
                    if not isinstance(data, list):
                        data = [data]  # Convert single object to list
                except json.JSONDecodeError:
                    data = []  # Start fresh if file is corrupted
        else:
            data = []
        
        # Append new entry
        data.append(log_entry)
        
        # Write back to file
        with open(filename, 'w') as f:
            json.dump(data, f, indent=4)
        
        print(f"Successfully appended entry to {filename}")
    except IOError as e:
        print(f"Error writing to file: {e}")


def with_trace(event_name:str, payload:dict, trace_id: Optional[str]):
    return None


    ''' this functio infers log severity level - INFO, WARNING, ERROR'''
