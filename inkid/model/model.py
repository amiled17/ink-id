"""
Functions for building the tf model.
"""
from functools import partial

import numpy as np
import tensorflow as tf
import torch

import inkid.ops
import inkid.metrics


class EvalCheckpointSaverListener(tf.estimator.CheckpointSaverListener):
    """Run some logic every time a checkpoint is saved.

    This is a bit of a Trojan horse that allows us to run validations,
    predictions, or arbitrary logic in the middle of a training
    run. An instance of this class is passed to the estimator when
    .train() is called. We also define in the RunConfig of the
    estimator how often we want it to save a checkpoint. So it will
    save a checkpoint that often, and then the after_save() method
    below is called. By passing the estimator itself to this class
    when it is initialized, we can call .evaluate() or .predict() on
    the estimator from here. Once done, the training process will
    continue unaware that any of this happened.

    https://stackoverflow.com/a/47043377

    """

    def __init__(self, estimator, val_input_fn, predict_input_fn,
                 validate_every_n_checkpoints,
                 predict_every_n_checkpoints, region_set,
                 predictions_dir, label_type):
        """Initialize the listener.

        Notably we pass the estimator itself to this class so that we
        can use it later.

        """
        self._estimator = estimator
        self._val_input_fn = val_input_fn
        self._predict_input_fn = predict_input_fn
        self._validate_every_n_checkpoints = validate_every_n_checkpoints
        self._predict_every_n_checkpoints = predict_every_n_checkpoints
        self._region_set = region_set
        self._predictions_dir = predictions_dir
        self._total_checkpoints = 0
        self._best_auc = 0
        self._label_type = label_type

    def after_save(self, session, global_step):
        """Run our custom logic after the estimator saves a checkpoint."""
        self._total_checkpoints += 1

        if self._label_type == 'ink_classes':
            best_auc = False
            if self._total_checkpoints % self._validate_every_n_checkpoints == 0:
                val_results = self._estimator.evaluate(self._val_input_fn)
                if val_results['area_under_roc_curve'] > self._best_auc:
                    best_auc = True
                    self._best_auc = val_results['area_under_roc_curve']

            if self._total_checkpoints % self._predict_every_n_checkpoints == 0:
                predictions = self._estimator.predict(
                    self._predict_input_fn,
                    predict_keys=[
                        'region_id',
                        'ppm_xy',
                        'probabilities',
                    ],
                )
                for prediction in predictions:
                    self._region_set.reconstruct_predicted_ink_classes(
                        np.array([prediction['region_id']]),
                        np.array([prediction['probabilities']]),
                        np.array([prediction['ppm_xy']]),
                    )
                if best_auc:
                    self._region_set.save_predictions(
                        self._predictions_dir,
                        str(global_step) + '_best_auc'
                    )
                else:
                    self._region_set.save_predictions(self._predictions_dir, global_step)
                self._region_set.reset_predictions()

        elif self._label_type == 'rgb_values':
            if self._total_checkpoints % self._predict_every_n_checkpoints == 0:
                predictions = self._estimator.predict(
                    self._predict_input_fn,
                    predict_keys=[
                        'region_id',
                        'ppm_xy',
                        'rgb',
                    ],
                )
                for prediction in predictions:
                    self._region_set.reconstruct_predicted_rgb(
                        np.array([prediction['region_id']]),
                        np.array([prediction['rgb']]),
                        np.array([prediction['ppm_xy']]),
                    )
                self._region_set.save_predictions(self._predictions_dir, global_step)
                self._region_set.reset_predictions()


