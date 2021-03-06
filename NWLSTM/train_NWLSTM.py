#! /usr/bin/env python
# -*- coding: utf-8 -*-
import sys, csv, itertools, operator, os, time, ast, datetime
import numpy as np
import theano
import theano.tensor as T
from utils import *
from NWLSTM_Net import NWLSTM_Net
from generate_from_NWLSTM import generate_sentence

# Data parameters
MAX_MINIBATCHES = False
MINIBATCH_SIZE = 100
SEQUENCE_LENGTH = 100 #SEQUENCE_LENGTH>=MINIBATCH_SIZE REQUIRED
BPTT_TRUNCATE = -1

# Stack parameters
WANT_STACK = False
STACK_HEIGHT = 15
NULL = 'NULL_TOKEN'
PUSH_CHAR = NULL
POP_CHAR = NULL

# Layer parameters
HIDDEN_DIM = 512
NUM_LAYERS = 2
ACTIVATION = 'tanh'

# Optimization parameters
OPTIMIZATION = 'RMSprop' # RMSprop or SGD
LEARNING_RATE = .00001
DROPOUT = .5
NEPOCH = 1000
EVAL_LOSS_AFTER = 100
L1_REGULARIZATION = 0.0001
L2_REGULARIZATION = 0.01

# Data source parameters
# DATAFILE = '../data/tmp.txt'
# LOSSFILE = '../data/tmp_loss.txt'
DATAFILE = '../data/simcity.txt'
LOSSFILE = '../data/simcity_loss.txt'
# DATAFILE = '../data/tex.txt'
# LOSSFILE = '../data/tex_loss.txt'
MODEL_FILE = 'saved_model_parameters/NWLSTM_savedparameters_7985.0__03-17___11-26-16.npz'

# Sampling parameters
SAMPLE = True
STARTING_STRING = '''static void
ListboxRedrawRange(listPtr, first, last)
    register Listbox *listPtr;      /* Information about widget. */
    int first;              /* Index of first element in list
                     * that needs to be redrawn. */
    int last;               /* Index of last element in list
                     * that needs to be redrawn.  May
                     * be less than first;
                     * these just bracket a range. */
{
    if ((listPtr->tkwin == NULL) || !Tk_IsMapped(listPtr->tkwin)
        || (listPtr->flags & REDRAW_PENDING)) {
    return;
    }
    Tk_DoWhenIdle(DisplayListbox, (ClientData) listPtr);
    listPtr->flags |= REDRAW_PENDING;
# }'''
# STARTING_STRING='''\\begin{problem}{0}
# THIS PROBLEM CONCERNS THE TABLE

# \\begin{table}[h] 
# \\begin{center}
# \\addtolength{\\tabcolsep}{1mm}
# \\renewcommand{\\arraystretch}{1.2}
# \\begin{tabular}{|c|r|r|r|r|r|}
# \hline
# \hline
# $t$    & \phantom{0}1.0 & \phantom{0}1.2 
#                    &  1.4 &  1.6 &  1.8 \\
# \hline
# $f(t)$ & 3.0 & 7.0 & 10.0 & 12.0 & 13.0 \\
# \hline
# \hline
# \end{tabular}
# \end{center}
# \end{table}

# \\vfill
# \end{problem}


# % problem with vertical table
# \\begin{problem}{0}
# THIS PROBLEM CONCERNS THE TABLE

# \\begin{table}[h] '''
SAMPLE_EVERY = 100
SAMPLE_LIMIT = 250
SAMPLE_NUMBER = 1
SOFTMAX_TEMPS = [.5]

# theano.config.optimizer = 'None'
# theano.config.compute_test_value = 'raise'
# theano.config.exception_verbosity = 'high'

# theano.config.profile='True'

theano.config.warn_float64 = 'warn'
theano.config.floatX = 'float32'

print "Training NWLSTM with parameters:\
    \nMax Number of Minibatches: {0}\
    \nMinibatch size: {4}\
    \nSequence Length: {5}\
    \nTruncate gradient: {10}\
    \nStack: {8}\
    \nHidden Layer: {1}\
    \nNumber of Layers: {2}\
    \nActivation: {12}\
    \nOptimization: {11}\
    \nLearning Rate: {3}\
    \nDropout: {9}\
    \nNumber of epochs: {6}\
    \nEvaluate loss every: {13}\
    \nL1 Regularization: {14}\
    \nL2 Regularization: {15}\
    \nLoading from model: {7}\
    \nSample: {16}, every {17} iterations\n".format(MAX_MINIBATCHES, HIDDEN_DIM, NUM_LAYERS, LEARNING_RATE, MINIBATCH_SIZE,
        SEQUENCE_LENGTH, NEPOCH, MODEL_FILE, WANT_STACK, DROPOUT, BPTT_TRUNCATE, OPTIMIZATION, ACTIVATION, EVAL_LOSS_AFTER,
        L1_REGULARIZATION,L2_REGULARIZATION,SAMPLE,SAMPLE_EVERY)

