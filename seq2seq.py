import tensorflow as tf 
import numpy as np 
import sys
from random import randint
import datetime
from sklearn.utils import shuffle
import pickle
import os

#add <EOS> to response file
def createTrainingSentences(convFile,wList):
	conversationDictionary = np.load(convFile).item()
	print(len(conversationDictionary))
	max_message_length = 0
	max_response_length = 0
	message_text_id = []
	response_text_id = []

	for index,(key,value) in enumerate(conversationDictionary.items()):
		message_token_id = []
		response_token_id = []

		if len(key.split(" ")) > max_message_length:
			max_message_length = len(key.split(" "))
		if len(value.split(" ")) > max_response_length:
			max_response_length = len(value.split(" "))

		for i,token in enumerate(key.split(" ")):
			if (token != ""):
				try:
					message_token_id.append(wList.index(token))
				except ValueError:
					message_token_id.append(wList.index('<UNK>'))

		for i,token in enumerate(value.split(" ")):
			if (token != ""):
				try:
					response_token_id.append(wList.index(token))
				except ValueError:
					response_token_id.append(wList.index('<UNK>'))
		response_token_id.append(wList.index('<EOS>'))

		message_text_id.append(message_token_id)
		response_text_id.append(response_token_id)
	print("message :: %d , response :: %d",(len(message_text_id),len(response_text_id)))
	return max_message_length,max_response_length,message_text_id,response_text_id


def enc_dec_model_inputs():
	inputs = tf.placeholder(tf.int32, [None, None], name='input')
	targets = tf.placeholder(tf.int32, [None, None], name='targets') 
	
	target_sequence_length = tf.placeholder(tf.int32, [None], name='target_sequence_length')
	max_target_len = tf.reduce_max(target_sequence_length)	
	
	return inputs, targets, target_sequence_length, max_target_len


def hyperparam_inputs():
	lr_rate = tf.placeholder(tf.float32, name='lr_rate')
	keep_prob = tf.placeholder(tf.float32, name='keep_prob')
	
	return lr_rate, keep_prob

def process_decoder_input(target_data, wList, batch_size):
	"""
	Preprocess target data for encoding
	:return: Preprocessed target data
	"""
	# get '<GO>' id
	go_id = wList.index('<GO>')
	
	after_slice = tf.strided_slice(target_data, [0, 0], [batch_size, -1], [1, 1])
	after_concat = tf.concat( [tf.fill([batch_size, 1], go_id), after_slice], 1)
	
	return after_concat

def encoding_layer(rnn_inputs, rnn_size, num_layers, keep_prob, 
				   source_vocab_size, 
				   encoding_embedding_size):
	"""
	:return: tuple (RNN output, RNN state)
	"""
	embed = tf.contrib.layers.embed_sequence(rnn_inputs, 
											 vocab_size=source_vocab_size, 
											 embed_dim=encoding_embedding_size)
	
	stacked_cells = tf.contrib.rnn.MultiRNNCell([tf.contrib.rnn.DropoutWrapper(tf.contrib.rnn.LSTMCell(rnn_size), keep_prob) for _ in range(num_layers)])
	
	outputs, state = tf.nn.dynamic_rnn(stacked_cells, 
									   embed, 
									   dtype=tf.float32)
	return outputs, state

def decoding_layer_train(encoder_state, dec_cell, dec_embed_input, 
						 target_sequence_length, max_summary_length, 
						 output_layer, keep_prob):
	"""
	Create a training process in decoding layer 
	:return: BasicDecoderOutput containing training logits and sample_id
	"""
	dec_cell = tf.contrib.rnn.DropoutWrapper(dec_cell, 
											 output_keep_prob=keep_prob)
	
	# for only input layer
	helper = tf.contrib.seq2seq.TrainingHelper(dec_embed_input, 
											   target_sequence_length)
	
	decoder = tf.contrib.seq2seq.BasicDecoder(dec_cell, 
											  helper, 
											  encoder_state, 
											  output_layer)

	# unrolling the decoder layer
	outputs, _, _ = tf.contrib.seq2seq.dynamic_decode(decoder, 
													  impute_finished=True, 
													  maximum_iterations=max_summary_length)
	return outputs

