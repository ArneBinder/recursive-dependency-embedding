# from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import csv
import fnmatch
import json
import logging
import ntpath
import os
import re
# import google3
import shutil
from functools import reduce, partial
import copy

import numpy as np
import six
import tensorflow as tf
import tensorflow_fold as td
from scipy.stats.mstats import spearmanr
from scipy.stats.stats import pearsonr

import constants
import corpus_simtuple
import lexicon as lex
import model_fold

# model flags (saved in flags.json)
import mytools
import sequence_trees as sqt

default_config = {'train_data_path': ['DEFINE_string',
                                      # '/media/arne/WIN/Users/Arne/ML/data/corpora/ppdb/process_sentence3_ns1/PPDB_CMaggregate',
                                      # '/media/arne/WIN/Users/Arne/ML/data/corpora/sick/process_sentence2/SICK_CMaggregate',
                                      '/media/arne/WIN/ML/data/corpora/SICK/process_sentence3_marked/SICK_CMaggregate',
                                      # SICK default
                                      # '/media/arne/WIN/Users/Arne/ML/data/corpora/STSBENCH/process_sentence3/STSBENCH_CMaggregate',	# STSbench default
                                      # '/media/arne/WIN/Users/Arne/ML/data/corpora/ANNOPPDB/process_sentence3/ANNOPPDB_CMaggregate',   # ANNOPPDB default
                                      # '/media/arne/WIN/Users/Arne/ML/data/corpora/sick/process_sentence2/SICK_tt_CMsequence_ICMtree',
                                      # '/media/arne/WIN/Users/Arne/ML/data/corpora/sick/process_sentence3/SICK_tt_CMsequence_ICMtree',
                                      # '/media/arne/WIN/Users/Arne/ML/data/corpora/sick/process_sentence4/SICK_tt_CMsequence_ICMtree',
                                      # '/media/arne/WIN/Users/Arne/ML/data/corpora/debate_cluster/process_sentence3/HASAN_CMaggregate',
                                      # '/media/arne/WIN/Users/Arne/ML/data/corpora/debate_cluster/process_sentence3/HASAN_CMaggregate_NEGSAMPLES0',
                                      # '/media/arne/WIN/Users/Arne/ML/data/corpora/debate_cluster/process_sentence3/HASAN_CMsequence_ICMtree_NEGSAMPLES0',
                                      #   '/media/arne/WIN/Users/Arne/ML/data/corpora/debate_cluster/process_sentence3/HASAN_CMsequence_ICMtree_NEGSAMPLES1',
                                      'TF Record file containing the training dataset of sequence tuples.',
                                      'data'],
                  'batch_size': ['DEFINE_integer',
                                 100,
                                 'How many samples to read per batch.',
                                 'batchs'],
                  'epochs': ['DEFINE_integer',
                             1000000,
                             'The number of epochs.',
                             None],
                  'dev_file_index': ['DEFINE_integer',
                                     1,
                                     'Which file of the train data files should be used as test data.',
                                     'test_file_i'],
                  'lexicon_trainable': ['DEFINE_boolean',
                                        #   True,
                                        False,
                                        'Iff enabled, fine tune the embeddings.',
                                        'lex_train'],
                  'sim_measure': ['DEFINE_string',
                                  'sim_cosine',
                                  'similarity measure implementation (tensorflow) from model_fold for similarity score '
                                  'calculation. Currently implemented:'
                                  '"sim_cosine" -> cosine'
                                  '"sim_layer" -> similarity measure similar to the one defined in [Tai, Socher 2015]'
                                  '"sim_manhattan" -> l1-norm based similarity measure (taken from MaLSTM) [Mueller et al., 2016]',
                                  'sm'],
                  'tree_embedder': ['DEFINE_string',
                                    'TreeEmbedding_FLAT_AVG',
                                    'TreeEmbedder implementation from model_fold that produces a tensorflow fold block on '
                                    'calling which accepts a sequence tree and produces an embedding. '
                                    'Currently implemented (see model_fold.py):'
                                    '"TreeEmbedding_TREE_LSTM"           -> TreeLSTM'
                                    '"TreeEmbedding_HTU_GRU"             -> Headed Tree Unit, using a GRU for order aware '
                                    '                                       and summation for order unaware composition'
                                    '"TreeEmbedding_FLAT_AVG"            -> Averaging applied to first level children '
                                    '                                       (discarding the root)'
                                    '"TreeEmbedding_FLAT_AVG_2levels"    -> Like TreeEmbedding_FLAT_AVG, but concatenating first'
                                    '                                       second level children (e.g. dep-edge embedding) to '
                                    '                                       the first level children (e.g. token embeddings)'
                                    '"TreeEmbedding_FLAT_LSTM"           -> LSTM applied to first level children (discarding the'
                                    '                                       root)'
                                    '"TreeEmbedding_FLAT_LSTM_2levels"   -> Like TreeEmbedding_FLAT_LSTM, but concatenating '
                                    '                                       first second level children (e.g. dependency-edge '
                                    '                                       type embedding) to the first level children '
                                    '                                       (e.g. token embeddings)',
                                    'te'
                                    ],
                  'leaf_fc_size': ['DEFINE_integer',
                                   0,
                                   # 50,
                                   'If not 0, apply a fully connected layer with this size before composition',
                                   'leaffc'
                                   ],
                  'root_fc_size': ['DEFINE_integer',
                                   0,
                                   # 50,
                                   'If not 0, apply a fully connected layer with this size after composition',
                                   'rootfc'
                                   ],
                  'state_size': ['DEFINE_integer',
                                 50,
                                 'size of the composition layer',
                                 'state'],
                  'learning_rate': ['DEFINE_float',
                                    0.02,
                                    # 'tanh',
                                    'learning rate',
                                    'learning_r'],
                  'optimizer': ['DEFINE_string',
                                'AdadeltaOptimizer',
                                'optimizer',
                                'opt'],
                  'early_stop_queue': ['DEFINE_integer',
                                       50,
                                       'If not 0, stop training when current test loss is smaller then last queued '
                                       'previous losses',
                                       None],
                  'keep_prob': ['DEFINE_float',
                                0.7,
                                'Keep probability for dropout layer'
                                ],
                  'auto_restore': ['DEFINE_boolean',
                                   False,
                                   #   True,
                                   'Iff enabled, restore from last checkpoint if no improvements during epoch on test data.',
                                   'restore'],
                  'data_single': ['DEFINE_boolean',
                                  False,
                                  #   True,
                                  'If enabled, use iterate_scored_tree_data to load train data and set roots of sim_tuple '
                                  'entries to fixed dummy value (IDENTITY_idx) for test data. Create a dedicated training '
                                  'and test models.',
                                  'single'],
                  'extensions': ['DEFINE_string',
                                 '',
                                 'extensions of the files to use as train/test files (appended to .idx.<NR> file names)',
                                 'ext'],
                  'clipping': ['DEFINE_float',
                               5.0,
                               'global norm threshold for clipping gradients',
                               'clip'],

                  }

