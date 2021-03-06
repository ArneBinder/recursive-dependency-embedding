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


## TACRED relation extraction

## DIRECT

# RECNN
./train.sh "$USE_GPUS" RE/TACRED/DIRECT/RECNN train-settings/task/re-tacred.env train-settings/model/recnn.env train-settings/dataset/corenlp/tacred-direct.env "$ENV_GENERAL"

# BOW
./train.sh "$USE_GPUS" RE/TACRED/DIRECT/BOW train-settings/task/re-tacred.env train-settings/model/bow.env train-settings/dataset/corenlp/tacred-direct.env "$ENV_GENERAL"

# RNN
./train.sh "$USE_GPUS" RE/TACRED/DIRECT/RNN train-settings/task/re-tacred.env train-settings/model/rnn.env train-settings/dataset/corenlp/tacred-direct.env "$ENV_GENERAL"

## SPAN

# RECNN
./train.sh "$USE_GPUS" RE/TACRED/SPAN/RECNN train-settings/task/re-tacred.env train-settings/model/recnn.env train-settings/dataset/corenlp/tacred-span.env "$ENV_GENERAL"

# BOW
./train.sh "$USE_GPUS" RE/TACRED/SPAN/BOW train-settings/task/re-tacred.env train-settings/model/bow.env train-settings/dataset/corenlp/tacred-span.env "$ENV_GENERAL"

# RNN
./train.sh "$USE_GPUS" RE/TACRED/SPAN/RNN train-settings/task/re-tacred.env train-settings/model/rnn.env train-settings/dataset/corenlp/tacred-span.env "$ENV_GENERAL"

## EDGES

# RECNN
./train.sh "$USE_GPUS" RE/TACRED/EDGES/RECNN train-settings/task/re-tacred.env train-settings/model/recnn.env train-settings/dataset/corenlp/tacred-edges.env "$ENV_GENERAL"