def one_hot(x, dimensions):
    tmp = np.zeros(dimensions)
    tmp[x] = 1
    return tmp.astype('float32')

def nullOutMinibatch(minibatch, desired_length, desired_size):
    while len(minibatch)<desired_size:
        null_sequence = [NULL]*desired_length
        minibatch.append(null_sequence)
    return minibatch

def parseFileForCharacterDicts(filename):
    with open(filename, 'rb') as f:
        unique_chars = set()
        while True:
            chunk = f.read(256)
            for c in chunk:
                unique_chars.add(c)
            if not chunk: break

    code_to_char_dict = dict([(i,c) for i,c in enumerate(sorted(unique_chars))])
    char_to_code_dict = dict([(code_to_char_dict[k],k) for k in code_to_char_dict])

    ALPHABET_LENGTH = len(code_to_char_dict.keys()) + 1

    char_to_code_dict[NULL] = ALPHABET_LENGTH-1
    code_to_char_dict[ALPHABET_LENGTH-1] = NULL

    #ALPHABET_LENGTH+=1 #dicts are zero-indexed, but we want to create vectors of size one greater

    return char_to_code_dict, code_to_char_dict, ALPHABET_LENGTH

def readFile(filename, char_to_code_dict):

    with open(filename) as f:
        filestring = f.read()

    np_data = np.zeros((len(filestring), len(char_to_code_dict))).astype('float32')

    c_index=0
    for c in filestring:
        np_data[c_index, char_to_code_dict[c]] = 1
        c_index+=1


    minibatches_yielded = 0
    startend_positions = [(start,start+SEQUENCE_LENGTH) for start in xrange(MINIBATCH_SIZE)]

    end_file = False
    while True:
        x_s = []
        y_s = []
        for start,end in startend_positions:
            if (end+1)>=np_data.shape[0]:
                end_file=True
                break

            x = np_data[start:end,:]
            y = np_data[start+1:end+1,:]
            x_s.append(x)
            y_s.append(y)

        if end_file: break

        x_s = np.stack(x_s, axis=2)
        y_s = np.stack(y_s, axis=2)

        yield x_s,y_s

        minibatches_yielded+=1
        if MAX_MINIBATCHES and minibatches_yielded>=MAX_MINIBATCHES: break

        startend_positions = [(x+MINIBATCH_SIZE,y+MINIBATCH_SIZE) for x,y in startend_positions]

def readFileWithUnmatchedLefts(filename, dictsFile=None, outputDictsToFile=None):
    with open(filename, 'rb') as f:
        
        
        minibatches_yielded = 0
        current_minibatch = []
        current_sequence = [NULL]*(SEQUENCE_LENGTH-1)

        unmatched_pushes = []
        popped_buffers = []
        while True:
            c = f.read(1)
            if not c:
                break

            if c==PUSH_CHAR:
                current_sequence.append(c)
                push_buffer = current_sequence[-CONTEXT_TO_PUSH:]
                push_buffer.append(NULL)
                push_buffer = [char if char!=POP_CHAR else NULL for char in push_buffer]
                push_buffer = [SEQUENCE_LENGTH+1,push_buffer]
                unmatched_pushes.append( push_buffer )
                #print "\nPUSH BUFFER: {0}\n".format(push_buffer)
            elif c==POP_CHAR:
                pop_buffer = unmatched_pushes.pop()
                pop_buffer[0] = SEQUENCE_LENGTH+1
                popped_buffers.append(pop_buffer)
                #print "\nPOP BUFFER: {0}\n".format(pop_buffer)
                current_sequence.append(c)
            else:
                current_sequence.append(c)

            unmatched_pushes = [[max(0,counter-1), pushed] for counter,pushed in unmatched_pushes]
            popped_buffers = [[max(0,counter-1), pushed] for counter,pushed in popped_buffers]
            popped_buffers = filter(lambda x: x[0]!=0, popped_buffers)


            if len(current_sequence)>=SEQUENCE_LENGTH:
                prepended_mb = []
                    # for stack_item in unmatched_pushes:
                    #     if stack_item[0]==0:
                    #         prepended_mb.extend(stack_item[1])
                for stack_item in popped_buffers:
                    if stack_item[0]!=0:
                        prepended_mb.extend(stack_item[1])
                prepended_mb.extend(current_sequence)
                #print "".join(prepended_mb).replace("\t","<").replace("\r"," ").replace("\n",">")
                
                # if minibatch up to this point has a different dimension, null out and then yield it,
                # and start a new one for this sequence
                if len(current_minibatch)>0 and not len(current_minibatch[0])==len(prepended_mb):
                    current_minibatch = nullOutMinibatch(current_minibatch, len(current_minibatch[0]), MINIBATCH_SIZE)
                    #print ["".join(p).replace("\t","<").replace("\r"," ").replace("\n",">") for p in current_minibatch], [len(p) for p in current_minibatch]# yield it
                    yield current_minibatch
                    current_minibatch = []

                current_minibatch.append(prepended_mb)
                #current_minibatch.append(current_sequence) #add this sequence to current minibatch
                current_sequence = current_sequence[1:]
                
                if len(current_minibatch)>=MINIBATCH_SIZE: #next sequence starts a new minibatch
                    #print ["".join(p).replace("\t","<").replace("\r"," ").replace("\n",">") for p in current_minibatch], [len(p) for p in current_minibatch]
                    yield current_minibatch
                   
                    minibatches_yielded+=1
                    if MAX_MINIBATCHES and minibatches_yielded>=MAX_MINIBATCHES:
                        break
                    
                    current_minibatch = []
                    continue

