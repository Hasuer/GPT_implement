由Andrej Karpathy的lecture而来，目的是跟随[视频](https://www.youtube.com/watch?v=kCc8FmEb1nY&ab_channel=AndrejKarpathy)自己实现GPT，对于decoder模块的架构更加了解。

其中对于scaled-attention的解释比较好(note 6)，但是也没有完全听懂，加入scaled-attention的目的是为了让Q\*K^T的方差在1左右，否则在head_size左右，也就是论文中的d_m. 如果没有进行scaled的话，Q\*K^T方差较大，说明数据比较分散，那么较大的值在softmax之后都会聚集在1左边，而较小的值在softmax之后都会据集在-1的右边，这样就会导致在反向传播的时候会产生梯度消失的问题。一些常用的激活函数，如 sigmoid 和 tanh，在输入较大或较小的时候会饱和，导致梯度接近于零。sigmoid函数的输出范围在0,1之间，当输入非常大或非常小时，函数的斜率（梯度）趋近于零。

