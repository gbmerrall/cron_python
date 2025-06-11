#!/bin/bash

export PATH=$HOME/.local/bin:$PATH

DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd $DIR
pipenv run python $(1).py
