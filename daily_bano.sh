#!/bin/bash
./load_code_cadastre.sh
cat deplist.txt | nice ionice -c 2 parallel -j 5 export LANG=fr_FR.UTF-8\; python load_cumul.py {1} OSM #> /dev/null
cat deplist.txt | nice ionice -c 2 parallel -j 5 export LANG=fr_FR.UTF-8\; python load_cumul.py {1} CADASTRE #> /dev/null
cat deplist.txt | nice ionice -c 2 parallel -j 5 export LANG=fr_FR.UTF-8\; python load_cumul_place.py {1} #> /dev/null
#cd out
#./banout-all.sh

