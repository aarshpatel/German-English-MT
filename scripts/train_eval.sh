# Script to train and evaluate Seq2Seq models (Attentional GRU and Transformer)

# Make sure if the arguments were passed in
if [[ $# -eq 0 ]] ; then
    echo "Did not pass in the correct number of arguments"
    echo "This is the correct way to run the script: ./scripts/train_eval.sh {config_file} {exp_name}"
    exit 1
fi


# Data Folder
data_path=./data/iwslt/bpe/

# Load in the model config file
model_config=$1
source $model_config 

# Experiment Name
exp_name=$2

# Make an ./experiments folder if it doesn't exist
mkdir -p ./experiments

# Using the exp_naem, create a model directory in the ./experiments folder
model_dir="./experiments/"$exp_name"/"

# run make_config.py to make the model folder
echo "Make experiment folder for exp_name: " $exp_name

if [ $model_type = "GRU" ]
then
    python ./make_config.py -e $epochs -mf $min_freq -trbsz $train_batch_size -dvbsz $dev_batch_size \
                            -embsz $embedding_size -hidsz $hidden_size -nenc $n_layers_enc -ndec $n_layers_dec \
                            -maxlen $max_len -lr $lr -gc $grad_clip -tf $tf -inpdrop $input_dropout -laydrop $layer_dropout  \
                            -decweightshare $tgt_emb_prj_weight_sharing -encdecweightshare $emb_src_tgt_weight_sharing \
                            -attention $attention -exp_name $exp_name -model_type $model_type
else
    python ./make_config.py -e $epochs -mf $min_freq -trbsz $train_batch_size -dvbsz $dev_batch_size \
                            -embsz $embedding_size -hidsz $hidden_size -nenc $n_layers_enc -ndec $n_layers_dec \
                            -maxlen $max_len -lr $lr -gc $grad_clip -tf $tf -inpdrop $input_dropout -laydrop $layer_dropout  \
                            -attndrop $attention_dropout -reldrop $relu_dropout -labsmooth $label_smoothing -dff $d_ff \
                            -decweightshare $tgt_emb_prj_weight_sharing -encdecweightshare $emb_src_tgt_weight_sharing \
                            -warmup $n_warmup_steps -exp_name $exp_name -model_type $model_type
fi
echo "Done making experiment folder..."

echo "Training experiment: " $exp_name " using model_type: " $model_type
python train.py -data_path=$data_path -model_dir=$model_dir

echo "Evaluating Model on Dev set using Greedy/Beam Search..."
python translate.py -data_path=$data_path -model_dir=$model_dir -average=$average -beam_size=$beam_size