class Subvolume3DcnnModel(torch.nn.Module):
    def __init__(self, drop_rate, subvolume_shape, pad_to_shape,
                 batch_norm_momentum, no_batch_norm, filters, output_neurons):
        super().__init__()

        self._batch_norm = not no_batch_norm

        # TODO padding math for 'same' (all layers)
        # TODO add activations below
        # TODO init https://pytorch.org/docs/stable/nn.html#torch.nn.Module.apply, kernel glorotuniform and bias zeros
        # TODO try leaky ReLU
        # TODO should dropout be elsewhere?
        # TODO look up actual 3D architectures commonly used and try that
        # TODO some way to indicate to batch norm and dropout if we are training
        # TODO remove all old code across files
        # TODO add AUC metric

        self.conv1 = torch.nn.Conv3d(in_channels=1, out_channels=filters[0], kernel_size=3, stride=1, padding=1)
        self.batch_norm1 = torch.nn.BatchNorm3d(num_features=filters[0], momentum=batch_norm_momentum)

        self.conv2 = torch.nn.Conv3d(in_channels=filters[0], out_channels=filters[1], kernel_size=3, stride=2, padding=1)
        self.batch_norm2 = torch.nn.BatchNorm3d(num_features=filters[1], momentum=batch_norm_momentum)

        self.conv3 = torch.nn.Conv3d(in_channels=filters[1], out_channels=filters[2], kernel_size=3, stride=2, padding=1)
        self.batch_norm3 = torch.nn.BatchNorm3d(num_features=filters[2], momentum=batch_norm_momentum)

        self.conv4 = torch.nn.Conv3d(in_channels=filters[2], out_channels=filters[3], kernel_size=3, stride=2, padding=1)
        self.batch_norm4 = torch.nn.BatchNorm3d(num_features=filters[3], momentum=batch_norm_momentum)

        self.fc = torch.nn.Linear(filters[3] * 216, output_neurons)  # TODO change this input size based on padding
        self.dropout = torch.nn.Dropout(p=drop_rate)

        self.relu = torch.nn.ReLU()
        self.flatten = torch.nn.Flatten()

    def forward(self, x):
        y = self.conv1(x)
        y = self.relu(y)
        if self._batch_norm:
            y = self.batch_norm1(y)
        y = self.conv2(y)
        y = self.relu(y)
        if self._batch_norm:
            y = self.batch_norm2(y)
        y = self.conv3(y)
        y = self.relu(y)
        if self._batch_norm:
            y = self.batch_norm3(y)
        y = self.conv4(y)
        y = self.relu(y)
        if self._batch_norm:
            y = self.batch_norm4(y)
        y = self.flatten(y)
        y = self.fc(y)
        y = self.dropout(y)

        return y


