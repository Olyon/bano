#!/bin/bash

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
source $SCRIPT_DIR/config

PBF_URL=${1:-http://download.openstreetmap.fr/extracts/europe/france/auvergne.osm.pbf}
PBF_FILE=$(basename "$PBF_URL")

mkdir -p $DOWNLOAD_DIR
cd $DOWNLOAD_DIR
wget -NS $PBF_URL

cd $SCRIPT_DIR
osm2pgsql -S osm2pgsql.style -s -l -d bano -U famille -p osm2pgsql $DOWNLOAD_DIR/$PBF_FILE

$pgsql_BANO -f $SCRIPT_DIR/sql/finalisation_osm2pgsql.sql
