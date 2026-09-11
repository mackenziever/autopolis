# Meshy / citizen assets for Civitas

## Live viewer policy (anti-blob)

The live city at `/live` uses **procedural citizens only** by default.

- `loadCitizenGlb` is **fail-closed** (empty pools unless you pass explicit URLs)
- `createCitizen(..., { allowGlb: false })` ignores any pool until opted in
- Blocked forever unless renamed + allowlisted: `woman.glb`, `xbot.glb`, `cesium_man.glb`
  (these caused the giant green emissive/bloom "monster")
- `citizens/meshy/*` bypasses the filename blocklist (`isBlockedCitizenGlb`) —
  it's the vetted drop-in location, not a loophole for the old bad files.

## `citizens/meshy/xbot.glb` + `soldier.glb` — tried 2026-09-11, reverted

Materials confirmed clean (`emissiveFactor === [0,0,0]`, no lime/full-white),
so the original bloom-monster bug is NOT present in these two files. Wired
them in and found a **different** problem, live in the browser:

- `normalizeCitizenRoot()` scales by `max(size.x, size.y, size.z)`. Both GLBs
  load in Mixamo bind **T-pose** (arms straight out), so the arm-to-arm width
  exceeds standing height — the height-targeted scale came out wrong, leaving
  every citizen ~35-65cm tall instead of ~100-105cm.
- `animateCitizen()` returns immediately for `fromGlb` meshes — there is no
  `AnimationMixer` wired anywhere in `city_kit.js`/`living_city_live.html`, so
  a GLB citizen would stand frozen in that T-pose while "walking" the city.

Reverted to `allowGlb: false` (see `ensureAgent()` in `living_city_live.html`)
rather than ship visibly-broken proportions. To actually turn these on:

1. Fix `normalizeCitizenRoot()` to scale off a fixed reference bone (e.g. hips
   to head-top) or a rest-pose bounding box, not the raw T-pose AABB.
2. Add a minimal `THREE.AnimationMixer` per GLB citizen (idle/walk clip picked
   by `moving`), driven from `animateCitizen(group, dt, moving)` instead of
   the current early-return.
3. Re-test scale AND the pose before flipping `allowGlb: true` again.

## Adding more vetted characters

1. Drop the GLB under `citizens/meshy/` (Y-up, no full-white/lime emissive —
   check with `gltf.materials[].emissiveFactor`/`baseColorFactor`).
2. Wire the URL into the `loadCitizenGlb(...)` call in `living_city_live.html`'s
   `bootstrap()`, fix the scale/animation gaps above, **then** flip `allowGlb: true`.
3. Hard-refresh `/live` (viewer is bind-mounted — no `docker cp`/rebuild needed).

```powershell
# viewer is bind-mounted — edits apply without docker cp
# If not mounted yet:
docker compose up -d living
```

Optional folders: `buildings/`, `props/` — not auto-loaded by live viewer.
