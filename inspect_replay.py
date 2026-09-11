from __future__ import annotations
import argparse, collections, json
from telemetry.logger import iter_records, replay_digest
p=argparse.ArgumentParser();p.add_argument("path",nargs="?",default="data/simulation_replay.msgpack")
a=p.parse_args();records=iter_records(a.path);header=next(records);counts=collections.Counter();last={};ticks=0
for r in records:
    if r.get("record")!="tick":continue
    ticks+=1
    for e in r["events"]:
        counts[e["type"]]+=1
        if e["type"]=="snapshot":last[e["agent_id"]]=e
print(json.dumps({"header":header,"ticks":ticks,"event_counts":counts,"agents":len(last),
                  "sha256":replay_digest(a.path)},ensure_ascii=False,indent=2,default=dict))
print("\nPrimi 5 agenti finali:")
for aid in sorted(last)[:5]:print(aid,last[aid])
