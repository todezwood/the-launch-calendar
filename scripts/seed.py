"""Load the seed calendar into a store.  python -m scripts.seed [json|notion]"""
import json
import sys
from pathlib import Path

from adapters.cli import load_env, open_store
from agent.schema import Launch

SEED = Path(__file__).parent.parent / "tests" / "fixtures" / "seed.json"


def main(backend: str = "json") -> None:
    load_env()
    store = open_store(backend)
    if store.list():
        sys.exit("Store is not empty — refusing to seed twice.")
    launches = [Launch.from_dict(d) for d in json.loads(SEED.read_text())["launches"]]
    ids = {}
    for launch in launches:            # ids are store-assigned, so remap dependencies
        old, deps = launch.id, launch.depends_on
        launch.depends_on = []
        ids[old] = store.save(launch).id
        launch.depends_on = deps
    for launch in launches:
        if launch.depends_on:
            launch.depends_on = [ids[d] for d in launch.depends_on]
            store.update(launch, {"depends_on"})
    print(f"Seeded {len(launches)} launches into the {backend} store.")


if __name__ == "__main__":
    main(*sys.argv[1:2])
