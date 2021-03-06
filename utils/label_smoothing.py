""" Implementation of LabelSmoothingLoss from OpenNMT """
import torch
from torch import nn
import torch.nn.functional as F


class LabelSmoothingLoss(nn.Module):
    """
    Use LabelSmoothing to compute the loss
    KL-Divergence between the q: smoothed ground truth prob distribution
    and p: probability distribution computed the model

    Why Label Smoothing? 
        A network is over confident when it places all probability on a `single class`
        in the training set. We want to prevent peaky distributions, which 
        can lead to better generalizations by relaxing the confidence on the labels. 
        By confidence, we mean to not use one hot encoding (place 1.0 probability on the correct
        next word in the sequence) but to use a more smoothed distribution. You still put most of the
        probability mass on the correct next word, but also put small probability mass on all other words
    """

    def __init__(self, label_smoothing, tgt_vocab_size, pad_index):
        assert 0.0 <= label_smoothing <= 1.0, "Label Smoothing parameter must between 0 and 1"
        super().__init__()
        self.pad_index = pad_index
        # (-2 to account for padding token)
        smoothing_value = label_smoothing / (tgt_vocab_size - 2)
        # [tgt_vocab_size]
        one_hot = torch.full((tgt_vocab_size,), smoothing_value)
        one_hot[self.pad_index] = 0
        # [1, tgt_vocab_size]
        self.register_buffer("one_hot", one_hot.unsqueeze(0))
        self.confidence = 1.0 - label_smoothing

    def forward(self, output, target):
        """
        output (FloatTensor): [batch_size * seq_len,  trg_vocab_size]
        target (Long Tensor): [batch_size * seq_len]
        """
        output = output.type(torch.DoubleTensor)
        # [batch_size, tgt_vocab_size]
        model_prob = self.one_hot.repeat(target.size(0), 1)
        model_prob.scatter_(1, target.unsqueeze(1), self.confidence)
        model_prob.masked_fill_((target == self.pad_index).unsqueeze(1), 0)
        return F.kl_div(output, model_prob.type(torch.DoubleTensor), reduction='sum')
