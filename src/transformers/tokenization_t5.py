# coding=utf-8
# Copyright 2018 T5 Authors and HuggingFace Inc. team.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
""" Tokenization class for model T5."""


import logging
import os
import re
from shutil import copyfile

from .tokenization_utils import PreTrainedTokenizer


logger = logging.getLogger(__name__)

SPIECE_UNDERLINE = "▁"

####################################################
# Mapping from the keyword arguments names of Tokenizer `__init__`
# to file names for serializing Tokenizer instances
####################################################
VOCAB_FILES_NAMES = {"vocab_file": "spiece.model"}

####################################################
# Mapping from the keyword arguments names of Tokenizer `__init__`
# to pretrained vocabulary URL for all the model shortcut names.
####################################################
PRETRAINED_VOCAB_FILES_MAP = {
    "vocab_file": {
        "t5-small": "https://s3.amazonaws.com/models.huggingface.co/bert/t5-spiece.model",
        "t5-base": "https://s3.amazonaws.com/models.huggingface.co/bert/t5-spiece.model",
        "t5-large": "https://s3.amazonaws.com/models.huggingface.co/bert/t5-spiece.model",
        "t5-3b": "https://s3.amazonaws.com/models.huggingface.co/bert/t5-spiece.model",
        "t5-11b": "https://s3.amazonaws.com/models.huggingface.co/bert/t5-spiece.model",
    }
}

####################################################
# Mapping from model shortcut names to max length of inputs
####################################################
PRETRAINED_POSITIONAL_EMBEDDINGS_SIZES = {
    "t5-small": 512,
    "t5-base": 512,
    "t5-large": 512,
    "t5-3b": 512,
    "t5-11b": 512,
}


class T5Tokenizer(PreTrainedTokenizer):
    """
        SentencePiece based tokenizer. Peculiarities:

            - requires `SentencePiece <https://github.com/google/sentencepiece>`_
            - `extra_ids` add a number of extra ids added to the end of the vocabulary for use as sentinels.
                These tokens are accessible as `<extra_id_{%d}>` where `{%d}` is a number between 0 and extra_ids-1.
                Extra tokens are indexed from the end of the vocabulary up to beginnning (<extra_id_0> is the last token in the vocabulary)
                (like in T5 preprocessing
                see: https://github.com/google-research/text-to-text-transfer-transformer/blob/9fd7b14a769417be33bc6c850f9598764913c833/t5/data/preprocessors.py#L2117)
    """

    vocab_files_names = VOCAB_FILES_NAMES
    pretrained_vocab_files_map = PRETRAINED_VOCAB_FILES_MAP
    max_model_input_sizes = PRETRAINED_POSITIONAL_EMBEDDINGS_SIZES

    def __init__(
        self,
        vocab_file,
        bos_token="<s>",
        eos_token="</s>",
        unk_token="<unk>",
        pad_token="<pad>",
        extra_ids=100,
        additional_special_tokens=None,
        **kwargs
    ):
        # Add extra_ids to the special token list
        if extra_ids > 0:
            if additional_special_tokens is None:
                additional_special_tokens = []
            additional_special_tokens.extend(["<extra_id_{}>".format(i) for i in range(extra_ids)])

        super(T5Tokenizer, self).__init__(
            bos_token=bos_token,
            eos_token=eos_token,
            unk_token=unk_token,
            pad_token=pad_token,
            additional_special_tokens=additional_special_tokens,
            **kwargs
        )

        try:
            import sentencepiece as spm
        except ImportError:
            logger.warning(
                "You need to install SentencePiece to use T5Tokenizer:"
                "https://github.com/google/sentencepiece"
                "pip install sentencepiece"
            )
            raise

        self.vocab_file = vocab_file
        self._extra_ids = extra_ids

        self.sp_model = spm.SentencePieceProcessor()
        self.sp_model.Load(vocab_file)

    @property
    def vocab_size(self):
        return self.sp_model.get_piece_size() + self._extra_ids

    def __getstate__(self):
        state = self.__dict__.copy()
        state["sp_model"] = None
        return state

    def __setstate__(self, d):
        self.__dict__ = d
        try:
            import sentencepiece as spm
        except ImportError:
            logger.warning(
                "You need to install SentencePiece to use XLNetTokenizer: https://github.com/google/sentencepiece"
                "pip install sentencepiece"
            )
            raise
        self.sp_model = spm.SentencePieceProcessor()
        self.sp_model.Load(self.vocab_file)

    def _tokenize(self, text, sample=False):
        """ Take as input a string and return a list of strings (tokens) for words/sub-words
        """
        if not sample:
            pieces = self.sp_model.EncodeAsPieces(text)
        else:
            pieces = self.sp_model.SampleEncodeAsPieces(text, 64, 0.1)
        return pieces

    def _convert_token_to_id(self, token):
        """ Converts a token (str) in an id using the vocab. """
        if token.startswith("<extra_id_"):
            match = re.match(r"<extra_id_(\d+)>", token)
            num = int(match.group(1))
            return self.vocab_size - num - 1
        return self.sp_model.piece_to_id(token)

    def _convert_id_to_token(self, index):
        """Converts an index (integer) in a token (str) using the vocab."""
        if index < self.sp_model.get_piece_size():
            token = self.sp_model.IdToPiece(index)
        else:
            token = "<extra_id_{}>".format(self.vocab_size - 1 - index)
        return token

    def convert_tokens_to_string(self, tokens):
        """ Converts a sequence of tokens (string) in a single string. """
        out_string = self.sp_model.decode_pieces(tokens)
        return out_string

    def build_inputs_with_special_tokens(self, token_ids_0, token_ids_1=None):
        """
        Build model inputs from a sequence or a pair of sequence for seq-to-seq tasks
        by concatenating and adding special tokens.
        A encoder-decoder sequence has the following format:
            single sequence: <s> X </s>
            pair of sequences: <s> A </s></s> B </s>
        """
        if token_ids_1 is None:
            return [self.bos_token_id] + token_ids_0 + [self.eos_token_id]
        return [self.bos_token_id] + token_ids_0 + [self.eos_token_id] + [self.bos_token_id] + token_ids_1 + [self.eos_token_id]

    def save_vocabulary(self, save_directory):
        """ Save the sentencepiece vocabulary (copy original file) and special tokens file
            to a directory.
        """
        if not os.path.isdir(save_directory):
            logger.error("Vocabulary path ({}) should be a directory".format(save_directory))
            return
        out_vocab_file = os.path.join(save_directory, VOCAB_FILES_NAMES["vocab_file"])

        if os.path.abspath(self.vocab_file) != os.path.abspath(out_vocab_file):
            copyfile(self.vocab_file, out_vocab_file)

        return (out_vocab_file,)
