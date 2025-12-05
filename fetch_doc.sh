set -e
wget -r -k -E --mirror -p \
     --no-parent \
     --wait=2 \
     --random-wait \
     --limit-rate=200k \
     -e robots=off \
     -U Mozilla \
     https://www.mlit.go.jp/plateaudocument/
