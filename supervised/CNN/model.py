import tensorflow as tf
import tensorflow.contrib.slim as slim
import pdb


def buildModel(x, y, keep_prob, config):
    x = tf.reshape(x, [-1, config["x_Dimension"], config["y_Dimension"], config["z_Dimension"], config["numChannels"]])
    conv1 = slim.batch_norm(slim.convolution(x, 50, [5,5,5], stride=[1,1,1]))
    conv2 = slim.batch_norm(slim.convolution(conv1, 50, [5,5,5], stride=[2,2,1]))
    conv3 = slim.batch_norm(slim.convolution(conv2, 50, [5,5,5], stride=[1,1,1]))
    conv4 = slim.batch_norm(slim.convolution(conv3, 50, [5,5,5], stride=[2,2,1]))
    # conv5 = slim.batch_norm(slim.convolution(conv3, 128, [3,3,3], stride=[2,2,1]))

    pred = tf.nn.dropout(slim.fully_connected(slim.flatten(conv4), config["n_Classes"], activation_fn=None), keep_prob)
    loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits=pred, labels=y))

    return tf.nn.softmax(pred), loss


def buildBaseModel(x, y, keep_prob, config):
    x = tf.reshape(x, [-1, config["x_Dimension"], config["y_Dimension"], config["z_Dimension"], config["numChannels"]])
    conv1 = slim.batch_norm(slim.convolution(x, config["neurons"][0], config["filter"], stride=[1,1,1]))
    conv2 = slim.batch_norm(slim.convolution(conv1, config["neurons"][1], config["filter"], stride=[2,2,2]))
    conv3 = slim.batch_norm(slim.convolution(conv2, config["neurons"][2], config["filter"], stride=[2,2,2]))
    conv4 = slim.batch_norm(slim.convolution(conv3, config["neurons"][3], config["filter"], stride=[2,2,2]))
    pred = tf.nn.dropout(slim.fully_connected(slim.flatten(conv4), config["n_Classes"], activation_fn=None), keep_prob)
    loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits=pred, labels=y))

    return tf.nn.softmax(pred), loss


def buildMultiNetworkModel(x, y, keep_prob, config):

    volumes = tf.split(x, config["numVolumes"], axis=4)

    denseLayers = []
    for v in volumes:
        conv1 = slim.batch_norm(slim.convolution(v, 50, [5,5,5], stride=[1,1,1]))
        conv2 = slim.batch_norm(slim.convolution(conv1, 50, [5,5,5], stride=[2,2,1]))
        conv3 = slim.batch_norm(slim.convolution(conv2, 50, [5,5,5], stride=[1,1,1]))
        conv4 = slim.batch_norm(slim.convolution(conv3, 50, [5,5,5], stride=[2,2,1]))
        fc = slim.fully_connected(slim.flatten(conv4), 1, activation_fn=None)
        denseLayers.append(fc)

    multiNetworkVector = tf.concat(denseLayers, axis=1)

    l1 = slim.fully_connected(multiNetworkVector, 25) # TODO: test with different activation_fn
    pred = tf.nn.dropout(slim.fully_connected(l1, config["n_Classes"], activation_fn=None), keep_prob)

    loss = tf.reduce_mean(tf.nn.softmax_cross_entropy_with_logits(logits=pred, labels=y))

    return tf.nn.softmax(pred), loss