# def ink_classes_model_fn(features, labels, mode, params):
#     if mode == tf.estimator.ModeKeys.PREDICT:
#         logits = model(inputs, training=False)
#         # Here we specify all of the possible outputs from calling
#         # .predict(), which returns a dictionary with these keys for
#         # each prediction. So by passing predict_keys to .predict(),
#         # we can select some of these and not return the others.
#         predictions = {
#             'region_id': features['RegionID'],
#             'ppm_xy': features['PPM_XY'],
#             'class': tf.argmax(logits, axis=1),
#             'probabilities': tf.nn.softmax(logits),
#             'inputs': inputs,
#         }
#         return tf.estimator.EstimatorSpec(
#             mode=tf.estimator.ModeKeys.PREDICT,
#             predictions=predictions,
#         )
#
#     if mode == tf.estimator.ModeKeys.TRAIN:
#         if params['adagrad_optimizer']:
#             if params['decay_steps'] and params['decay_rate']:
#                 start_learning_rate = params['learning_rate']
#                 global_step = tf.compat.v1.train.get_global_step()
#                 learning_rate = tf.compat.v1.train.exponential_decay(start_learning_rate,
#                                                                      global_step, params['decay_steps'],
#                                                                      params['decay_rate'])
#                 optimizer = tf.compat.v1.train.AdagradOptimizer(learning_rate)
#             else:
#                 optimizer = tf.compat.v1.train.AdagradOptimizer(learning_rate=params['learning_rate'])
#         else:
#             if params['decay_steps'] and params['decay_rate']:
#                 start_learning_rate = params['learning_rate']
#                 global_step = tf.compat.v1.train.get_global_step()
#                 learning_rate = tf.compat.v1.train.exponential_decay(start_learning_rate,
#                                                                      global_step, params['decay_steps'],
#                                                                      params['decay_rate'])
#                 optimizer = tf.compat.v1.train.AdamOptimizer(learning_rate)
#             else:
#                 optimizer = tf.compat.v1.train.AdamOptimizer(learning_rate=params['learning_rate'])
#
#         logits = model(inputs, training=True)
#         loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(
#             labels=labels, logits=logits))
#
#         epsilon = 1e-5
#         predicted = tf.argmax(logits, 1)
#         actual = tf.argmax(labels, 1)
#         true_positives = tf.math.count_nonzero(predicted * actual, dtype=tf.float32)
#         true_negatives = tf.math.count_nonzero((predicted - 1) * (actual - 1), dtype=tf.float32)
#         false_positives = tf.math.count_nonzero(predicted * (actual - 1), dtype=tf.float32)
#         false_negatives = tf.math.count_nonzero((predicted - 1) * actual, dtype=tf.float32)
#         positives = true_positives + false_positives
#         negatives = true_negatives + false_negatives
#         accuracy = tf.divide(
#             true_positives + true_negatives,
#             true_positives + true_negatives + false_positives + false_negatives
#         )
#         precision = tf.divide(
#             true_positives,
#             true_positives + false_positives + epsilon
#         )
#         recall = tf.divide(
#             true_positives,
#             true_positives + false_negatives + epsilon
#         )
#         # https://en.wikipedia.org/wiki/F1_score
#         fbeta_weight = params['fbeta_weight']
#         fbeta_squared = tf.constant(fbeta_weight ** 2.0)
#         fbeta = (1 + fbeta_squared) * tf.divide(
#             (precision * recall),
#             (fbeta_squared * precision) + recall + epsilon
#         )
#
#         tf.identity(true_positives, name='train_true_positives')
#         tf.identity(true_negatives, name='train_true_negatives')
#         tf.identity(false_positives, name='train_false_positives')
#         tf.identity(false_negatives, name='train_false_negatives')
#         tf.identity(positives, name='train_positives')
#         tf.identity(negatives, name='train_negatives')
#         tf.identity(accuracy, name='train_accuracy')
#         tf.identity(precision, name='train_precision')
#         tf.identity(recall, name='train_recall')
#         tf.identity(fbeta, name='train_fbeta_score')
#
#         tf.summary.scalar('train_true_positives', true_positives)
#         tf.summary.scalar('train_true_negatives', true_negatives)
#         tf.summary.scalar('train_false_positives', false_positives)
#         tf.summary.scalar('train_false_negatives', false_negatives)
#         tf.summary.scalar('train_positives', positives)
#         tf.summary.scalar('train_negatives', negatives)
#         tf.summary.scalar('train_accuracy', accuracy)
#         tf.summary.scalar('train_precision', precision)
#         tf.summary.scalar('train_recall', recall)
#         tf.summary.scalar('train_fbeta_score', fbeta)
#
#         # These three lines are very important despite being a little
#         # opaque. Without them, batch normalization does not really
#         # work at all, and the model will appear to train successfully
#         # but this will not transfer to any validation or prediction
#         # runs.
#         # https://github.com/tensorflow/tensorflow/issues/16455
#         # https://www.tensorflow.org/api_docs/python/tf/layers/batch_normalization
#         update_ops = tf.compat.v1.get_collection(tf.compat.v1.GraphKeys.UPDATE_OPS)
#         with tf.control_dependencies(update_ops):
#             train_op = optimizer.minimize(loss, global_step=tf.compat.v1.train.get_global_step())
#
#         return tf.estimator.EstimatorSpec(
#             mode=tf.estimator.ModeKeys.TRAIN,
#             loss=loss,
#             train_op=train_op
#         )
#
#     if mode == tf.estimator.ModeKeys.EVAL:
#         logits = model(inputs, training=False)
#         loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(
#             labels=labels, logits=logits))
#
#         return tf.estimator.EstimatorSpec(
#             mode=tf.estimator.ModeKeys.EVAL,
#             loss=loss,
#             eval_metric_ops={
#                 'accuracy': tf.compat.v1.metrics.accuracy(
#                     labels=tf.argmax(labels, 1),
#                     predictions=tf.argmax(logits, 1)
#                 ),
#                 'precision': tf.compat.v1.metrics.precision(
#                     labels=tf.argmax(labels, 1),
#                     predictions=tf.argmax(logits, 1)
#                 ),
#                 'recall': tf.compat.v1.metrics.recall(
#                     labels=tf.argmax(labels, 1),
#                     predictions=tf.argmax(logits, 1)
#                 ),
#                 'fbeta_score': inkid.metrics.fbeta_score(
#                     labels=tf.argmax(labels, 1),
#                     predictions=tf.argmax(logits, 1),
#                     beta=params['fbeta_weight']
#                 ),
#                 'total_positives': inkid.metrics.total_positives(
#                     labels=tf.argmax(labels, 1),
#                     predictions=tf.argmax(logits, 1)
#                 ),
#                 'total_negatives': inkid.metrics.total_negatives(
#                     labels=tf.argmax(labels, 1),
#                     predictions=tf.argmax(logits, 1)
#                 ),
#                 'area_under_roc_curve': tf.compat.v1.metrics.auc(
#                     labels=tf.argmax(labels, 1),
#                     predictions=tf.nn.softmax(logits)[:, 1],
#                 ),
#             })


