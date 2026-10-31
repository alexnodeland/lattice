"""Resolve envoy.yaml's anchors and merge keys, drop its x- keys, write envoy.json."""

import json
import pathlib

import yaml

here = pathlib.Path(__file__).parent
config = yaml.safe_load((here / "envoy.yaml").read_text())
config = {k: v for k, v in config.items() if not k.startswith("x-")}
(here / "envoy.json").write_text(json.dumps(config, indent=1) + "\n")
