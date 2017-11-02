import ast
import csv
import json
import os
import pprint
import logging
import random
import sys
from scipy import spatial

import spacy
import tensorflow as tf
import pickle
import numpy as np

import constants
import corpus
import corpus_simtuple
import preprocessing
import lexicon as lex
import sequence_trees
import similarity_tree_tuple_pb2  # , sequence_node_sequence_pb2

tf.flags.DEFINE_string(
    'corpus_data_input_train',
    '/home/arne/devel/ML/data/corpora/DEBATE_CLUSTER/hasan_transformed_data_multi_clusters_post_level.tsv',
    'The path to the hasan corpus train data file.')
tf.flags.DEFINE_string(
    'corpus_data_output_dir',
    # 'data/corpora/sick',
    '/media/arne/WIN/Users/Arne/ML/data/corpora/debate_cluster',
    'The path to the output data files (samples, embedding vectors, mappings).')
tf.flags.DEFINE_string(
    'corpus_data_output_fn', 'HASAN',
    'Base filename of the output data files (samples, embedding vectors, mappings).')
# tf.flags.DEFINE_string(
#    'dict_filename', 'data/nlp/spacy/dict',
#    'The path to the output data files (samples, embedding vectors, mappings).')
tf.flags.DEFINE_integer(
    'corpus_size', -1,
    'How many samples to write. Use a negative dummy value to set no limit.')
tf.flags.DEFINE_string(
    'sentence_processor',
    'process_sentence3',
    'Which data types (features) are used to build the data sequence.')
tf.flags.DEFINE_string(
    'concat_mode',
    'sequence',
    #'aggregate',
    # constants.default_inner_concat_mode,
    'How to concatenate the trees returned for one sentence. '
    '"tree" -> use dependency parse tree'
    '"sequence" -> roots point to next root, '
    '"aggregate" -> roots point to an added, artificial token (AGGREGATOR) in the end of the token sequence'
    '(NOT ALLOWED for similarity scored tuples!) None -> do not concat at all')
tf.flags.DEFINE_string(
    'inner_concat_mode',
     'tree',
    #None,
    # constants.default_inner_concat_mode,
    'How to concatenate the trees returned for one token. '
    '"tree" -> use dependency parse tree'
    '"sequence" -> roots point to next root, '
    '"aggregate" -> roots point to an added, artificial token (AGGREGATOR) in the end of the token sequence'
    'None -> do not concat at all')
tf.flags.DEFINE_integer(
    'negative_samples', 0,
    'Count of negative samples per added positive.')
tf.flags.DEFINE_integer(
    'fold_count', 10,
    'How many folds to write.')
tf.flags.DEFINE_integer(
    'count_threshold', 2,
    'The minimum of token occurrences to keep the token in the dictionary.')
tf.flags.DEFINE_integer(
    'max_token_count', 500,
    'The minimum of token occurrences to keep the token in the dictionary.')

FLAGS = tf.flags.FLAGS

pp = pprint.PrettyPrinter(indent=4)

FIELDNAMES = ['debate', 'source_id', 'clusters', 'cluster_count', 'content']


def hasan_sentence_reader(filename):
    with open(filename, 'rb') as csvfile:
        reader = csv.DictReader(csvfile, fieldnames=FIELDNAMES, delimiter='\t')
        for row in reader:
            c = row['content'].decode('utf-8')
            if len(c.split()) < FLAGS.max_token_count:
                yield c


