#!/bin/sh

USE_GPUS="$1"
echo "USE_GPUS=$USE_GPUS"
shift

ENV_GENERAL="train-settings/general/gpu-train-dev.env"
## use next argument as gpu nbr, if available
if [ -n "$1" ]; then
    ENV_GENERAL="$1"
    shift
fi
echo "ENV_GENERAL=$ENV_GENERAL"


## SEMEVAL2010T8 relation extraction via LM

## EDGES
./train.sh "$USE_GPUS" RE_DEP/SEMEVAL2010T8/EDGES/LM train-settings/task/redep-semeval.env train-settings/model/lm.env train-settings/dataset/corenlp/semeval-edges-FIXED.env "$ENV_GENERAL"