def calculateLoss(filename, model, counter, epoch):
    with open(filename) as f:
        seq = f.read()
        minibatch = [seq]*MINIBATCH_SIZE

    loss_x = np.dstack([np.asarray([one_hot(model.char_to_code_dict[c], model.word_dim) for c in seq[:-1]]) for seq in minibatch])
    loss_y = np.dstack([np.asarray([one_hot(model.char_to_code_dict[c], model.word_dim) for c in seq[1:]]) for seq in minibatch])

    softmax_temp = 1
    h_prev = np.zeros((NUM_LAYERS,HIDDEN_DIM,MINIBATCH_SIZE)).astype('float32')
    c_prev = np.zeros((NUM_LAYERS,HIDDEN_DIM,MINIBATCH_SIZE)).astype('float32')
    stack_prev = np.zeros((NUM_LAYERS,MINIBATCH_SIZE,STACK_HEIGHT,HIDDEN_DIM)).astype('float32')
    ptrs_to_top_prev = np.zeros((NUM_LAYERS,MINIBATCH_SIZE,STACK_HEIGHT,HIDDEN_DIM)).astype('float32')
    ptrs_to_top_prev[:,:,0,:] = 1

    if not WANT_STACK:
        loss, l1_loss, l2_loss = model.loss_for_minibatch(loss_x, loss_y, h_prev, c_prev, softmax_temp)
    else:
        loss, l1_loss, l2_loss = model.loss_for_minibatch_stack(loss_x, loss_y, h_prev, c_prev, stack_prev, ptrs_to_top_prev, softmax_temp)

    loss_per_char = loss / (MINIBATCH_SIZE * len(seq))

    dt = datetime.datetime.now().strftime("%m-%d___%H-%M-%S")
    print "{0}: Loss after examples={1}, epoch={2}:  {3:.15f}    {4:.0f}    {5:.0f}".format(dt, counter, epoch, loss_per_char*MINIBATCH_SIZE*SEQUENCE_LENGTH, l1_loss*L1_REGULARIZATION, l2_loss*L2_REGULARIZATION)
    save_model_parameters_lstm("saved_model_parameters/NWLSTM_savedparameters_{0:.1f}__{1}.npz".format(loss_per_char*MINIBATCH_SIZE*SEQUENCE_LENGTH, dt), model)