def hasan_cluster_reader(filename):
    with open(filename, 'rb') as csvfile:
        reader = csv.DictReader(csvfile, fieldnames=FIELDNAMES, delimiter='\t')
        for row in reader:
            c = row['content'].decode('utf-8')
            if len(c.split()) < FLAGS.max_token_count:
                yield ast.literal_eval(row['clusters'].decode('utf-8'))


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG, stream=sys.stdout)
    logging.info('load spacy ...')
    nlp = spacy.load('en')
    nlp.pipeline = [nlp.tagger, nlp.entity, nlp.parser]

    # vecs, mapping = corpus.create_or_read_dict(FLAGS.dict_filename, nlp.vocab)
    # corpus.make_parent_dir(FLAGS.dict_filename)
    vecs, types = lex.get_dict_from_vocab(nlp.vocab)  # corpus.create_or_read_dict(FLAGS.dict_filename, nlp.vocab)
    mapping = lex.mapping_from_list(types)

    sentence_processor = getattr(preprocessing, FLAGS.sentence_processor)
    out_dir = os.path.abspath(os.path.join(FLAGS.corpus_data_output_dir, sentence_processor.func_name))
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    out_path = os.path.join(out_dir, FLAGS.corpus_data_output_fn)

    assert FLAGS.concat_mode is not None and FLAGS.concat_mode != 'tree', \
        "concat_mode=None or concat_mode='tree' is NOT ALLOWED for similarity scored tuples! Use 'sequence' or 'aggregate'"
    out_path = out_path + '_CM' + FLAGS.concat_mode
    if FLAGS.inner_concat_mode is not None:
        out_path = out_path + '_ICM' + FLAGS.inner_concat_mode
    out_path = out_path + '_NEGSAMPLES' + str(FLAGS.negative_samples)

    data, parents, clusters, _ = corpus.parse_texts_clustered(filename=FLAGS.corpus_data_input_train,
                                                              reader=hasan_sentence_reader,
                                                              reader_clusters=hasan_cluster_reader,
                                                              sentence_processor=sentence_processor,
                                                              parser=nlp,
                                                              mapping=mapping,
                                                              concat_mode=FLAGS.concat_mode,
                                                              inner_concat_mode=FLAGS.inner_concat_mode)

    types = lex.revert_mapping_to_list(mapping)
    converter, vecs, types, new_counts, new_idx_unknown = lex.sort_and_cut_and_fill_dict(data, vecs, types,
                                                                                            count_threshold=FLAGS.count_threshold)
    data = corpus.convert_data(data, converter, len(types), new_idx_unknown)
    logging.info('save data, parents, scores, vecs and types to: ' + out_path + ' ...')
    data.dump(out_path + '.data')
    parents.dump(out_path + '.parent')
    with open(out_path + '.cluster', 'wb') as cluster_file:
        pickle.dump(clusters, cluster_file)
    # scores.dump(out_path + '.score')
    lex.write_dict(out_path, vecs=vecs, types=types)
    children, roots = sequence_trees.children_and_roots(parents)
    logging.info('the dataset contains ' + str(len(clusters)) + ' clustered texts')

    clusters_by_id = {None: []}
    for idx, c_ids in enumerate(clusters):
        if len(c_ids) == 0:
            clusters_by_id[None].append(idx)
        else:
            for c_id in c_ids:
                if c_id not in clusters_by_id:
                    clusters_by_id[c_id] = []
                clusters_by_id[c_id].append(idx)

    # debug
    # for c_id in clusters_by_id:
    #     print(str(c_id) + ': ' + str(len(clusters_by_id[c_id])))
    # debug end


    def get_jaccard(cluster_ids1, cluster_ids2):
        ids1_set = set(cluster_ids1)
        ids2_set = set(cluster_ids2)
        return float(len(ids1_set & ids2_set)) / float(len(ids1_set | ids2_set))


    sim_tuples = []
    # sim_positive_count = 0
    added_positive = np.zeros(shape=(len(clusters), len(clusters)), dtype=bool)
    added_negative = np.zeros(shape=(len(clusters), len(clusters)), dtype=bool)
    for idx, c_ids in enumerate(clusters):
        added = set()
        for c_id in c_ids:
            # add all with at least one same cluster
            for other_idx in clusters_by_id[c_id]:
                if other_idx not in added:
                    # calc similarity
                    sim = get_jaccard(c_ids, clusters[other_idx])
                    # check, if itself or the reverse was already added
                    if not added_positive[idx][other_idx] and not added_positive[other_idx][idx]:
                        sim_tuples.append((idx, other_idx, sim))
                        added_positive[idx][other_idx] = True

                    added.add(other_idx)
        # sim_positive_count += len(added)
        # add negative samples
        not_added = np.array(list(set(range(len(clusters))).difference(added)))
        # TODO: add (FLAGS.negative_samples * np.sum(added_positive[idx])) neg samples? or just FLAGS.negative_samples?
        neg_sample_ids = np.random.choice(not_added, FLAGS.negative_samples * np.sum(added_positive[idx]))
        for neg_id in neg_sample_ids:
            if not added_negative[idx][neg_id] and not added_negative[neg_id][idx]:
                sim_tuples.append((idx, neg_id, 0.0))
                added_negative[idx][neg_id] = True

    # sim_positive_count = np.sum(added_positive)
    logging.info('total positive sample count: ' + str(np.sum(added_positive)))
    logging.info('total negative sample count: ' + str(np.sum(added_negative)))
    logging.info('total data size: ' + str(len(sim_tuples)))
    logging.info('shuffle data ...')
    random.shuffle(sim_tuples)

    fold_size = len(sim_tuples) / FLAGS.fold_count
    for fold in range(FLAGS.fold_count):
        out_fn = out_path + '.train.' + str(fold)
        corpus_simtuple.write_sim_tuple_data(out_fn, sim_tuples[fold * fold_size:(fold + 1) * fold_size], data, children, roots)