# non-saveable flags
tf.flags.DEFINE_string('logdir',
                       # '/home/arne/ML_local/tf/supervised/log/dataPs2aggregate_embeddingsUntrainable_simLayer_modelTreelstm_normalizeTrue_batchsize250',
                       #  '/home/arne/ML_local/tf/supervised/log/dataPs2aggregate_embeddingsTrainable_simLayer_modelAvgchildren_normalizeTrue_batchsize250',
                       #  '/home/arne/ML_local/tf/supervised/log/SA/EMBEDDING_FC_dim300',
                       '/home/arne/ML_local/tf/supervised/log/SA/PRETRAINED',
                       'Directory in which to write event logs.')
tf.flags.DEFINE_string('test_file',
                       None,
                       'Set this to execute only.')
tf.flags.DEFINE_boolean('test_only',
                        False,
                        'Enable to execute evaluation only.')
tf.flags.DEFINE_string('logdir_continue',
                       None,
                       'continue training with config from flags.json')
tf.flags.DEFINE_string('logdir_pretrained',
                       None,
                       # '/home/arne/ML_local/tf/supervised/log/batchsize100_embeddingstrainableTRUE_learningrate0.001_optimizerADADELTAOPTIMIZER_simmeasureSIMCOSINE_statesize50_testfileindex1_traindatapathPROCESSSENTENCE3SICKTTCMSEQUENCEICMTREE_treeembedderTREEEMBEDDINGHTUGRUSIMPLIFIED',
                       # '/home/arne/ML_local/tf/supervised/log/SA/EMBEDDING_FC/batchsize100_embeddingstrainableTRUE_learningrate0.001_optimizerADADELTAOPTIMIZER_simmeasureSIMCOSINE_statesize50_testfileindex1_traindatapathPROCESSSENTENCE3SICKTTCMAGGREGATE_treeembedderTREEEMBEDDINGFLATAVG2LEVELS',
                       'Set this to fine tune a pre-trained model. The logdir_pretrained has to contain a types file '
                       'with the filename "model.types"'
                       )
tf.flags.DEFINE_boolean('init_only',
                        False,
                        'If True, save the model without training and exit')
tf.flags.DEFINE_string('grid_config_file',
                       None,
                       'read config parameter dict from this file and execute multiple runs')
tf.flags.DEFINE_integer('run_count',
                        1,
                        'repeat each run this often')

# flags which are not logged in logdir/flags.json
tf.flags.DEFINE_string('master', '',
                       'Tensorflow master to use.')
tf.flags.DEFINE_integer('task', 0,
                        'Task ID of the replica running the training.')
tf.flags.DEFINE_integer('ps_tasks', 0,
                        'Number of PS tasks in the job.')
FLAGS = tf.flags.FLAGS


