#!/bin/sh

USE_GPUS="$1"
echo "USE_GPUS=$USE_GPUS"

# TACRED relation extraction
./train.sh "$USE_GPUS" RE/TACRED/SPAN/BOW train-settings/general/gpu-search.env train-settings/model/bow.env train-settings/task/re-tacred.env train-settings/dataset/corenlp/tacred-span.env

