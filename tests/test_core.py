import asyncio, os, tempfile
from config import SimConfig
from engine.tick_engine import CivitasEngine
from telemetry.logger import iter_records, replay_digest
from world.map import CityMap
from engine.spatial import SpatialService

def run(path,seed=42,ticks=80):
    cfg=SimConfig(num_agents=20,total_ticks=ticks,seed=seed,log_path=path,llm_record_path=path+".jsonl")
    asyncio.run(CivitasEngine(cfg).run(realtime=False))

def test_astar_reaches_goal():
    m=CityMap(64,64,42,.08);s=SpatialService(m)
    p=s.astar((6,6),(54,10));assert p[0]==(6,6) and p[-1]==(54,10)
    assert all(m.walkable(x) for x in p)

def test_replay_is_byte_deterministic(tmp_path):
    a=str(tmp_path/"a.msgpack");b=str(tmp_path/"b.msgpack")
    run(a);run(b);assert replay_digest(a)==replay_digest(b)

def test_snapshot_count(tmp_path):
    p=str(tmp_path/"x.msgpack");run(p,ticks=25)
    n=sum(e["type"]=="snapshot" for r in iter_records(p) if r.get("record")=="tick" for e in r["events"])
    assert n==20*25

def test_seed_changes_replay(tmp_path):
    a=str(tmp_path/"a.msgpack");b=str(tmp_path/"b.msgpack")
    run(a,1);run(b,2);assert replay_digest(a)!=replay_digest(b)
