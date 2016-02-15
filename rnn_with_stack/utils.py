import numpy as np
import sys
from stack_rnn_theano import StackRNNTheano

def softmax(x):
    xt = np.exp(x - np.max(x))
    return xt / np.sum(xt)

def save_model_parameters_theano(outfile, model):
    U, V, W = model.U.get_value(), model.V.get_value(), model.W.get_value()
    np.savez(outfile, U=U, V=V, W=W)
    print "Saved model parameters to %s." % outfile
   
def load_model_parameters_theano(path, model):
    npzfile = np.load(path)
    U, V, W = npzfile["U"], npzfile["V"], npzfile["W"]
    model.hidden_dim = U.shape[0]
    model.word_dim = U.shape[1]
    model.U.set_value(U)
    model.V.set_value(V)
    model.W.set_value(W)
    print "Loaded model parameters from %s. hidden_dim=%d word_dim=%d" % (path, U.shape[0], U.shape[1])
    
def save_model_parameters_stackrnn(outfile, model):
    np.savez(outfile,
        W_hx=model.W_hx.get_value(),
        W_yh=model.W_yh.get_value(),
        W_hh=model.W_hh.get_value())
    print "Saved model parameters to %s." % outfile

def load_model_parameters_stackrnn(path, char_to_code_dict):
    npzfile = np.load(path)
    W_hx, W_yh, W_hh = npzfile["W_hx"], npzfile["W_yh"], npzfile["W_hh"]
    hidden_dim, word_dim = W_hx.shape[0], W_hx.shape[1]
    model = StackRNNTheano(word_dim, hidden_dim=hidden_dim, char_to_code_dict=char_to_code_dict)
    model.W_hx.set_value(W_hx)
    model.W_yh.set_value(W_yh)
    model.W_hh.set_value(W_hh)

    print "Building model model from %s with hidden_dim=%d word_dim=%d" % (path, hidden_dim, word_dim)
    return model

def save_model_parameters_lstm(outfile, model):
    np.savez(outfile,
        W_x_i=model.W_x_i.get_value(),
        W_h_i=model.W_h_i.get_value(),
        W_x_o=model.W_x_o.get_value(),
        W_h_o=model.W_h_o.get_value(),
        W_x_f=model.W_x_f.get_value(),
        W_h_f=model.W_h_f.get_value(),
        W_x_g=model.W_x_g.get_value(),
        W_h_g=model.W_h_g.get_value(),
        W_hy=model.W_hy.get_value())
    print "Saved model parameters to %s." % outfile

def load_model_parameters_lstm(path):
    npzfile = np.load(path)
    W_x_i, W_h_i = npzfile["W_x_i"], npzfile["W_h_i"]
    W_x_o, W_h_o = npzfile["W_x_o"], npzfile["W_h_o"]
    W_x_f, W_h_f = npzfile["W_x_f"], npzfile["W_h_f"]
    W_x_g, W_h_g = npzfile["W_x_g"], npzfile["W_h_g"]
    W_hy = npzfile["W_hy"]
    hidden_dim, word_dim = W_x_i.shape[0], W_x_i.shape[1]
    print "Building model model from %s with hidden_dim=%d word_dim=%d" % (path, hidden_dim, word_dim)
    sys.stdout.flush()
    model = LSTMTheano(word_dim, hidden_dim=hidden_dim)
    model.W_x_i.set_value(W_x_i)
    model.W_h_i.set_value(W_h_i)
    model.W_x_o.set_value(W_x_o)
    model.W_h_o.set_value(W_h_o)
    model.W_x_f.set_value(W_x_f)
    model.W_h_f.set_value(W_h_f)
    model.W_x_g.set_value(W_x_g)
    model.W_h_g.set_value(W_h_g)
    model.W_hy.set_value(W_hy)
    return model
