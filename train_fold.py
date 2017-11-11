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

import numpy as np
import six
import tensorflow as tf
import tensorflow_fold as td
from scipy.stats.mstats import spearmanr
from scipy.stats.stats import pearsonr
from sklearn import linear_model

import constants
import corpus_simtuple
import lexicon
import lexicon as lex
import model_fold

# model flags (saved in flags.json)
import mytools
import sequence_trees

model_flags = {'train_data_path': ['DEFINE_string',
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
               'test_file_index': ['DEFINE_integer',
                                   1,
                                   'Which file of the train data files should be used as test data.',
                                   'test_file_i'],
               'lexicon_trainable': ['DEFINE_boolean',
                                     #   False,
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
                                # 0,
                                50,
                                'If not 0, apply a fully connected layer with this size before composition',
                                'leaffc'
                                ],
               'root_fc_size': ['DEFINE_integer',
                                # 0,
                                50,
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
                               'single']

               }

# non-saveable flags
tf.flags.DEFINE_string('logdir',
                       # '/home/arne/ML_local/tf/supervised/log/dataPs2aggregate_embeddingsUntrainable_simLayer_modelTreelstm_normalizeTrue_batchsize250',
                       #  '/home/arne/ML_local/tf/supervised/log/dataPs2aggregate_embeddingsTrainable_simLayer_modelAvgchildren_normalizeTrue_batchsize250',
                       #  '/home/arne/ML_local/tf/supervised/log/SA/EMBEDDING_FC_dim300',
                       '/home/arne/ML_local/tf/supervised/log/SA/PRETRAINED',
                       'Directory in which to write event logs.')
tf.flags.DEFINE_string('test_only_file',
                       None,
                       'Set this to execute evaluation only.')
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

# flags which are not logged in logdir/flags.json
tf.flags.DEFINE_string('master', '',
                       'Tensorflow master to use.')
tf.flags.DEFINE_integer('task', 0,
                        'Task ID of the replica running the training.')
tf.flags.DEFINE_integer('ps_tasks', 0,
                        'Number of PS tasks in the job.')
FLAGS = tf.flags.FLAGS
mytools.logging_init()

if FLAGS.logdir_continue:
    logging.info('load flags from logdir: %s', FLAGS.logdir_continue)
    with open(os.path.join(FLAGS.logdir_continue, 'flags.json'), 'r') as infile:
        model_flags = json.load(infile)
elif FLAGS.logdir_pretrained:
    logging.info('load flags from logdir_pretrained: %s', FLAGS.logdir_pretrained)
    new_train_data_path = model_flags['train_data_path']
    with open(os.path.join(FLAGS.logdir_pretrained, 'flags.json'), 'r') as infile:
        model_flags = json.load(infile)
    model_flags['train_data_path'] = new_train_data_path

for flag in model_flags:
    v = model_flags[flag]
    getattr(tf.flags, v[0])(flag, v[1], v[2])


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


def main(unused_argv):
    run_desc = []
    for flag in sorted(model_flags.keys()):
        # get real flag value
        new_value = getattr(FLAGS, flag)
        model_flags[flag][1] = new_value

        # collect run description
        if 'run_description' not in model_flags:
            # if a short flag name is set, use it. if it is set to None, add this flag not to the run_descriptions
            if len(model_flags[flag]) < 4 or model_flags[flag][3]:
                if len(model_flags[flag]) >= 4:
                    flag_name = model_flags[flag][3]
                else:
                    flag_name = flag
                flag_name = flag_name.replace('_', '')
                flag_value = str(new_value).replace('_', '')
                # if flag_value is a path, take only the last two subfolders
                flag_value = ''.join(flag_value.split(os.sep)[-2:])
                run_desc.append(flag_name.lower() + flag_value.upper())

    if 'run_description' not in model_flags:
        model_flags['run_description'] = ['DEFINE_string', '_'.join(run_desc),
                                          'short string description of the current run', None]
        logging.info('serialized run description: ' + model_flags['run_description'][1])

    logdir = FLAGS.logdir_continue or os.path.join(FLAGS.logdir, model_flags['run_description'][1])
    logging.info('logdir: %s' % logdir)
    if not os.path.isdir(logdir):
        os.makedirs(logdir)

    # GET CHECKPOINT or PREPARE LEXICON ################################################################################

    checkpoint_fn = tf.train.latest_checkpoint(logdir)
    old_checkpoint_fn = None
    vecs = None
    if checkpoint_fn:
        logging.info('read lex_size from model ...')
        reader = tf.train.NewCheckpointReader(checkpoint_fn)
        saved_shapes = reader.get_variable_to_shape_map()
        logging.debug(saved_shapes)
        logging.debug('parameter count: %i' % get_parameter_count_from_shapes(saved_shapes))
        embed_shape = saved_shapes[model_fold.VAR_NAME_LEXICON]
        lex_size = embed_shape[0]
        # create test result writer
        test_result_writer = csv_test_writer(os.path.join(logdir, 'test'), mode='a')
        types = lex.read_types(os.path.join(logdir, 'model'))

        # SOURCE_idx = types.index(constants.vocab_manual[constants.SOURCE_EMBEDDING])
        # COMPATIBILITY
        vecs, types, ROOT_idx = lexicon.add_and_get_idx(vecs, types,
                                                        new_type=constants.vocab_manual[constants.ROOT_EMBEDDING])
        vecs, types, IDENTITY_idx = lexicon.add_and_get_idx(vecs, types,
                                                            new_type=constants.vocab_manual[
                                                                constants.IDENTITY_EMBEDDING])
        # COMPATIBILITY END
        # _SOURCE = constants.vocab_manual[constants.SOURCE_EMBEDDING]
        # if _SOURCE in types:
        #    SOURCE_idx = types.index(_SOURCE)
        # else:
        #    SOURCE_idx = len(types)
        #    # COMPATIBILITY END
    else:
        vecs, types = lex.load(FLAGS.train_data_path)
        if FLAGS.logdir_pretrained:
            logging.info('load lexicon from pre-trained model: %s' % FLAGS.logdir_pretrained)
            old_checkpoint_fn = tf.train.latest_checkpoint(FLAGS.logdir_pretrained)
            assert old_checkpoint_fn is not None, 'No checkpoint file found in logdir_pretrained: ' + FLAGS.logdir_pretrained
            reader_old = tf.train.NewCheckpointReader(old_checkpoint_fn)
            vecs_old = reader_old.get_tensor(model_fold.VAR_NAME_LEXICON)
            types_old = lex.read_types(os.path.join(FLAGS.logdir_pretrained, 'model'))
            vecs, types = lex.merge_dicts(vecs1=vecs, types1=types, vecs2=vecs_old, types2=types_old, add=False,
                                          remove=False)

        vecs, types, ROOT_idx = lexicon.add_and_get_idx(vecs, types,
                                                        new_type=constants.vocab_manual[constants.ROOT_EMBEDDING])
        vecs, types, IDENTITY_idx = lexicon.add_and_get_idx(vecs, types, new_type=constants.vocab_manual[
            constants.IDENTITY_EMBEDDING])

        lex.dump(os.path.join(logdir, 'model'), types=types)
        lex_size = vecs.shape[0]

        # write flags for current run
        with open(os.path.join(logdir, 'flags.json'), 'w') as outfile:
            json.dump(model_flags, outfile, indent=2, sort_keys=True)

        # create test result writer
        test_result_writer = csv_test_writer(os.path.join(logdir, 'test'))
        test_result_writer.writeheader()

    logging.info('lex_size: %i' % lex_size)
    IDENTITY_idx = types.index(constants.vocab_manual[constants.IDENTITY_EMBEDDING])
    logging.debug('IDENTITY_idx: %i' % IDENTITY_idx)
    ROOT_idx = types.index(constants.vocab_manual[constants.ROOT_EMBEDDING])
    logging.debug('ROOT_idx: %i' % ROOT_idx)

    # TRAINING and TEST DATA ###########################################################################################

    def set_head_neg(tree):
        tree['head'] -= lex_size
        for c in tree['children']:
            set_head_neg(c)

    # deprecated
    def tuple_data_iterator(sim_index_files, data, children, replace_idx=None, set_neg=False):
        for sim_index_file in sim_index_files:
            sim_index_tuples = corpus_simtuple.load_sim_tuple_indices(sim_index_file)
            for sim_index_tuple in sim_index_tuples:
                x = {'first': sequence_trees.build_sequence_tree_dict(data, children, sim_index_tuple[0]),
                     'second': sequence_trees.build_sequence_tree_dict(data, children, sim_index_tuple[1]),
                     'similarity': sim_index_tuple[2]}
                if replace_idx:
                    x['first']['head'] = replace_idx
                    x['second']['head'] = replace_idx
                else:
                    x['second']['head'] = x['first']['head']
                if set_neg:
                    set_head_neg(x['first'])
                    set_head_neg(x['second'])
                yield x

    def tuple_data_iterator_simpile(sim_index_files, data, children):
        for sim_index_file in sim_index_files:
            sim_index_tuples = corpus_simtuple.load_sim_tuple_indices(sim_index_file)
            for sim_index_tuple in sim_index_tuples:
                x = {'first': sequence_trees.build_sequence_tree_dict(data, children, sim_index_tuple[0]),
                     'second': sequence_trees.build_sequence_tree_dict(data, children, sim_index_tuple[1]),
                     'similarity': sim_index_tuple[2]}
                yield x

    # if FLAGS.data_single:
    # data_iterator_train = corpus_simtuple.iterate_scored_tree_data
    # data_iterator_test = partial(tuple_data_iterator, replace_idx=IDENTITY_idx, set_neg=True)
    # else:
    # data_iterator_train = partial(tuple_data_iterator, replace_idx=ROOT_idx)
    # data_iterator_test = partial(tuple_data_iterator, replace_idx=ROOT_idx, set_neg=True)

    data_iterator_train = tuple_data_iterator_simpile
    data_iterator_test = tuple_data_iterator_simpile

    parent_dir = os.path.abspath(os.path.join(FLAGS.train_data_path, os.pardir))
    if not (FLAGS.test_only_file or FLAGS.init_only):
        logging.info('collect train data from: ' + FLAGS.train_data_path + ' ...')
        regex = re.compile(r'%s\.idx\.\d+$' % ntpath.basename(FLAGS.train_data_path))
        train_fnames = filter(regex.search, os.listdir(parent_dir))
        regex = re.compile(r'%s\.idx\.\d+\.negs\d+$' % ntpath.basename(FLAGS.train_data_path))
        train_fnames_negs = filter(regex.search, os.listdir(parent_dir))
        # TODO: use train_fnames_negs
        train_fnames = [os.path.join(parent_dir, fn) for fn in sorted(train_fnames)]
        assert len(train_fnames) > 0, 'no matching train data files found for ' + FLAGS.train_data_path
        logging.info('found ' + str(len(train_fnames)) + ' train data files')
        test_fname = train_fnames[FLAGS.test_file_index]
        logging.info('use ' + test_fname + ' for testing')
        del train_fnames[FLAGS.test_file_index]
        train_iterator = partial(data_iterator_train, sim_index_files=train_fnames)
        test_iterator = partial(data_iterator_test, sim_index_files=[test_fname])
    elif FLAGS.test_only_file:
        test_fname = os.path.join(parent_dir, FLAGS.test_only_file)
        test_iterator = partial(data_iterator_test, sim_index_files=[test_fname])
        train_iterator = None
    else:
        test_iterator = None
        train_iterator = None

    # MODEL DEFINITION #################################################################################################

    optimizer = FLAGS.optimizer
    if FLAGS.optimizer:
        optimizer = getattr(tf.train, optimizer)

    sim_measure = getattr(model_fold, FLAGS.sim_measure)
    tree_embedder = getattr(model_fold, FLAGS.tree_embedder)

    logging.info('create tensorflow graph ...')
    with tf.Graph().as_default() as graph:
        with tf.device(tf.train.replica_device_setter(FLAGS.ps_tasks)):
            # Build the graph.
            model_tree = model_fold.SequenceTreeModel(lex_size=lex_size,
                                                      tree_embedder=tree_embedder,
                                                      state_size=FLAGS.state_size,
                                                      lexicon_trainable=FLAGS.lexicon_trainable,
                                                      leaf_fc_size=FLAGS.leaf_fc_size,
                                                      root_fc_size=FLAGS.root_fc_size,
                                                      keep_prob=FLAGS.keep_prob,
                                                      # keep_prob_fixed=FLAGS.keep_prob # to enable full head dropout
                                                      )

            # has to be created first #TODO: really?
            if FLAGS.data_single:
                model_train = model_fold.SimilaritySequenceTreeTupleModel2(tree_model=model_tree,
                                                                           learning_rate=FLAGS.learning_rate,
                                                                           optimizer=optimizer,
                                                                           tree_count=2)
                # reg = linear_model.LinearRegression()

            model_test = model_fold.SimilaritySequenceTreeTupleModel(tree_model=model_tree,
                                                                     learning_rate=FLAGS.learning_rate,
                                                                     optimizer=optimizer,
                                                                     sim_measure=sim_measure,
                                                                     idx_root=IDENTITY_idx if FLAGS.data_single else None
                                                                     )
            if not FLAGS.data_single:
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

            if vecs is not None:
                logging.info('init embeddings with external vectors...')
                sess.run(model_tree.embedder.lexicon_init,
                         feed_dict={model_tree.embedder.lexicon_placeholder: vecs})

            if FLAGS.init_only:
                supervisor.saver.save(sess, checkpoint_path(logdir, 0))
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
                    emit_dict.update({'pearson_r': p_r[0], 'pearson_r_p': p_r[1], 'spearman_r': s_r[0], 'spearman_r_p': s_r[1], 'sim_avg': np.average(sim)})
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
                    execute_vars['probs_gold'] = model.probs_gold
                else:
                    execute_vars['scores'] = model.scores
                    execute_vars['scores_gold'] = model.scores_gold
                if train:
                    execute_vars['train_op'] = model.train_op
                    execute_vars['step'] = model.global_step
                else:
                    feed_dict[model.keep_prob] = 1.0
                #if apply_linreg:
                #    execute_vars['embeddings'] = model.tree_embeddings_all

                _result_all = []

                # for batch in td.group_by_batches(data_set, FLAGS.batch_size if train else len(test_set)):
                for batch in td.group_by_batches(data_set, FLAGS.batch_size):
                    feed_dict[model.compiler.loom_input_tensor] = batch
                    _result_all.append(sess.run(execute_vars, feed_dict))

                # list of dicts to dict of lists
                result_all = dict(zip(_result_all[0], zip(*[d.values() for d in _result_all])))

                # if train, set step to last executed step
                if train and len(_result_all) > 0:
                    step = result_all['step'][-1]

                # logging.debug(np.concatenate(score_all).tolist())
                # logging.debug(np.concatenate(score_all_gold).tolist())



                #if apply_linreg:
                #    # EXPERIMENTAL
                #    embeddings_all = np.concatenate(result_all['embeddings'], axis=0)
                #    reg.fit(embeddings_all, score_all_gold_)
                #    score_all_ = np.matmul(embeddings_all, reg.coef_)
                #    loss_all = np.mean((score_all_ - score_all_gold_) ** 2)
                #    # EXPERIMENTAL end
                #else:
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

            data, parents = sequence_trees.load(FLAGS.train_data_path)
            children, roots = sequence_trees.children_and_roots(parents)
            with model_train.compiler.multiprocessing_pool():
                if model_test is not None:
                    logging.info('create test data set ...')
                    test_set = list(model_test.compiler.build_loom_inputs(test_iterator(data=data, children=children)))
                    logging.info('test data size: ' + str(len(test_set)))
                    if not train_iterator:
                        do_epoch(model_test, test_set, 0, train=False, emit=False)
                        return

                logging.info('create train data set ...')
                # data_train = list(train_iterator)
                train_set = model_train.compiler.build_loom_inputs(train_iterator(data=data, children=children))
                # logging.info('train data size: ' + str(len(data_train)))
                # dev_feed_dict = compiler.build_feed_dict(dev_trees)
                logging.info('training the model')
                test_p_rs = []
                test_p_rs_sorted = [0]
                step_train = sess.run(model_train.global_step)
                for epoch, shuffled in enumerate(td.epochs(train_set, FLAGS.epochs, shuffle=True), 1):

                    # train
                    if not FLAGS.early_stop_queue or len(test_p_rs) > 0:
                        step_train, _, _, _ = do_epoch(model_train, shuffled, epoch, new_model=FLAGS.data_single)

                    if model_test is not None:
                        # test
                        step_test, loss_test, sim_all, sim_all_gold = do_epoch(model_test, test_set, epoch,
                                                                               train=False, test_step=step_train,
                                                                               # apply_linreg=FLAGS.data_single
                                                                               )

                        # EARLY STOPPING ###############################################################################

                        # loss_test = round(loss_test, 6) #100000000
                        p_r = pearsonr(sim_all, sim_all_gold)[0]
                        p_r = round(p_r, 6)
                        p_r_dif = p_r - max(test_p_rs_sorted)
                        # stop, if different previous test losses are smaller than current loss. The amount of regarded
                        # previous values is set by FLAGS.early_stop_queue
                        if p_r not in test_p_rs:
                            test_p_rs.append(p_r)
                            test_p_rs_sorted = sorted(test_p_rs, reverse=True)
                        rank = test_p_rs_sorted.index(p_r)

                        logging.debug(
                            'pearson_r rank (of %i):\t%i\tdif: %f' % (len(test_p_rs), rank, round(p_r_dif, 6)))
                        if FLAGS.early_stop_queue and len(test_p_rs) > FLAGS.early_stop_queue and rank == len(
                                test_p_rs) - 1:  # min(test_p_rs) == p_r :
                            logging.info('last test pearsons_r: ' + str(test_p_rs))
                            break

                        if len(test_p_rs) > FLAGS.early_stop_queue:
                            if test_p_rs[0] == max(test_p_rs):
                                logging.debug('warning: remove highest value (%f)' % test_p_rs[0])
                            del test_p_rs[0]

                        if rank > len(test_p_rs) * 0.05:
                            # auto restore if no improvement on test data
                            if FLAGS.auto_restore:
                                supervisor.saver.restore(sess, tf.train.latest_checkpoint(logdir))
                        else:
                            # don't save after first epoch if FLAGS.early_stop_queue > 0
                            if len(test_p_rs) > 1 or not FLAGS.early_stop_queue:
                                supervisor.saver.save(sess, checkpoint_path(logdir, step_train))
                    else:
                        supervisor.saver.save(sess, checkpoint_path(logdir, step_train))


if __name__ == '__main__':
    tf.app.run()
