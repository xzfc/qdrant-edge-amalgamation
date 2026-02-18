#!/bin/sh

set -e

[ "$1" ] || { echo "Usage: $0 path"; exit 1; }

AMALGAMATION=$1

sed -i '
    s/custom(function = "crate::\(.*\)")/custom(function = "crate::api::\1")/
    s/custom(function = "\(common::.*\)")/custom(function = "crate::\1")/
' "$AMALGAMATION"/src/api/grpc/qdrant.rs

sed -i '
    s:"cpp/:"cpp/quantization/:;
' "$AMALGAMATION"/build-quantization.rs

sed -i '
    /^pub mod dynamic_channel_pool;$/d
    /^pub mod dynamic_pool;$/d
    /^pub mod transport_channel_pool;$/d
    /^pub const QDRANT_DESCRIPTOR_SET:/d
' "$AMALGAMATION"/src/api/grpc/mod.rs

fix_rust_paths() {
	local PACKAGE=$1 DEPS="$2"
	ast-grep scan --inline-rules '
id: self-crate
language: rust
rule:
  kind: crate
  not:
    inside:
      kind: visibility_modifier
fix: crate::'"$PACKAGE"'

---
id: self-crate-in-macro-rules
language: rust
rule:
  all:
    - kind: metavariable
    - regex: '\''^\$crate$'\''
    - inside: { kind: macro_definition, stopBy: end }
fix: $crate::'"$PACKAGE"'

---
id: inner-deps
language: rust
rule:
  all:
    - kind: identifier
    - pattern: $MOD
    - regex: "^('"$DEPS"')$"
    - any:
        - inside: { kind: scoped_identifier, stopBy: end }
        - inside: { kind: scoped_type_identifier, stopBy: end }
        - inside: { kind: scoped_use_list, stopBy: end }
    - any:
        - precedes: { kind: identifier, stopBy: end }
        - precedes: { kind: type_identifier, stopBy: end }
        - precedes: { kind: use_list, stopBy: end }
fix: crate::$MOD
        ' "$AMALGAMATION"/src/"$PACKAGE" --globs '**/*.rs' -U
}

fix_rust_paths common          commn-has-no-deps
fix_rust_paths posting_list    common
fix_rust_paths gridstore       common
fix_rust_paths sparse          'common|gridstore'
fix_rust_paths segment         'common|posting_list|quantization|gridstore|sparse'
fix_rust_paths quantization    'common|gridstore'
fix_rust_paths api             'sparse|segment|common'
fix_rust_paths shard           'common|posting_list|quantization|gridstore|sparse|segment|api'
fix_rust_paths edge            'common|posting_list|quantization|gridstore|sparse|segment|api|shard'
