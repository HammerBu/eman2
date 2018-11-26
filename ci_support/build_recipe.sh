#!/usr/bin/env bash

set -xe

MYDIR="$(cd "$(dirname "$0")"; pwd -P)"

source ci_support/setup_conda.sh

conda install conda-build=3 -c defaults --yes --quiet

export CPU_COUNT=2

conda info -a
conda list
conda render recipes/eman
conda build purge-all

conda build recipes/eman -c cryoem/label/dev -c cryoem -c defaults -c conda-forge --quiet
