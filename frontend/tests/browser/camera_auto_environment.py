"""Create an isolated SQLite backup of the marked synthetic camera demo.

No schema/data reset and no copying of a live SQLite file outside its backup API.
The credential sidecar stays in ignored artifacts and is never printed.
"""
import argparse
import json
from pathlib import Path
import sqlite3
from uuid import uuid4

ROOT=Path(__file__).resolve().parents[3]
parser=argparse.ArgumentParser()
parser.add_argument("--credentials",required=True,type=Path)
args=parser.parse_args()
credentials=json.loads(args.credentials.read_text(encoding="utf-8"))
source=Path(credentials["database"]).resolve()
marker=json.loads(Path(str(source)+".demo.json").read_text(encoding="utf-8"))
if credentials.get("profile")!="single-lot-academic-v1" or marker.get("synthetic_history") is not True:
    raise ValueError("Source must be the marked synthetic academic database")
directory=ROOT/"backend/artifacts/camera-auto-uat/environments"/uuid4().hex[:10]
directory.mkdir(parents=True)
database=directory/"camera-auto-clone.db"
with sqlite3.connect(source.as_uri()+"?mode=ro",uri=True) as src,sqlite3.connect(database) as dst:
    src.backup(dst)
    snapshot={"policies":src.execute("SELECT * FROM vision_automation_policies ORDER BY camera_id").fetchall(),
              "sessions":src.execute("SELECT COUNT(*) FROM parking_sessions").fetchone()[0],
              "observations":src.execute("SELECT COUNT(*) FROM vision_observations").fetchone()[0],
              "passages":src.execute("SELECT COUNT(*) FROM vision_passage_events").fetchone()[0]}
marker.update(camera_auto_uat_clone=True,source_database=str(source))
Path(str(database)+".demo.json").write_text(json.dumps(marker,ensure_ascii=False,indent=2),encoding="utf-8")
credentials["database"]=str(database)
sidecar=Path(str(database)+".demo-credentials.json")
sidecar.write_text(json.dumps(credentials,ensure_ascii=False,indent=2),encoding="utf-8")
(directory/"source-before.json").write_text(json.dumps(snapshot,ensure_ascii=False,indent=2),encoding="utf-8")
(directory/"environment.json").write_text(json.dumps({"database":str(database),"credentials":str(sidecar),"source_database":str(source),"source_before":"source-before.json"},ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"directory":str(directory),"database":str(database),"credentials_file":str(sidecar)},ensure_ascii=True))