def main():
    print "Parsing for set of characters: {0}\n".format(DATAFILE)
    char_to_code_dict, code_to_char_dict, ALPHABET_LENGTH = parseFileForCharacterDicts(DATAFILE)
    print "char_to_code_dict: {0}\ncode_to_char_dict: {1}\n".format(char_to_code_dict, code_to_char_dict)

    print "Compiling model..."
    if MODEL_FILE != None:
        model = load_model_parameters_lstm(MODEL_FILE)
    else:
        push_vec = one_hot(char_to_code_dict[PUSH_CHAR], ALPHABET_LENGTH).reshape((ALPHABET_LENGTH,1))
        pop_vec = one_hot(char_to_code_dict[POP_CHAR], ALPHABET_LENGTH).reshape((ALPHABET_LENGTH,1))
        null_vec = one_hot(char_to_code_dict[NULL], ALPHABET_LENGTH).reshape((ALPHABET_LENGTH,1))
        t1 = time.time()
        model = NWLSTM_Net(word_dim=ALPHABET_LENGTH, hidden_dim=HIDDEN_DIM, minibatch_dim=MINIBATCH_SIZE, bptt_truncate=BPTT_TRUNCATE,
                           num_layers=NUM_LAYERS, optimization=OPTIMIZATION, activation=ACTIVATION, want_stack=WANT_STACK,
                           stack_height=STACK_HEIGHT, push_vec=push_vec, pop_vec=pop_vec, null_vec=null_vec, dropout=DROPOUT,
                           l1_rate=L1_REGULARIZATION, l2_rate=L2_REGULARIZATION)
        t2 = time.time()
        model.char_to_code_dict = char_to_code_dict
        model.code_to_char_dict = code_to_char_dict
        print "Finished! Compiling model took: {0:.0f} seconds\n".format(t2 - t1)


    losses = []
    counter = 0
    softmax_temp = 1
    for epoch in xrange(NEPOCH):
        h_prev = np.zeros((NUM_LAYERS,HIDDEN_DIM,MINIBATCH_SIZE)).astype('float32')
        c_prev = np.zeros((NUM_LAYERS,HIDDEN_DIM,MINIBATCH_SIZE)).astype('float32')
        stack_prev = np.zeros((NUM_LAYERS,MINIBATCH_SIZE,STACK_HEIGHT,HIDDEN_DIM)).astype('float32')
        ptrs_to_top_prev = np.zeros((NUM_LAYERS,MINIBATCH_SIZE,STACK_HEIGHT,HIDDEN_DIM)).astype('float32')
        ptrs_to_top_prev[:,:,0,:] = 1


        # for minibatch in readFile2(DATAFILE):
        for x,y in readFile(DATAFILE, char_to_code_dict):
            
            # x = np.dstack([np.asarray([one_hot(char_to_code_dict[c], ALPHABET_LENGTH) for c in seq[:-1]]) for seq in minibatch])
            # y = np.dstack([np.asarray([one_hot(char_to_code_dict[c], ALPHABET_LENGTH) for c in seq[1:]]) for seq in minibatch])


            if counter%EVAL_LOSS_AFTER==0:
                if counter==0: print "Dims of one minibatch: {0}".format(x.shape)
                t1 = time.time()

                if not WANT_STACK:
                    h_prev,c_prev = model.train_model(x, y, h_prev, c_prev, LEARNING_RATE, softmax_temp)
                else:
                    h_prev,c_prev,stack_prev,ptrs_to_top_prev = model.train_model_stack(x, y, h_prev, c_prev, 
                        stack_prev, ptrs_to_top_prev, LEARNING_RATE, softmax_temp)

                t2 = time.time()
                if counter%(EVAL_LOSS_AFTER*10)==0: print "One SGD step took: {0:.2f} milliseconds".format((t2 - t1) * 1000.)


                # if not WANT_STACK:
                #     loss, l1_loss, l2_loss = model.loss_for_minibatch(x, y, h_prev, c_prev, softmax_temp)
                # else:
                #     loss, l1_loss, l2_loss = model.loss_for_minibatch_stack(x, y, h_prev, c_prev, stack_prev, ptrs_to_top_prev, softmax_temp)

                calculateLoss(LOSSFILE, model, counter, epoch)
                # losses.append((epoch, loss))
                # dt = datetime.datetime.now().strftime("%m-%d___%H-%M-%S")
                # print "{0}: Loss after examples={1}, epoch={2}:  {3:.0f}    {4:.0f}    {5:.0f}".format(dt, counter, epoch, loss, l1_loss, l2_loss)
                # save_model_parameters_lstm("saved_model_parameters/NWLSTM_savedparameters_{0:.1f}__{1}.npz".format(loss, dt), model)

            else:
                if not WANT_STACK:
                    h_prev,c_prev = model.train_model(x, y, h_prev, c_prev, LEARNING_RATE, softmax_temp)
                else:
                    h_prev,c_prev,stack_prev,ptrs_to_top_prev = model.train_model_stack(x, y, h_prev, c_prev, 
                        stack_prev, ptrs_to_top_prev, LEARNING_RATE, softmax_temp)


            if SAMPLE and (counter!=0) and counter%SAMPLE_EVERY==0:
                for softmax_temp in SOFTMAX_TEMPS:
                    print "\nSampling sentence with softmax {0}".format(softmax_temp)
                    for _ in xrange(SAMPLE_NUMBER):
                        sent = generate_sentence(model, sample_limit=SAMPLE_LIMIT, softmax_temp=softmax_temp, starting_string=STARTING_STRING)
                        print "".join(sent)
                print

            counter+=1
            


    print "{0}: Loss after {1} examples, {2} epochs: {3:.1f}".format(dt, counter, epoch, loss)
    save_model_parameters_lstm("saved_model_parameters/NWLSTM_savedparameters_{0:.1f}__{1}.npz".format(loss, dt), model)          



if __name__=="__main__":
    main()