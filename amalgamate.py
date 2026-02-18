#!/usr/bin/env -S uv run --script
# /// script
# dependencies = [
#     "tomlkit",
# ]
# ///

import argparse
import shlex
import subprocess
import textwrap
from pathlib import Path

import tomlkit


def r(*cmd: str | Path) -> None:
    print("\x1b[7m $ \x1b[m " + " ".join(shlex.quote(str(x)) for x in cmd))  # ]]
    subprocess.run(cmd, check=True)


args = argparse.ArgumentParser()
args.add_argument("QDRANT_SRC", type=Path, help="Path to qdrant source code")
args = args.parse_args()

QDRANT_SRC = args.QDRANT_SRC
AMALGAMATION = Path(__file__).parent / "qdrant-edge-amalgamation"

r("rm", "-rf", AMALGAMATION)
(AMALGAMATION).mkdir()
(AMALGAMATION / "src").mkdir()
r("cp", "-r", QDRANT_SRC / "lib/common/common/src", AMALGAMATION / "src/common")
r("cp", "-r", QDRANT_SRC / "lib/posting_list/src", AMALGAMATION / "src/posting_list")
r("cp", "-r", QDRANT_SRC / "lib/gridstore/src", AMALGAMATION / "src/gridstore")
r("cp", "-r", QDRANT_SRC / "lib/sparse/src", AMALGAMATION / "src/sparse")
r("cp", "-r", QDRANT_SRC / "lib/segment/src", AMALGAMATION / "src/segment")
r("cp", "-r", QDRANT_SRC / "lib/quantization/src", AMALGAMATION / "src/quantization")
r("cp", "-r", QDRANT_SRC / "lib/api/src", AMALGAMATION / "src/api")
r("cp", "-r", QDRANT_SRC / "lib/shard/src", AMALGAMATION / "src/shard")
r("cp", "-r", QDRANT_SRC / "lib/edge/src", AMALGAMATION / "src/edge")

(AMALGAMATION / "cpp").mkdir()
r(
    "cp",
    QDRANT_SRC / "lib/quantization/build.rs",
    AMALGAMATION / "build-quantization.rs",
)
r("cp", "-r", QDRANT_SRC / "lib/quantization/cpp", AMALGAMATION / "cpp/quantization")

r("cp", "-r", QDRANT_SRC / "lib/segment/tokenizer", AMALGAMATION / "tokenizer")


class DepsGatherer:
    def __init__(self) -> None:
        self.root_manifest = tomlkit.loads(Path(QDRANT_SRC / "Cargo.toml").read_text())

        self.workspace_deps = {}
        for k, v in self.root_manifest["workspace"]["dependencies"].items():
            if isinstance(v, str):
                v = {"version": v}
            self.workspace_deps[k] = v

        self.dependencies = {}
        self.build_dependencies = {}

    @staticmethod
    def merge(a: dict, b: dict) -> dict:
        # TODO: merge properly, e.g. use latest version, merge features, etc.
        return {**a, **b}

    def add_crate(self, path: Path) -> None:
        crate = tomlkit.loads(path.read_text())

        # TODO: dedup code
        # TODO: dev-dependencies

        for k, v in crate["dependencies"].items():
            if isinstance(v, str):
                v = {"version": v}

            if "path" in v:
                continue
            elif v.get("workspace") is True:
                del v["workspace"]
                vv = self.workspace_deps[k]

                self.dependencies[k] = self.merge(
                    self.merge(self.dependencies.get(k, {}), vv), v
                )
            else:
                self.dependencies[k] = self.merge(self.dependencies.get(k, {}), v)

        for k, v in crate.get("build-dependencies", {}).items():
            if isinstance(v, str):
                v = {"version": v}

            if "path" in v:
                continue
            elif v.get("workspace") is True:
                del v["workspace"]
                vv = self.workspace_deps[k]

                self.build_dependencies[k] = self.merge(
                    self.merge(self.build_dependencies.get(k, {}), vv), v
                )
            else:
                self.build_dependencies[k] = self.merge(
                    self.build_dependencies.get(k, {}), v
                )


g = DepsGatherer()
g.add_crate(QDRANT_SRC / "lib/common/common/Cargo.toml")
g.add_crate(QDRANT_SRC / "lib/posting_list/Cargo.toml")
g.add_crate(QDRANT_SRC / "lib/gridstore/Cargo.toml")
g.add_crate(QDRANT_SRC / "lib/sparse/Cargo.toml")
g.add_crate(QDRANT_SRC / "lib/segment/Cargo.toml")
g.add_crate(QDRANT_SRC / "lib/quantization/Cargo.toml")
g.add_crate(QDRANT_SRC / "lib/api/Cargo.toml")
g.add_crate(QDRANT_SRC / "lib/shard/Cargo.toml")
g.add_crate(QDRANT_SRC / "lib/edge/Cargo.toml")

t = tomlkit.dumps(
    {
        "package": {
            "name": "qdrant-edge",
            "version": "0.0.0",
            "authors": ["Qdrant Team <info@qdrant.tech>"],
            "license": "Apache-2.0",
            "edition": "2024",
            "publish": False,
        },
        "dependencies": {
            **g.dependencies,
            **{
                # XXX: we can't put proc-macro crates into amalgamation
                "macros": {"path": str(Path.cwd() / QDRANT_SRC / "lib/macros")},
                # FIXME: these are linux-only deps
                "thread-priority": "3.0.0",
                "cgroups-rs": "0.3",
                "procfs": {"version": "0.18", "default-features": False},
                "io-uring": "0.7.11",
            },
        },
        "build-dependencies": g.build_dependencies,
    }
)
(AMALGAMATION / "Cargo.toml").write_text(t)


(AMALGAMATION / "src/lib.rs").write_text(
    textwrap.dedent(
        """
        #![allow(unexpected_cfgs)]
        #![allow(unused_imports)]

        #[path = "common/lib.rs"]       pub mod common;
        #[path = "posting_list/lib.rs"] pub mod posting_list;
        #[path = "gridstore/lib.rs"]    pub mod gridstore;
        #[path = "sparse/lib.rs"]       pub mod sparse;
        #[path = "segment/lib.rs"]      pub mod segment;
        #[path = "quantization/lib.rs"] pub mod quantization;
        #[path = "api/lib.rs"]          pub mod api;
        #[path = "shard/lib.rs"]        pub mod shard;
        #[path = "edge/lib.rs"]         mod edge;

        pub use edge::*;
        """
    )
)

(AMALGAMATION / "build.rs").write_text(
    textwrap.dedent(
        """
        include!("build-quantization.rs");
        // TODO: segment/build.rs - for arm neon .c files
        """
    )
)

r(Path(__file__).parent / "fixup.sh", AMALGAMATION)
