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

## DIRECT + add_heads=EDG,ARGS (manual adding required for LM model)
./train.sh "$USE_GPUS" RE/SEMEVAL2010T8/DIRECT/LM_LCA_NEW train-settings/task/re-semeval.env train-settings/model/lm.env train-settings/dataset/corenlp/semeval-direct.env train-settings/specific/add-heads-EDG-ARGS.env "$ENV_GENERAL"
