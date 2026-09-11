.PHONY: install run fast test inspect clean
install:
	python -m pip install -r requirements.txt
run:
	python main.py --agents 50 --ticks 600 --hz 15
fast:
	python benchmark.py --agents 50 --ticks 5000
inspect:
	python inspect_replay.py data/simulation_replay.msgpack
test:
	pytest -q
clean:
	rm -f data/*.msgpack data/*.jsonl data/*.parquet
