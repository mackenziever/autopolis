"""Tests for city self-construction (progress → POI unlock)."""
from __future__ import annotations

from world.city_growth import (
    CityGrowthEngine,
    parse_blueprints_from_text,
    validate_blueprint,
)
from world.map import CityMap


def test_validate_and_parse_external_blueprint_json():
    text = """
Vision: una città che cresce.

```json
{
  "blueprints": [
    {
      "id": "market_hall",
      "poi": "MarketHall",
      "xy": [25, 25],
      "kind": "infra",
      "requires": {"money_total": 50},
      "description": "Mercato coperto"
    }
  ]
}
```
"""
    items = parse_blueprints_from_text(text)
    assert len(items) == 1
    ok, reason = validate_blueprint(items[0])
    assert ok, reason


def test_city_growth_builds_when_metrics_met():
    city = CityMap(64, 64, seed=1, obstacle_density=0.08)
    growth = CityGrowthEngine.load(seed=1, extra_dir=None, enabled=True)
    # Force library requirements
    growth.metrics.skills_unlocked = 10
    growth.metrics.lessons = 10
    assert "Library" not in city.pois
    events = growth.try_build(tick=100, city_map=city)
    assert len(events) == 1
    assert events[0]["type"] == "city_build"
    assert events[0]["poi"] == "Library"
    assert "Library" in city.pois
    # Second call builds next eligible or none same tick catalog order
    growth.metrics.jobs_above_intern = 5
    growth.metrics.money_total = 100
    events2 = growth.try_build(tick=101, city_map=city)
    assert events2 and events2[0]["poi"] == "Workshop"


def test_map_register_poi_clears_area():
    city = CityMap(64, 64, seed=2, obstacle_density=0.5)
    city.register_poi("LabX", (20, 20))
    assert city.pois["LabX"] == (20, 20)
    assert city.walkable((20, 20))


def test_blueprint_without_xy_does_not_overlap_existing_poi():
    """Bugfix (2026-09-11, "edifici sovrapposti"): un blueprint senza `xy`
    esplicito ricadeva sempre sul default [32,32] — se un altro POI occupava
    gia' quella zona (o un secondo blueprint senza xy veniva costruito dopo),
    i due edifici finivano sovrapposti. Ora cerca il primo slot libero."""
    city = CityMap(64, 64, seed=5, obstacle_density=0.0)
    city.register_poi("Existing", (32, 32))
    growth = CityGrowthEngine.load(seed=5, extra_dir=None, enabled=True)
    growth.blueprints.append(
        {"id": "no_xy_test", "poi": "NoXyPoi", "requires": {}, "unlocks": {}, "description": ""}
    )
    events = growth.try_build(tick=1, city_map=city)
    built = next(e for e in events if e["poi"] == "NoXyPoi")
    bx, by = built["xy"]
    assert max(abs(bx - 32), abs(by - 32)) >= 7