# def rgb_values_model_fn(features, labels, mode, params):
#     output_neurons = 3
#
#     if params['feature_type'] == 'voxel_vector_1dcnn':
#         model = VoxelVector1dcnnModel(
#             params['drop_rate'],
#             params['length_in_each_direction'],
#             params['batch_norm_momentum'],
#             params['filters'],
#             output_neurons,
#         )
#     elif params['feature_type'] == 'subvolume_3dcnn':
#         model = Subvolume3dcnnModel(
#             params['drop_rate'],
#             params['subvolume_shape'],
#             params['pad_to_shape'],
#             params['batch_norm_momentum'],
#             params['no_batch_norm'],
#             params['filters'],
#             output_neurons,
#         )
#     elif params['feature_type'] == 'descriptive_statistics':
#         model = DescriptiveStatisticsModel(
#             # Create a dummy array to see how many descriptive
#             # statistics there will be
#             len(inkid.ops.get_descriptive_statistics(np.array([0, 1, 2]))),
#             output_neurons,
#         )
#     else:
#         raise ValueError('Feature type {} was not recognized.'.format(params['feature_type']))
#
#     inputs = features['Input']
#
#     if mode == tf.estimator.ModeKeys.PREDICT:
#         logits = model(inputs, training=False)
#
#         predictions = {
#             'region_id': features['RegionID'],
#             'ppm_xy': features['PPM_XY'],
#             'rgb': logits,
#             'inputs': inputs,
#         }
#         return tf.estimator.EstimatorSpec(
#             mode=tf.estimator.ModeKeys.PREDICT,
#             predictions=predictions,
#         )
#
#     if mode == tf.estimator.ModeKeys.TRAIN:
#         if params['adagrad_optimizer']:
#             if params['decay_steps'] and params['decay_rate']:
#                 start_learning_rate = params['learning_rate']
#                 global_step = tf.train.get_global_step()
#                 learning_rate = tf.train.exponential_decay(start_learning_rate,
#                                                            global_step, params['decay_steps'], params['decay_rate'])
#                 optimizer = tf.train.AdagradOptimizer(learning_rate)
#             else:
#                 optimizer = tf.train.AdagradOptimizer(learning_rate=params['learning_rate'])
#         else:
#             if params['decay_steps'] and params['decay_rate']:
#                 start_learning_rate = params['learning_rate']
#                 global_step = tf.train.get_global_step()
#                 learning_rate = tf.train.exponential_decay(start_learning_rate,
#                                                            global_step, params['decay_steps'], params['decay_rate'])
#                 optimizer = tf.train.AdamOptimizer(learning_rate)
#             else:
#                 optimizer = tf.train.AdamOptimizer(learning_rate=params['learning_rate'])
#
#         logits = model(inputs, training=True)
#         loss = tf.losses.huber_loss(labels, logits)
#
#         update_ops = tf.compat.v1.get_collection(tf.compat.v1.GraphKeys.UPDATE_OPS)
#         with tf.control_dependencies(update_ops):
#             train_op = optimizer.minimize(loss, global_step=tf.train.get_global_step())
#
#         return tf.estimator.EstimatorSpec(
#             mode=tf.estimator.ModeKeys.TRAIN,
#             loss=loss,
#             train_op=train_op
#         )
#
#     if mode == tf.estimator.ModeKeys.EVAL:
#         logits = model(inputs, training=False)
#         loss = tf.losses.huber_loss(labels, logits)
#
#         return tf.estimator.EstimatorSpec(
#             mode=tf.estimator.ModeKeys.EVAL,
#             loss=loss,
#         )