class Config(object):
    def __init__(self, logdir_continue=None, logdir_pretrained=None, values=None):
        if logdir_continue is not None:
            logging.info('load flags from logdir: %s', logdir_continue)
            with open(os.path.join(logdir_continue, 'flags.json'), 'r') as infile:
                self.__dict__['__values'] = json.load(infile)
        elif logdir_pretrained is not None:
            logging.info('load flags from logdir_pretrained: %s', logdir_pretrained)
            # new_train_data_path = default_config['train_data_path']
            # new_extensions = default_config['extensions']
            with open(os.path.join(logdir_pretrained, 'flags.json'), 'r') as infile:
                self._values = json.load(infile)
            self.__dict__['__values']['train_data_path'] = default_config['train_data_path']
            self.__dict__['__values']['extensions'] = default_config['extensions']
        elif values is not None:
            self.__dict__['__values'] = values
        else:
            self.__dict__['__values'] = default_config

    def __getattr__(self, name):
        """Retrieves the 'value' attribute of the entry name."""

        if name not in self.__dict__['__values']:
            raise AttributeError(name)
        return self.__dict__['__values'][name][1]

    def as_dict(self):
        return {k: self.__getattr__(k) for k in self}

    def __setattr__(self, key, value):
        """Sets the 'value' attribute of the entry name."""

        if key not in self.__dict__['__values']:
            raise AttributeError(key)
        self.__dict__['__values'][key][1] = value

    def __iter__(self):
        return iter(self.__dict__['__values'])

    def dump(self, logdir):
        # write flags for current run
        filename = os.path.join(logdir, 'flags.json')
        with open(filename, 'w') as outfile:
            json.dump(self.__dict__['__values'], outfile, indent=2, sort_keys=True)

    def set_run_description(self):
        if 'run_description' not in self.__dict__['__values']:
            run_desc = []
            for flag in sorted(self.__dict__['__values'].keys()):
                # get real flag value
                # new_value = getattr(FLAGS, flag)
                # default_config[flag][1] = new_value
                # value = config[flag][1]
                value = getattr(self, flag)
                entry_values = self.__dict__['__values'][flag]

                # collect run description
                # if 'run_description' not in config:
                # if a short flag name is set, use it. if it is set to None, add this flag not to the run_descriptions
                if len(entry_values) < 4 or entry_values[3]:
                    if len(entry_values) >= 4:
                        flag_name = entry_values[3]
                    else:
                        flag_name = flag
                    flag_name = flag_name.replace('_', '')
                    flag_value = str(value).replace('_', '').replace(',', '-')
                    # if flag_value is a path, take only the last two subfolders
                    flag_value = ''.join(flag_value.split(os.sep)[-2:])
                    run_desc.append(flag_name.lower() + flag_value.upper())
                self.__dict__['__values']['run_description'] = ['DEFINE_string',
                                                                '_'.join(run_desc),
                                                                'short string description of the current run',
                                                                None]
            logging.debug('set run description: %s' % self.run_description)
            # if 'run_description' not in config:
            #    config['run_description'] = ['DEFINE_string', '_'.join(run_desc), 'short string description of the current run', None]
            #    logging.info('serialized run description: ' + config['run_description'][1])

    def update_with_flags(self, flags):
        for flag in self:
            # get real flag value
            if flag in flags.__dict__['__flags']:
                new_value = getattr(flags, flag)
                self.__setattr__(flag, new_value)

    def init_flags(self):
        for flag in self.__dict__['__values'].keys():
            v = self.__dict__['__values'][flag]
            getattr(tf.flags, v[0])(flag, v[1], v[2])

    def __deepcopy__(self):
        newone = type(self)(values=copy.deepcopy(self.__dict__['__values']))
        return newone

    def explode(self, value_dict):
        for d in mytools.dict_product(value_dict):
            temp = self.__deepcopy__()
            for k in d.keys():
                temp.__setattr__(key=k, value=d[k])
            yield temp, d


def emit_values(supervisor, session, step, values, writer=None, csv_writer=None):
    summary = tf.Summary()
    for name, value in six.iteritems(values):
        summary_value = summary.value.add()
        summary_value.tag = name
        summary_value.simple_value = float(value)
    if writer:
        writer.add_summary(summary, step)
    else:
        supervisor.summary_computed(session, summary, global_step=step)
    if csv_writer:
        values['step'] = step
        csv_writer.writerow({k: values[k] for k in values if k in csv_writer.fieldnames})


def checkpoint_path(logdir, step):
    return os.path.join(logdir, 'model.ckpt-' + str(step))


def csv_test_writer(logdir, mode='w'):
    if not os.path.isdir(logdir):
        os.makedirs(logdir)
    test_result_csv = open(os.path.join(logdir, 'results.csv'), mode, buffering=1)
    fieldnames = ['step', 'loss', 'pearson_r', 'sim_avg']
    test_result_writer = csv.DictWriter(test_result_csv, fieldnames=fieldnames, delimiter='\t')
    return test_result_writer


def get_parameter_count_from_shapes(shapes, selector_suffix='/Adadelta'):
    count = 0
    for tensor_name in shapes:
        if tensor_name.endswith(selector_suffix):
            count += reduce((lambda x, y: x * y), shapes[tensor_name])
    return count


