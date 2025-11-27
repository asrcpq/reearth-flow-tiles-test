set -e
cd ~/Projects/reearth-flow/engine
cargo build
cargo clippy
cargo fmt
cargo make doc-action
cargo make generate-examples-cms-workflow
cargo make test
