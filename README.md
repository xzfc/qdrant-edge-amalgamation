```sh
cd /path/to/qdrant/repo
git checkout origin/fixes-for-amalgamator

cd /path/to/this/repo
./amalgamate.py /path/to/qdrant/repo

cd edge_example
cargo build
```
