#!/usr/bin/env python3
"""Query by default; flight requires explicit command-line options."""
import time
import argparse
from easyfly_pybind import Client

parser = argparse.ArgumentParser(description='Default: query only. Flight requires explicit options.')
flight = parser.add_mutually_exclusive_group()
flight.add_argument('--navigate', nargs=3, type=float, metavar=('X', 'Y', 'Z'))
flight.add_argument('--mission', metavar='YAML_PATH')
parser.add_argument('--sim-time', action='store_true')
args = parser.parse_args()

with Client(use_sim_time=args.sim_time) as client:
    time.sleep(0.2)
    print(client.state())
    print('navigate server:', client.server_ready('navigate'))
    operation = None
    if args.navigate:
        operation = client.navigate(*args.navigate)
    elif args.mission:
        operation = client.execute_mission(args.mission)
    if operation:
        end = time.monotonic() + 30
        while not operation.wait(.2) and time.monotonic() < end:
            snapshot = operation.snapshot()
            print(snapshot.admission, snapshot.feedback)
        if operation.snapshot().remote_execution_pending:
            operation.cancel()  # Explicit example policy, not wait's behavior.
            operation.wait(5)
        snapshot = operation.snapshot()
        print(snapshot.status, snapshot.success, snapshot.message,
              'remote_pending=', snapshot.remote_execution_pending)
    if not client.close(2):
        print('WARNING: unresolved peer execution; process exit cannot guarantee stop')