def execute_run(config, logdir_continue=None, logdir_pretrained=None, test_file=None, init_only=None, test_only=None):
    config.set_run_description()

    logdir = logdir_continue or os.path.join(FLAGS.logdir, config.run_description)
    logging.info('logdir: %s' % logdir)
    if not os.path.isdir(logdir):
        os.makedirs(logdir)

    logger = logging.getLogger('')
    fh_debug = logging.FileHandler(os.path.join(logdir, 'train-debug.log'))
    fh_debug.setLevel(logging.DEBUG)
    logger.addHandler(fh_debug)
    fh_info = logging.FileHandler(os.path.join(logdir, 'train-info.log'))
    fh_info.setLevel(logging.INFO)
    logger.addHandler(fh_info)

    # GET CHECKPOINT or PREPARE LEXICON ################################################################################

    checkpoint_fn = tf.train.latest_checkpoint(logdir)
    if logdir_continue:
        assert checkpoint_fn is not None, 'could not read checkpoint from logdir: %s' % logdir
    old_checkpoint_fn = None
    lexicon = None
    if checkpoint_fn:
        if not checkpoint_fn.startswith(logdir):
            raise ValueError('entry in checkpoint file ("%s") is not located in logdir=%s' % (checkpoint_fn, logdir))
        logging.info('read lex_size from model ...')
        reader = tf.train.NewCheckpointReader(checkpoint_fn)
        saved_shapes = reader.get_variable_to_shape_map()
        logging.debug(saved_shapes)
        logging.debug('parameter count: %i' % get_parameter_count_from_shapes(saved_shapes))
        # create test result writer
        test_result_writer = csv_test_writer(os.path.join(logdir, 'test'), mode='a')
        lexicon = lex.Lexicon(filename=os.path.join(logdir, 'model'))
        assert len(lexicon) == saved_shapes[model_fold.VAR_NAME_LEXICON][0]
        ROOT_idx = lexicon[constants.vocab_manual[constants.ROOT_EMBEDDING]]
        IDENTITY_idx = lexicon[constants.vocab_manual[constants.IDENTITY_EMBEDDING]]
        # TODO: ENTRY1 and ENTRY2 add to vocab_manual (changes lexicon creation!)
        if config.data_single:
            ENTRY1_idx = lexicon[u'ENTRY1']
            ENTRY2_idx = lexicon[u'ENTRY2']
    else:
        lexicon = lex.Lexicon(filename=config.train_data_path)
        if logdir_pretrained:
            logging.info('load lexicon from pre-trained model: %s' % logdir_pretrained)
            old_checkpoint_fn = tf.train.latest_checkpoint(logdir_pretrained)
            assert old_checkpoint_fn is not None, 'No checkpoint file found in logdir_pretrained: ' + logdir_pretrained
            reader_old = tf.train.NewCheckpointReader(old_checkpoint_fn)
            lexicon_old = lex.Lexicon(filename=os.path.join(logdir_pretrained, 'model'))
            lexicon_old.init_vecs(reader_old.get_tensor(model_fold.VAR_NAME_LEXICON))
            lexicon.merge(lexicon_old, add=False, remove=False)

        ROOT_idx = lexicon[constants.vocab_manual[constants.ROOT_EMBEDDING]]
        IDENTITY_idx = lexicon[constants.vocab_manual[constants.IDENTITY_EMBEDDING]]
        # TODO: ENTRY1 and ENTRY2 add to vocab_manual (changes lexicon creation!)
        if config.data_single:
            ENTRY1_idx = lexicon[u'ENTRY1']
            ENTRY2_idx = lexicon[u'ENTRY2']
            lexicon.pad()

        lexicon.dump(filename=os.path.join(logdir, 'model'), types_only=True)
        assert lexicon.is_filled, 'lexicon: not all vecs for all types are set (len(types): %i, len(vecs): %i)' % \
                                  (len(lexicon), len(lexicon.vecs))

        # dump config
        config.dump(logdir=logdir)

        # create test result writer
        test_result_writer = csv_test_writer(os.path.join(logdir, 'test'))
        test_result_writer.writeheader()

    logging.info('lexicon size: %i' % len(lexicon))
    logging.debug('IDENTITY_idx: %i' % IDENTITY_idx)
    logging.debug('ROOT_idx: %i' % ROOT_idx)

    # TRAINING and TEST DATA ###########################################################################################

    # use this to enable full head dropout
    def set_head_neg(tree):
        tree['head'] -= len(lexicon)
        for c in tree['children']:
            set_head_neg(c)

    def data_tuple_iterator(sim_index_files, sequence_trees, root_idx=None, shuffle=False, extensions=None, split=False,
                            head_dropout=False, merge_prob_idx=None, subtree_head_ids=None):
        if merge_prob_idx is not None:
            assert subtree_head_ids is not None and type(subtree_head_ids) == list, \
                'merge_prob_idx is given (%i), but subtree_head_ids is not a list' % merge_prob_idx
            assert root_idx is not None, 'merge_prob_idx is given (%i), but root_idx is not set' % merge_prob_idx
            assert not shuffle, 'merge_prob_idx is given (%i), but SHUFFLE is enabled' % merge_prob_idx
            assert not split, 'merge_prob_idx is given (%i), but SPLIT is enabled' % merge_prob_idx
        n_last = None
        for sim_index_file in sim_index_files:
            indices, probs = corpus_simtuple.load_sim_tuple_indices(sim_index_file, extensions)
            n = len(indices[0])
            assert n_last is None or n_last == n, 'all (eventually merged) index tuple files have to contain the ' \
                                                  'same amount of tuple entries, but entries in %s ' \
                                                  '(with extensions=%s) deviate with %i from %i' \
                                                  % (sim_index_file, str(extensions), n, n_last)
            n_last = n
            for idx in range(len(indices)):
                index_tuple = indices[idx]
                _trees = [sequence_trees.get_tree_dict_unsorted(i) for i in index_tuple]
                _probs = probs[idx]

                if merge_prob_idx is not None:
                    for i in range(n):
                        _trees[i]['head'] = subtree_head_ids[i]
                    new_root = {'head': root_idx, 'children': _trees}
                    _trees = [new_root]
                    _probs = [_probs[merge_prob_idx]]
                else:
                    if root_idx is not None:
                        _trees[0]['head'] = root_idx
                    # unify heads
                    for i in range(1, n):
                        _trees[i]['head'] = _trees[0]['head']

                if head_dropout:
                    for t in _trees:
                        set_head_neg(t)

                if shuffle:
                    perm = np.random.permutation(n)
                    [_trees, _probs] = [[_trees[i] for i in perm], np.array([_probs[i] for i in perm])]
                if split:
                    for i in range(1, n):
                        yield [[_trees[0], _trees[i]], np.array([_probs[0], _probs[i]])]
                else:
                    yield [_trees, _probs]

    extensions = config.extensions.split(',')
    if config.data_single:
        # extensions = ['', '.negs1']
        #data_iterator_train = partial(data_tuple_iterator, extensions=extensions)
        #data_iterator_dev = partial(data_tuple_iterator, extensions=extensions)
        data_iterator_train = partial(data_tuple_iterator, root_idx=ROOT_idx, merge_prob_idx=1, subtree_head_ids=[ENTRY1_idx, ENTRY2_idx])
        data_iterator_dev = partial(data_tuple_iterator, root_idx=ROOT_idx, merge_prob_idx=1, subtree_head_ids=[ENTRY1_idx, ENTRY2_idx])
        #tuple_size = 3  # [1.0, <sim_value>, 0.0]   # [first_sim_entry, second_sim_entry, one neg_sample]
        tuple_size = 1
    else:
        data_iterator_train = partial(data_tuple_iterator, root_idx=ROOT_idx, split=True, extensions=extensions)
        data_iterator_dev = partial(data_tuple_iterator, root_idx=ROOT_idx, split=True, extensions=extensions)
        tuple_size = 2  # [1.0, <sim_value>]   # [first_sim_entry, second_sim_entry]

    parent_dir = os.path.abspath(os.path.join(config.train_data_path, os.pardir))
    if test_file is not None:
        test_fname = os.path.join(parent_dir, test_file)
        test_iterator = partial(data_tuple_iterator, sim_index_files=[test_fname], root_idx=ROOT_idx, split=True)
    else:
        test_iterator = None
    if not (test_only or init_only):
        logging.info('collect train data from: ' + config.train_data_path + ' ...')
        regex = re.compile(r'%s\.idx\.\d+$' % ntpath.basename(config.train_data_path))
        train_fnames = filter(regex.search, os.listdir(parent_dir))
        # regex = re.compile(r'%s\.idx\.\d+\.negs\d+$' % ntpath.basename(FLAGS.train_data_path))
        # train_fnames_negs = filter(regex.search, os.listdir(parent_dir))
        # TODO: use train_fnames_negs
        train_fnames = [os.path.join(parent_dir, fn) for fn in sorted(train_fnames)]
        assert len(train_fnames) > 0, 'no matching train data files found for ' + config.train_data_path
        logging.info('found ' + str(len(train_fnames)) + ' train data files')
        test_fname = train_fnames[config.dev_file_index]
        logging.info('use ' + test_fname + ' for testing')
        del train_fnames[config.dev_file_index]
        train_iterator = partial(data_iterator_train, sim_index_files=train_fnames)
        dev_iterator = partial(data_iterator_dev, sim_index_files=[test_fname])
    elif test_only:
        assert test_iterator is not None, 'flag "test_file" has to be set if flag "test_only" is enabled, but it is None'
        train_iterator = None
        dev_iterator = None
    else:
        dev_iterator = None
        train_iterator = None
        test_iterator = None

    # MODEL DEFINITION #################################################################################################

    optimizer = config.optimizer
    if optimizer is not None:
        optimizer = getattr(tf.train, optimizer)

    sim_measure = getattr(model_fold, config.sim_measure)
    tree_embedder = getattr(model_fold, config.tree_embedder)

    logging.info('create tensorflow graph ...')
    with tf.Graph().as_default() as graph:
        with tf.device(tf.train.replica_device_setter(FLAGS.ps_tasks)):
            # Build the graph.
            model_tree = model_fold.SequenceTreeModel(lex_size=len(lexicon),
                                                      tree_embedder=tree_embedder,
                                                      state_size=config.state_size,
                                                      lexicon_trainable=config.lexicon_trainable,
                                                      leaf_fc_size=config.leaf_fc_size,
                                                      root_fc_size=config.root_fc_size,
                                                      keep_prob=config.keep_prob,
                                                      tree_count=tuple_size
                                                      # keep_prob_fixed=config.keep_prob # to enable full head dropout
                                                      )

            if config.data_single:
                # has to be created first #TODO: really?
                model_train = model_fold.ScoredSequenceTreeTupleModel_independent(tree_model=model_tree,
                                                                                  optimizer=optimizer,
                                                                                  learning_rate=config.learning_rate,
                                                                                  clipping_threshold=config.clipping)
                #model_test = model_fold.SimilaritySequenceTreeTupleModel(tree_model=model_tree,
                #                                                         optimizer=None,
                #                                                         learning_rate=config.learning_rate,
                #                                                         sim_measure=sim_measure,
                #                                                         clipping_threshold=config.clipping)
                model_test = model_train
            else:
                model_test = model_fold.SimilaritySequenceTreeTupleModel(tree_model=model_tree,
                                                                         optimizer=optimizer,
                                                                         learning_rate=config.learning_rate,
                                                                         sim_measure=sim_measure,
                                                                         clipping_threshold=config.clipping)
                model_train = model_test

            # PREPARE TRAINING #########################################################################################

            if old_checkpoint_fn is not None:
                logging.info(
                    'restore from old_checkpoint (except lexicon, step and optimizer vars): %s ...' % old_checkpoint_fn)
                lexicon_vars = tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES, scope=model_fold.VAR_NAME_LEXICON)
                optimizer_vars = model_train.optimizer_vars() + [model_train.global_step] \
                                 + ((model_test.optimizer_vars() + [
                    model_test.global_step]) if model_test is not None and model_test != model_train else [])
                restore_vars = [item for item in tf.get_collection(tf.GraphKeys.GLOBAL_VARIABLES) if
                                item not in lexicon_vars + optimizer_vars]
                pre_train_saver = tf.train.Saver(restore_vars)
            else:
                pre_train_saver = None

            def load_pretrain(sess):
                pre_train_saver.restore(sess, old_checkpoint_fn)

            # Set up the supervisor.
            supervisor = tf.train.Supervisor(
                # saver=None,# my_saver,
                logdir=logdir,
                is_chief=(FLAGS.task == 0),
                save_summaries_secs=10,
                save_model_secs=0,
                summary_writer=tf.summary.FileWriter(os.path.join(logdir, 'train'), graph),
                init_fn=load_pretrain if pre_train_saver is not None else None
            )
            test_writer = tf.summary.FileWriter(os.path.join(logdir, 'test'), graph)
            sess = supervisor.PrepareSession(FLAGS.master)

            if lexicon.is_filled:
                logging.info('init embeddings with external vectors...')
                sess.run(model_tree.embedder.lexicon_init,
                         feed_dict={model_tree.embedder.lexicon_placeholder: lexicon.vecs})

            if init_only:
                supervisor.saver.save(sess, checkpoint_path(logdir, 0))
                logger.removeHandler(fh_info)
                logger.removeHandler(fh_debug)
                return

            # MEASUREMENT ##############################################################################################

            def collect_values(epoch, step, loss, sim, sim_gold, train, print_out=True, emit=True):
                if train:
                    suffix = 'train'
                    writer = None
                    csv_writer = None
                else:
                    suffix = 'test '
                    writer = test_writer
                    csv_writer = test_result_writer

                emit_dict = {'loss': loss}
                if sim is not None and sim_gold is not None:
                    p_r = pearsonr(sim, sim_gold)
                    s_r = spearmanr(sim, sim_gold)
                    emit_dict.update(
                        {'pearson_r': p_r[0], 'pearson_r_p': p_r[1], 'spearman_r': s_r[0], 'spearman_r_p': s_r[1],
                         'sim_avg': np.average(sim)})
                    info_string = (
                                      'epoch=%d step=%d: loss_%s=%f\tpearson_r_%s=%f\tsim_avg=%f\tsim_gold_avg=%f\tsim_gold_var=%f') % (
                                      epoch, step, suffix, loss, suffix, p_r[0], np.average(sim),
                                      np.average(sim_gold), np.var(sim_gold))
                else:
                    info_string = (
                                      'epoch=%d step=%d: loss_%s=%f') % (epoch, step, suffix, loss)
                if emit:
                    emit_values(supervisor, sess, step, emit_dict, writer=writer, csv_writer=csv_writer)
                if print_out:
                    logging.info(info_string)

            # TRAINING #################################################################################################

            def do_epoch(model, data_set, epoch, train=True, emit=True, test_step=0, new_model=False):

                step = test_step
                feed_dict = {}
                execute_vars = {'loss': model.loss}
                if new_model:
                    execute_vars['probs_gold'] = model.tree_model.probs_gold
                else:
                    execute_vars['scores'] = model.scores
                    execute_vars['scores_gold'] = model.scores_gold
                    # execute_vars['probs_gold'] = model.tree_model.probs_gold
                    # execute_vars['probs_gold_flattened'] = model.tree_model.probs_gold_flattened
                    # execute_vars['embeddings_all'] = model.tree_model.embeddings_all
                    # execute_vars['embeddings_all_flattened'] = model.tree_model.embeddings_all_flattened
                if train:
                    execute_vars['train_op'] = model.train_op
                    execute_vars['step'] = model.global_step
                else:
                    feed_dict[model.tree_model.keep_prob] = 1.0

                _result_all = []

                # for batch in td.group_by_batches(data_set, config.batch_size if train else len(test_set)):
                for batch in td.group_by_batches(data_set, config.batch_size):
                    feed_dict[model.tree_model.compiler.loom_input_tensor] = batch
                    _result_all.append(sess.run(execute_vars, feed_dict))

                # list of dicts to dict of lists
                result_all = dict(zip(_result_all[0], zip(*[d.values() for d in _result_all])))

                # if train, set step to last executed step
                if train and len(_result_all) > 0:
                    step = result_all['step'][-1]

                # logging.debug(np.concatenate(score_all).tolist())
                # logging.debug(np.concatenate(score_all_gold).tolist())

                if new_model:
                    sizes = [len(result_all['probs_gold'][i]) for i in range(len(_result_all))]
                    score_all_ = None
                    score_all_gold_ = None
                else:
                    sizes = [len(result_all['scores_gold'][i]) for i in range(len(_result_all))]
                    score_all_gold_ = np.concatenate(result_all['scores_gold'])
                    score_all_ = np.concatenate(result_all['scores'])
                # sum batch losses weighted by individual batch size (can vary at last batch)
                loss_all = sum([result_all['loss'][i] * sizes[i] for i in range(len(_result_all))])
                loss_all /= sum(sizes)

                collect_values(epoch, step, loss_all, score_all_, score_all_gold_, train=train, emit=emit)
                return step, loss_all, score_all_, score_all_gold_

            # data, parents = sqt.load(config.train_data_path)
            # children, roots = sqt.children_and_roots(parents)
            sqt_data = sqt.Forest(filename=config.train_data_path)
            with model_tree.compiler.multiprocessing_pool():
                if model_test is not None:

                    if test_iterator is not None:
                        logging.info('create test data set ...')
                        test_set = list(
                            model_test.tree_model.compiler.build_loom_inputs(test_iterator(sequence_trees=sqt_data)))
                        logging.info('test data size: ' + str(len(test_set)))
                        if train_iterator is None:
                            step, loss_all, score_all, score_all_gold = do_epoch(model_test, test_set, 0, train=False,
                                                                                 emit=False)
                            p_r = pearsonr(score_all, score_all_gold)[0]
                            score_all.dump(os.path.join(logdir, 'sims.np'))
                            logger.removeHandler(fh_info)
                            logger.removeHandler(fh_debug)
                            return p_r, np.mean(np.square(score_all - score_all_gold))

                    logging.info('create dev data set ...')
                    dev_set = list(
                        model_test.tree_model.compiler.build_loom_inputs(dev_iterator(sequence_trees=sqt_data)))
                    logging.info('dev data size: ' + str(len(dev_set)))

                logging.info('create train data set ...')
                # data_train = list(train_iterator)
                train_set = model_tree.compiler.build_loom_inputs(train_iterator(sequence_trees=sqt_data))
                # logging.info('train data size: ' + str(len(data_train)))
                # dev_feed_dict = compiler.build_feed_dict(dev_trees)
                logging.info('training the model')
                loss_test_best = 9999
                TEST_MIN_INIT = -1
                test_p_rs = [TEST_MIN_INIT]
                step_train = sess.run(model_train.global_step)
                max_queue_length = 0
                for epoch, shuffled in enumerate(td.epochs(train_set, config.epochs, shuffle=True), 1):

                    # train
                    if not config.early_stop_queue or len(test_p_rs) > 0:
                        step_train, _, _, _ = do_epoch(model_train, shuffled, epoch, new_model=config.data_single)

                    if model_test is not None:
                        # test
                        step_test, loss_test, sim_all, sim_all_gold = do_epoch(model_test, dev_set, epoch,
                                                                               train=False, test_step=step_train,
                                                                               new_model=config.data_single)

                        if loss_test < loss_test_best:
                            loss_test_best = loss_test

                        # EARLY STOPPING ###############################################################################

                        if not config.data_single:
                            # loss_test = round(loss_test, 6) #100000000
                            p_r = pearsonr(sim_all, sim_all_gold)[0]
                        else:
                            p_r = 1. - loss_test
                        p_r = round(p_r, 6)
                        prev_max = max(test_p_rs)
                        # stop, if current test pearson r is not bigger than previous values. The amount of regarded
                        # previous values is set by config.early_stop_queue
                        if p_r > prev_max:
                            test_p_rs = []
                        else:
                            if len(test_p_rs) >= max_queue_length:
                                max_queue_length = len(test_p_rs) + 1
                        test_p_rs.append(p_r)
                        test_p_rs_sorted = sorted(test_p_rs, reverse=True)
                        rank = test_p_rs_sorted.index(p_r)

                        # write out queue length
                        emit_values(supervisor, sess, step_test, values={'queue_length': len(test_p_rs), 'rank': rank},
                                    writer=test_writer)

                        logging.debug(
                            'pearson_r rank (of %i):\t%i\tdif: %f\tmax_queue_length: %i' % (
                            len(test_p_rs), rank, round((p_r - prev_max), 6), max_queue_length))
                        if 0 < config.early_stop_queue < len(test_p_rs):
                            logging.info('last test pearsons_r: %s, last rank: %i' % (str(test_p_rs), rank))
                            logger.removeHandler(fh_info)
                            logger.removeHandler(fh_debug)
                            return test_p_rs_sorted[0], loss_test_best

                        # do not save, if score was not the best
                        # if rank > len(test_p_rs) * 0.05:
                        if len(test_p_rs) > 1 and config.early_stop_queue:
                            # auto restore if enabled
                            if config.auto_restore:
                                supervisor.saver.restore(sess, tf.train.latest_checkpoint(logdir))
                        else:
                            # don't save after first epoch if config.early_stop_queue > 0
                            if prev_max > TEST_MIN_INIT or not config.early_stop_queue:
                                supervisor.saver.save(sess, checkpoint_path(logdir, step_train))
                    else:
                        supervisor.saver.save(sess, checkpoint_path(logdir, step_train))

                logger.removeHandler(fh_info)
                logger.removeHandler(fh_debug)


