"""Read-only workflow evidence checks. This is not a replacement for product tests."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tomllib
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def evaluate(artifacts):
    results = []
    def record(name, expected, observed, passed):
        results.append({'Eval': name, 'Expected': expected, 'Observed': observed,
                        'Result': 'PASS' if passed else 'FAIL', 'Regression': 'UNKNOWN'})
    tracked = subprocess.check_output(['git', 'ls-files'], cwd=ROOT, text=True).splitlines()
    unwanted = [name for name in tracked if name.startswith(('HoSo_BaoCao_ParkingAI/', 'backend/artifacts/'))
                or name.endswith(('.onnx', '.pt', '.dump', '.env.production-test.local'))]
    record('private-artifacts', 'No private dossier/model/backup/credentials tracked',
           {'tracked_count': len(tracked), 'excluded_tracked_count': len(unwanted)}, not unwanted)
    fly = tomllib.loads((ROOT/'backend/fly.toml').read_text(encoding='utf-8'))
    record('resource-and-provider-scope', '1 CPU/1 GB, demo payments enabled, Gemini disabled in release config',
           {'vm': fly['vm'], 'AI_ENABLED': fly['env']['AI_ENABLED'], 'DEMO_PAYMENTS_ENABLED': fly['env']['DEMO_PAYMENTS_ENABLED']},
           fly['vm'][0]['cpus'] == 1 and fly['vm'][0]['memory_mb'] == 1024
           and fly['env']['AI_ENABLED'] == 'false' and fly['env']['DEMO_PAYMENTS_ENABLED'] == 'true')
    dump = artifacts/'private/parkingai-public-before-round3.dump'
    restore = artifacts/'restore-evidence.json'
    if dump.exists() and restore.exists():
        evidence = json.loads(restore.read_text(encoding='utf-8'))
        digest = hashlib.sha256(dump.read_bytes()).hexdigest()
        record('restore', 'Original public-schema checksum and isolated PG17 table counts match',
               {'sha256': digest, 'restore': evidence}, digest == '924e4ffca951b52d1c4d1f494635c1d2427234660d613dfcbf3cbc8241f1f747'
               and evidence['restore_passed'] and evidence['table_counts_equal'] and evidence['tables'] == 36)
    else:
        results.append({'Eval':'restore','Result':'BLOCKED','Observed':'Local private evidence unavailable','Regression':'UNKNOWN'})
    for name in ('sqlite-verified.xml', 'postgres-release.xml'):
        file = artifacts/name
        if not file.exists():
            results.append({'Eval':name,'Result':'BLOCKED','Observed':'Fresh result not yet available','Regression':'UNKNOWN'})
            continue
        tree = ET.parse(file)
        cases = list(tree.iter('testcase'))
        failed = sum(item.find('failure') is not None or item.find('error') is not None for item in cases)
        skipped = sum(item.find('skipped') is not None for item in cases)
        record(name, 'No failed/error tests; skipped counted separately',
               {'total':len(cases),'passed':len(cases)-failed-skipped,'failed':failed,'skipped':skipped}, bool(cases) and failed == 0)
    return results


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifacts', type=Path, default=ROOT/'backend/artifacts/round3')
    args = parser.parse_args()
    results = evaluate(args.artifacts)
    print(json.dumps(results, ensure_ascii=False, indent=2))
    raise SystemExit(any(row['Result'] != 'PASS' for row in results))
