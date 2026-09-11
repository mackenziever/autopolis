import sys
from telemetry.logger import replay_digest
a,b=sys.argv[1:3];da,db=replay_digest(a),replay_digest(b)
print("A",da);print("B",db);print("DETERMINISTIC" if da==db else "MISMATCH")
raise SystemExit(0 if da==db else 1)