def decoding_layer_infer(encoder_state, dec_cell, dec_embeddings, start_of_sequence_id,
						 end_of_sequence_id, max_target_sequence_length,
						 vocab_size, output_layer, batch_size, keep_prob):
	"""
	Create a inference process in decoding layer 
	:return: BasicDecoderOutput containing inference logits and sample_id
	"""
	dec_cell = tf.contrib.rnn.DropoutWrapper(dec_cell, 
											 output_keep_prob=keep_prob)
	
	helper = tf.contrib.seq2seq.GreedyEmbeddingHelper(dec_embeddings, 
													  tf.fill([batch_size], start_of_sequence_id), 
													  end_of_sequence_id)
	
	decoder = tf.contrib.seq2seq.BasicDecoder(dec_cell, 
											  helper, 
											  encoder_state, 
											  output_layer)
	
	outputs, _, _ = tf.contrib.seq2seq.dynamic_decode(decoder, 
													  impute_finished=True, 
													  maximum_iterations=max_target_sequence_length)
	return outputs

def decoding_layer(dec_input, encoder_state,
				   target_sequence_length, max_target_sequence_length,
				   rnn_size,
				   num_layers, target_vocab_to_int, target_vocab_size,
				   batch_size, keep_prob, decoding_embedding_size):
	"""
	Create decoding layer
	:return: Tuple of (Training BasicDecoderOutput, Inference BasicDecoderOutput)
	"""
	target_vocab_size = len(target_vocab_to_int)
	dec_embeddings = tf.Variable(tf.random_uniform([target_vocab_size, decoding_embedding_size]))
	dec_embed_input = tf.nn.embedding_lookup(dec_embeddings, dec_input)
	
	cells = tf.contrib.rnn.MultiRNNCell([tf.contrib.rnn.LSTMCell(rnn_size) for _ in range(num_layers)])
	
	with tf.variable_scope("decode"):
		output_layer = tf.layers.Dense(target_vocab_size)
		train_output = decoding_layer_train(encoder_state, 
											cells, 
											dec_embed_input, 
											target_sequence_length, 
											max_target_sequence_length, 
											output_layer, 
											keep_prob)

	with tf.variable_scope("decode", reuse=True):
		infer_output = decoding_layer_infer(encoder_state, 
											cells, 
											dec_embeddings, 
											target_vocab_to_int.index('<GO>'), 
											target_vocab_to_int.index('<EOS>'), 
											max_target_sequence_length, 
											target_vocab_size, 
											output_layer,
											batch_size,
											keep_prob)

	return (train_output, infer_output)

def seq2seq_model(input_data, target_data, keep_prob, batch_size,
				  target_sequence_length,
				  max_target_sentence_length,
				  source_vocab_size, target_vocab_size,
				  enc_embedding_size, dec_embedding_size,
				  rnn_size, num_layers, target_vocab_to_int):
	"""
	Build the Sequence-to-Sequence model
	:return: Tuple of (Training BasicDecoderOutput, Inference BasicDecoderOutput)
	"""
	enc_outputs, enc_states = encoding_layer(input_data, 
											 rnn_size, 
											 num_layers, 
											 keep_prob, 
											 source_vocab_size, 
											 enc_embedding_size)
	
	dec_input = process_decoder_input(target_data, 
									  target_vocab_to_int, 
									  batch_size)
	
	train_output, infer_output = decoding_layer(dec_input,
											   enc_states, 
											   target_sequence_length, 
											   max_target_sentence_length,
											   rnn_size,
											  num_layers,
											  target_vocab_to_int,
											  target_vocab_size,
											  batch_size,
											  keep_prob,
											  dec_embedding_size)
	
	return train_output, infer_output


def pad_sentence_batch(sentence_batch, pad_int):
	"""Pad sentences with <PAD> so that each sentence of a batch has the same length"""
	max_sentence = max([len(sentence) for sentence in sentence_batch])
	return [sentence + [pad_int] * (max_sentence - len(sentence)) for sentence in sentence_batch]


