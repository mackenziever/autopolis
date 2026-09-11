import argparse, asyncio, json
from config import SimConfig
from engine.tick_engine import CivitasEngine
p=argparse.ArgumentParser();p.add_argument("--agents",type=int,default=50);p.add_argument("--ticks",type=int,default=5000)
a=p.parse_args();cfg=SimConfig(num_agents=a.agents,total_ticks=a.ticks,log_path="data/benchmark.msgpack")
r=asyncio.run(CivitasEngine(cfg).run(realtime=False));print(json.dumps(r,indent=2))