if __name__ == '__main__':
    mytools.logging_init()
    logging.debug('test')
    # tf.app.run()
    if FLAGS.logdir_continue is not None and ',' in FLAGS.logdir_continue:
        logdirs = FLAGS.logdir_continue.split(',')
        logging.info('execute %i runs ...' % len(logdirs))
        with open(os.path.join(FLAGS.logdir, 'scores_new.tsv'), 'w') as csvfile:
            fieldnames = Config(logdir_continue=logdirs[0]).as_dict().keys() + ['score_pearson', 'score_mse']
            score_writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter='\t')
            score_writer.writeheader()
            for i, logdir in enumerate(logdirs,1):
                logging.info('START RUN %i of %i' % (i, len(logdirs)))
                config = Config(logdir_continue=logdir)
                config_dict = config.as_dict()
                p, mse = execute_run(config, logdir_continue=logdir, logdir_pretrained=FLAGS.logdir_pretrained,
                                     test_file=FLAGS.test_file, init_only=FLAGS.init_only, test_only=FLAGS.test_only)
                config_dict['score_pearson'] = p
                config_dict['score_mse'] = mse
                score_writer.writerow(config_dict)
                csvfile.flush()
    else:
        config = Config(logdir_continue=FLAGS.logdir_continue, logdir_pretrained=FLAGS.logdir_pretrained)
        config.init_flags()
        # pylint: disable=protected-access
        FLAGS._parse_flags()
        # pylint: enable=protected-access
        config.update_with_flags(FLAGS)
        if FLAGS.grid_config_file is not None:

            parameters_fn = os.path.join(FLAGS.logdir, FLAGS.grid_config_file)
            logging.info('load grid parameters from: %s' % parameters_fn)
            with open(parameters_fn, 'r') as infile:
                grid_parameters = json.load(infile)

            scores_fn = os.path.join(FLAGS.logdir, 'scores.tsv')
            fieldnames_loaded = None
            if os.path.isfile(scores_fn):
                file_mode = 'a'
                with open(scores_fn, 'r') as csvfile:
                    scores_done_reader = csv.DictReader(csvfile, delimiter='\t')
                    fieldnames_loaded = scores_done_reader.fieldnames
                    scores_done = list(scores_done_reader)
                run_descriptions_done = [s_d['run_description'] for s_d in scores_done]
                logging.debug('already finished: %s' % ', '.join(run_descriptions_done))
            else:
                file_mode = 'w'
                run_descriptions_done = []
            logging.info('write scores to: %s' % scores_fn)

            # mytools.make_parent_dir(scores_fn) #logdir has to contain grid_config_file
            fieldnames_expected = grid_parameters.keys() + ['pearson_dev_best', 'pearson_test', 'mse_dev_best',
                                                            'mse_test', 'run_description']
            assert fieldnames_loaded is None or set(fieldnames_loaded) == set(fieldnames_expected), 'field names in tsv file are not as expected'
            fieldnames = fieldnames_loaded or fieldnames_expected
            with open(scores_fn, file_mode) as csvfile:
                score_writer = csv.DictWriter(csvfile, fieldnames=fieldnames, delimiter='\t')
                if file_mode == 'w':
                    score_writer.writeheader()
                    csvfile.flush()

                for i in range(FLAGS.run_count):
                    for c, d in config.explode(grid_parameters):
                        c.set_run_description()
                        run_desc_backup = c.run_description

                        logging.info(
                            'start run ==============================================================================')
                        c.run_description = os.path.join(run_desc_backup, str(i))
                        logdir = os.path.join(FLAGS.logdir, c.run_description)

                        train_data_dir = os.path.abspath(os.path.join(c.train_data_path, os.pardir))
                        if FLAGS.test_file is not None:
                            test_fname = os.path.join(train_data_dir, FLAGS.test_file)
                            assert os.path.isfile(test_fname), 'could not find test file: %s' % test_fname
                        else:
                            test_fname = None

                        # skip already processed
                        if os.path.isdir(logdir) and c.run_description in run_descriptions_done:
                            logging.debug('skip config for logdir: %s' % logdir)
                            c.run_description = run_desc_backup
                            continue

                        d['pearson_dev_best'], d['mse_dev_best'] = execute_run(c)
                        logging.info('best dev score: %f' % d['pearson_dev_best'])
                        if test_fname is not None:
                            d['pearson_test'], d['mse_test'] = execute_run(c, logdir_continue=logdir, test_only=True, test_file=FLAGS.test_file)
                            logging.info('test score: %f' % d['pearson_test'])
                        else:
                            d['pearson_test'] = 0.0
                            d['mse_test'] = -1.0
                        d['run_description'] = c.run_description

                        c.run_description = run_desc_backup
                        score_writer.writerow(d)
                        csvfile.flush()

        else:
            execute_run(config, logdir_continue=FLAGS.logdir_continue, logdir_pretrained=FLAGS.logdir_pretrained,
                        test_file=FLAGS.test_file, init_only=FLAGS.init_only, test_only=FLAGS.test_only)
