import argparse
import torch
from torch import nn
from torch.autograd import Variable
from torch import optim
from torch.nn.utils import clip_grad_norm
from torch.nn import functional as F
from utils.data_loader import load_dataset
from models.lstm_seq2seq import Encoder, Decoder, Seq2Seq
from utils.utils import HyperParams, set_logger, load_checkpoint, save_checkpoint, RunningAverage
import os, sys
import logging
import time

def evaluate_loss_on_dev(model, dev_iter, params):
    """
    Evaluate the loss of the `model` on the dev set

    Arguments:
        model: the neural network
        dev_iter: BucketIterator for the dev set
        params: hyperparameters for the `model`
    """

    model.eval()
    criterion = nn.CrossEntropyLoss(ignore_index=params.pad_token)
    loss_avg = RunningAverage()
    with torch.no_grad():
        for index, batch in enumerate(dev_iter):
            src, trg = batch.src, batch.trg

            if params.cuda:
                src, trg = src.cuda(), trg.cuda()

            output = model(src, trg, tf_ratio=0.0)
            output = output[:, :-1, :].contiguous().view(-1, params.vocab_size)
            trg = trg[:, 1:].contiguous().view(-1)

            assert output.size(0) == trg.size(0)

            loss = criterion(output, trg)
            loss_avg.update(loss.item())
    return loss_avg()

def train_model(epoch_num, model, optimizer, train_iter, params):
    """
    Train the Model for one epoch on the training set

    Arguments:
        epoch_num: epoch number during training
        model: the neural network
        optimizer: optimizer for the parameters of the model
        train_iter: BucketIterator over the training data
        params: hyperparameters for the `model`
    """

    model.train()
    criterion = nn.CrossEntropyLoss(ignore_index=params.pad_token)
    loss_avg = RunningAverage()
    for index, batch in enumerate(train_iter):
        src, trg = batch.src, batch.trg
        len_src, len_trg = src.size(0), trg.size(0)

        if params.cuda:
            src, trg = src.cuda(), trg.cuda()

        output = model(src, trg, tf_ratio=params.teacher_forcing_ratio)
        output = output[:, :-1, :].contiguous().view(-1, params.vocab_size)
        trg = trg[:, 1:].contiguous().view(-1)

        assert output.size(0) == trg.size(0)

        optimizer.zero_grad()
        loss = criterion(output, trg)
        loss.backward()

        nn.utils.clip_grad_norm_(model.parameters(), params.grad_clip)
        optimizer.step()

        # update the average loss
        loss_avg.update(loss.item())

        if index % 50 == 0 and index != 0:
            logging.info("[%d][loss:%5.2f][pp:%5.2f]" %
                                    (index, loss_avg(), math.exp(loss_avg())))
        return loss_avg()

def epoch_time(start_time, end_time):
    """ Calculate time to train a single Epoch in minutes and seconds """
    elapsed_time = end_time - start_time
    elapsed_mins = int(elapsed_time / 60)
    elapsed_secs = int(elapsed_time - (elapsed_mins * 60))
    return elapsed_mins, elapsed_secs

def main(params):
    """
    The main function for training the Seq2Seq model with Dot-Product Attention

    Arguments:
        params: hyperparameters for the model
        model_dir: directory of the model
        restore_file: restore file for the model
    """

    logging.info("Loading the datasets...")
    train_iter, dev_iter, DE, EN = load_dataset(params.data_path, params.min_freq, params.batch_size)
    de_size, en_size = len(DE.vocab), len(EN.vocab)
    logging.info("[DE Vocab Size]: {}, [EN Vocab Size]: {}".format(de_size, en_size))
    logging.info("- done.")

    params.vocab_size = en_size
    params.pad_token = EN.vocab.stoi["<pad>"]

    # Instantiate the Seq2Seq model
    encoder = Encoder(input_size=de_size, embed_size=params.embed_size,
                      hidden_size=params.hidden_size, num_layers=params.n_layers_enc, dropout=params.dropout_enc)
    decoder = Decoder(output_size=en_size, embed_size=params.embed_size,
                      hidden_size=params.hidden_size, num_layers=params.n_layers_dec, dropout=params.dropout_dec)
    # seq2seq = Seq2SeqAttn(encoder, decoder).cuda() if params.cuda else Seq2SeqAttn(encoder, decoder)
    device = torch.device('cuda' if params.cuda else 'cpu')
    seq2seq = Seq2Seq(encoder, decoder, device).to(device)

    optimizer = optim.Adam(seq2seq.parameters(), lr=params.lr)

    if params.restore_file:
        restore_path = os.path.join(params.model_dir+"/checkpoints/", params.restore_file)
        logging.info("Restoring parameters from {}".format(restore_path))
        load_checkpoint(restore_path, seq2seq, optimizer)

    best_val_loss = float('inf')

    logging.info("Starting training for {} epoch(s)".format(params.epochs))
    for epoch in range(params.epochs):
        logging.info("Epoch {}/{}".format(epoch+1, params.epochs))

        # train the model for one epcoh
        epoch_start_time = time.time()
        train_loss_avg = train_model(epoch, seq2seq, optimizer, train_iter, params)
        epoch_end_time = time.time()
        epoch_mins, epoch_secs = epoch_time(epoch_start_time, epoch_end_time)

        # evaluate the model on the dev set
        val_loss = evaluate_loss_on_dev(seq2seq, dev_iter, params)
        # logging.info("Val loss after {} epochs: {}".format(epoch+1, val_loss))
        logging.info(f'Epoch: {epoch+1:02} | Avg Train Loss: {train_loss_avg} | Val Loss: {val_loss} | Time: {epoch_mins}m {epoch_secs}s')
        # val_loss = .003
        is_best = val_loss < best_val_loss

        # save checkpoint
        save_checkpoint({
            "epoch": epoch+1,
            "state_dict": seq2seq.state_dict(),
            "optim_dict": optimizer.state_dict()},
            is_best=is_best,
            checkpoint=params.model_dir+"/checkpoints/")

        if is_best:
            logging.info("- Found new lowest loss!")
            best_val_loss = val_loss


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Seq2Seq w/ Attention Hyperparameters")
    p.add_argument("-data_path", type=str, help="location of data")
    p.add_argument("-model_dir", default="./experiments/seq2seq", help="Directory containing seq2seq experiments")
    p.add_argument("-restore_file", default=None, help="Name of the file in the model directory containing weights \
                   to reload before training")
    args = p.parse_args()

    # create an experiments folder for training the seq2seq model
    if not os.path.exists("./experiments/seq2seq/"):
        os.mkdir("./experiments/seq2seq/")

    # Set the logger
    set_logger(os.path.join(args.model_dir, "train.log"))

    # load the params json file (if it exists)
    json_params_path = os.path.join(args.model_dir, "params.json")
    assert os.path.isfile(json_params_path), "No json configuration file found at {}".format(json_params_path)
    params = HyperParams(json_params_path)

    # add extra information to the params dictionary related to the training of the model
    params.data_path = args.data_path
    params.model_dir = args.model_dir
    params.restore_file = args.restore_file

    # use GPU if available
    params.cuda = torch.cuda.is_available()
    logging.info("Using GPU: {}".format(params.cuda))

    # manual seed for reproducing experiments
    torch.manual_seed(2)
    if params.cuda: torch.cuda.manual_seed(2)

    main(params)