def get_batches(sources, targets, batch_size, source_pad_int, target_pad_int):
	"""Batch targets, sources, and the lengths of their sentences together"""
	# print(len(sources)//batch_size)
	for batch_i in range(0, len(sources)//batch_size):
		start_i = batch_i * batch_size
		

		# Slice the right amount for the batch
		sources_batch = sources[start_i:start_i + batch_size]
		targets_batch = targets[start_i:start_i + batch_size]
		# Pad
		pad_sources_batch = np.array(pad_sentence_batch(sources_batch, source_pad_int))
		pad_targets_batch = np.array(pad_sentence_batch(targets_batch, target_pad_int))

		# Need the lengths for the _lengths parameters
		pad_targets_lengths = []
		for target in pad_targets_batch:
			pad_targets_lengths.append(len(target))

		pad_source_lengths = []
		for source in pad_sources_batch:
			pad_source_lengths.append(len(source))

		yield pad_sources_batch, pad_targets_batch, pad_source_lengths, pad_targets_lengths

def create_test_sentences(testStrings,wList):
	"""Converts testStrings to integer ids with padding and all"""
	message_text_id = []
	for index,text in enumerate(testStrings):
		message_token_id = []
		for i,token in enumerate(text.split(" ")):
			message_token_id.append(wList.index(token))
		message_text_id.append(message_token_id)

	pad_test_batch = np.array(pad_sentence_batch(message_text_id, wordList.index('<PAD>')))
	pad_test_lengths = []
	for test in pad_test_batch:
		pad_test_lengths.append(len(test))

	return pad_test_batch,pad_test_lengths

def test_to_text(testStrings,wList):
	""" Converts testlogits to text """
	output = []
	for i,token in enumerate(testStrings):
		output_text = []
		for j,token_word in enumerate(token):
			output_text.append(wList[int(token_word)])
		output.append(output_text)
	return output
#Loading in all the data structures
with open("wordList.txt", "r") as fp:
	wordList = fp.read().split('\n')

vocabSize = len(wordList)

if (os.path.isfile('embeddingMatrix.npy')):
	wordVectors = np.load('embeddingMatrix.npy')
	wordVecDimensions = wordVectors.shape[1]
else:
	wordVecDimensions = 100

PADVector = np.zeros((1, wordVecDimensions), dtype='int32')
EOSVector = np.ones((1, wordVecDimensions), dtype='int32')
GOVector = np.ones((1, wordVecDimensions), dtype='int32')
save_path = "/mnt/m/Study/Chatbot/final.mdl"
if (os.path.isfile('embeddingMatrix.npy')): 
	wordVectors = np.concatenate((wordVectors,PADVector), axis=0)
	wordVectors = np.concatenate((wordVectors,EOSVector), axis=0)
	wordVectors = np.concatenate((wordVectors,GOVector), axis=0)

# Need to modify the word list as well
wordList.append('<PAD>')
wordList.append('<GO>')
wordList.append('<EOS>')
wordList.append('<UNK>')
vocabSize = vocabSize + 4

testStrings = ["hey whats up","god morning","hi","score entha","em chesthunav"]

display_step = 30

epochs = 1
batch_size = 128

rnn_size = 128
num_layers = 3

encoding_embedding_size = 100
decoding_embedding_size = 100

learning_rate = 0.001
keep_probability = 0.5

if(os.path.isfile('text_ids.p')):
	with open('text_ids.p',mode = 'rb') as in_file:
		(max_message_length,max_response_length), (message_text_id, response_text_id) = pickle.load(in_file)
else:
	max_message_length,max_response_length, message_text_id, response_text_id = createTrainingSentences('conversationData.npy', wordList)
	print("Dumping text_ids to file")
	#dump preprocess data
	pickle.dump(((max_message_length,max_response_length),(message_text_id,response_text_id)),open('text_ids.p','wb'))

train_graph = tf.Graph()
with train_graph.as_default():
	input_data, targets, target_sequence_length, max_target_sequence_length = enc_dec_model_inputs()
	lr, keep_prob = hyperparam_inputs()
	
	train_logits, inference_logits = seq2seq_model(input_data,
												   targets,
												   keep_prob,
												   batch_size,
												   target_sequence_length,
												   max_target_sequence_length,
												   len(message_text_id),
												   len(response_text_id),
												   encoding_embedding_size,
												   decoding_embedding_size,
												   rnn_size,
												   num_layers,
												   wordList)
	
	training_logits = tf.identity(train_logits.rnn_output, name='logits')
	inference_logits = tf.identity(inference_logits.sample_id, name='predictions')

	# https://www.tensorflow.org/api_docs/python/tf/sequence_mask
	# - Returns a mask tensor representing the first N positions of each cell.
	masks = tf.sequence_mask(target_sequence_length, max_target_sequence_length, dtype=tf.float32, name='masks')
	with tf.name_scope("optimization"):
		# Loss function - weighted softmax cross entropy
		cost = tf.contrib.seq2seq.sequence_loss(
			training_logits,
			targets,
			masks)

		# Optimizer
		optimizer = tf.train.AdamOptimizer(lr)

		# Gradient Clipping
		gradients = optimizer.compute_gradients(cost)
		capped_gradients = [(tf.clip_by_value(grad, -1., 1.), var) for grad, var in gradients if grad is not None]
		train_op = optimizer.apply_gradients(capped_gradients)


###TODO ::: Need to create accuracy and training process


def get_accuracy(target, logits):
	"""
	Calculate accuracy
	"""
	max_seq = max(target.shape[1], logits.shape[1])
	if max_seq - target.shape[1]:
		target = np.pad(
			target,
			[(0,0),(0,max_seq - target.shape[1])],
			'constant')
	if max_seq - logits.shape[1]:
		logits = np.pad(
			logits,
			[(0,0),(0,max_seq - logits.shape[1])],
			'constant')

	return np.mean(np.equal(target, logits))

# Split data to training and validation sets
train_source = message_text_id[batch_size:]
train_target = response_text_id[batch_size:]
valid_source = message_text_id[:batch_size]
valid_target = response_text_id[:batch_size]
print("message_length :: %d , response_length :: %d " ,(len(message_text_id),len(response_text_id)))


(valid_sources_batch, valid_targets_batch, valid_sources_lengths, valid_targets_lengths ) = next(get_batches(valid_source, valid_target,batch_size,wordList.index('<PAD>'),wordList.index('<PAD>'))) 
# print(get_batches(valid_source, valid_target,batch_size,wordList.index('<PAD>'),wordList.index('<PAD>')))

test_batch,test_lengths = create_test_sentences(testStrings,wordList)

with tf.Session(graph=train_graph) as sess:
	sess.run(tf.global_variables_initializer())

	for epoch_i in range(epochs):
		for batch_i, (source_batch, target_batch, sources_lengths, targets_lengths) in enumerate(
				get_batches(train_source, train_target, batch_size,wordList.index('<PAD>'),wordList.index('<PAD>'))):
			print('epoch :: {}, batch :: {} '.format(epoch_i,batch_i))
			_, loss = sess.run(
				[train_op, cost],
				{input_data: source_batch,
				 targets: target_batch,
				 lr: learning_rate,
				 target_sequence_length: targets_lengths,
				 keep_prob: keep_probability})


			if batch_i % display_step == 0 and batch_i > 0:
				batch_train_logits = sess.run(
					inference_logits,
					{input_data: source_batch,
					 target_sequence_length: targets_lengths,
					 keep_prob: 1.0})

				batch_valid_logits = sess.run(
					inference_logits,
					{input_data: valid_sources_batch,
					 target_sequence_length: valid_targets_lengths,
					 keep_prob: 1.0})
				#outputs for testStrings

				test_logits = sess.run(inference_logits,{input_data:test_batch , target_sequence_length : test_lengths, keep_prob: 1.0})
				print ('Messages :: {}, Responses :: {}'.format(testStrings,test_to_text(test_logits)))

				train_acc = get_accuracy(target_batch, batch_train_logits)
				valid_acc = get_accuracy(valid_targets_batch, batch_valid_logits)
				print('Epoch {:>3} Batch {:>4} - Train Accuracy: {:>6.4f}, Validation Accuracy: {:>6.4f}, Loss: {:>6.4f}'
					  .format(epoch_i, batch_i,  train_acc, valid_acc, loss))

	# Save Model
	saver = tf.train.Saver()
	saver.save(sess, save_path)
	print('Model Trained and Saved')