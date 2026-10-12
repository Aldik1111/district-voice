"""Optional integration check: real local E5, A-H controls, with networking forbidden."""
from pathlib import Path
import argparse
import json
import os
import socket
import sys
import time

REPO = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(REPO / 'backend'), str(REPO / 'backend/tests')]
from test_analysis_controls import write_report
from app.ai import engine

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--report',type=Path,required=True)
arguments=parser.parse_args()
attempts = []
def deny_network(*args, **kwargs):
    attempts.append('network_attempt')
    raise AssertionError('Model inference must stay offline')

socket.socket.connect = deny_network
socket.create_connection = deny_network
socket.getaddrinfo = deny_network
start = time.monotonic()
model = engine._load_model()
report = write_report(arguments.report, mode='auto')
assert all(row['algorithm']['semantic'] for row in report['controls']), 'Real E5 was not used'
assert not attempts, 'Network attempted during inference'
report['real_model_verified'] = True
report['network_attempts'] = len(attempts)
report['elapsed_seconds'] = round(time.monotonic() - start, 2)
arguments.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps({key: report[key] for key in ['passed','total','real_model_verified','network_attempts','elapsed_seconds']}, ensure_ascii=False))
for control in report['controls']:
    print(control['id'], 'PASS' if control['passed'] else 'FAIL', control['failures'])
raise SystemExit(0 if report['passed']==report['total'] else 1)
