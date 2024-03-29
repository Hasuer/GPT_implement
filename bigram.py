import torch
import torch.nn as nn
from torch.nn import functional as F

# hyperparameters
batch_size = 32 # how many independent sequences will we process in parallel?
block_size = 8 # what is the maximum context length for predictions?
max_iters = 5000
eval_interval = 300
learning_rate = 1e-3 #lr减小的同时，可以适当的增加max_iters也就是训练的step
device = 'cuda:2' if torch.cuda.is_available() else 'cpu'
eval_iters = 200
n_embd = 32 # numbers for embedding dimension
# ------------

torch.manual_seed(1337)

# wget https://raw.githubusercontent.com/karpathy/char-rnn/master/data/tinyshakespeare/input.txt
with open('LLM_learn/GPT_impement/input.txt', 'r', encoding='utf-8') as f:
    text = f.read()

# here are all the unique characters that occur in this text
chars = sorted(list(set(text)))
vocab_size = len(chars)
# create a mapping from characters to integers
stoi = { ch:i for i,ch in enumerate(chars) }
itos = { i:ch for i,ch in enumerate(chars) }
encode = lambda s: [stoi[c] for c in s] # encoder: take a string, output a list of integers
decode = lambda l: ''.join([itos[i] for i in l]) # decoder: take a list of integers, output a string

# Train and test splits
data = torch.tensor(encode(text), dtype=torch.long)
n = int(0.9*len(data)) # first 90% will be train, rest val
train_data = data[:n]
val_data = data[n:]

# data loading
def get_batch(split):
    data = train_data if split == "train" else val_data
    #size must be ints,no int. x_index.shape = [batch_size]
    x_index = torch.randint(len(data) - block_size, (batch_size, )) 
    x = torch.stack([data[i : i+block_size] for i in x_index])
    y = torch.stack([data[i+1: i+1 + block_size] for i in x_index])
    x, y = x.to(device), y.to(device)
    return x, y

@torch.no_grad()
def estimate_loss():
    out = {}
    model.eval()
    for split in ['train', 'val']:
        losses = torch.zeros(eval_iters)
        for k in range(eval_iters):
            X, Y = get_batch(split)
            logits, loss = model(X, Y)
            losses[k] = loss.item()
        out[split] = losses.mean()
    model.train()
    return out

class Head(nn.Module):
    # 单头注意力机制
    
    def __init__(self,head_size) -> None:
        super().__init__()
        self.key = nn.Linear(n_embd, head_size, bias=False)
        self.query = nn.Linear(n_embd, head_size, bias=False)
        self.value = nn.Linear(n_embd, head_size, bias=False)
        self.register_buffer('tril',torch.tril(torch.ones(block_size, block_size)))
        
    def forward(self, x):
        B,T,C = x.shape
        k = self.key(x) # (B, T, C)
        q = self.query(x) # (B, T, C)
        v = self.value(x) # (B, T, C)
        wei = q @ k.transpose(-2,-1) * (C ** -0.5) # (B, T, T)
        # [:T,:T]这个加不加在训练的时候不重要，但是在generate的时候重要
        wei = wei.masked_fill(self.tril[:T,:T] == 0, float('-inf')) # (B, T, T) torch.Size([8, 8])
        wei = F.softmax(wei, dim= -1)
        v = self.value(x) # (B, T, C) torch.Size([32, 8, 32])
        out = wei @ v # (B, T, T) torch.Size([8, 8])
        return out
    
class MultiHeadAttention(nn.Module):
    """ multiple heads of self-attention in parallel """

    def __init__(self, num_heads, head_size):
        super().__init__()
        self.heads = nn.ModuleList([Head(head_size) for _ in range(num_heads)])
        # self.proj = nn.Linear(head_size * num_heads, n_embd)
        # self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        out = torch.cat([h(x) for h in self.heads], dim=-1) # h(x) 的size torch.Size([32, 8, 8])
        # out = self.dropout(self.proj(out))
        return out
    
class FeedFoward(nn.Module):
    """ a simple linear layer followed by a non-linearity """

    def __init__(self, n_embd):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_embd, 4 * n_embd),
            nn.ReLU(),
            nn.Linear(4 * n_embd, n_embd),
            # nn.Dropout(dropout),
        )

    def forward(self, x):
        return self.net(x)
        
# super simple bigram model
class GPTLanguageModel(nn.Module):

    def __init__(self):
        super().__init__()
        # each token directly reads off the logits for the next token from a lookup table
        self.token_embedding_table = nn.Embedding(vocab_size,n_embd)
        self.position_embedding_table = nn.Embedding(block_size, n_embd) #block_size可以理解为sequence_length
        self.sa_head = MultiHeadAttention(4, n_embd//4) # self-attention head
        self.ffwd = FeedFoward(n_embd) #前馈网络
        self.lm_head = nn.Linear(n_embd, vocab_size) ## linear to transfer tok_emb ---> logits

    def forward(self, idx, targets=None):
        B,T = idx.shape # T其实就是block_size

        # idx and targets are both (B,T) tensor of integers
        tok_emb = self.token_embedding_table(idx) # (B,T,C) [32, 8, 32]
        pos_emb = self.position_embedding_table(torch.arange(T, device = device)) # (T,C) 生成一个一维张量 torch.Size([8, 32])
        x = tok_emb + pos_emb # 使用广播机制相加 torch.Size([32, 8, 32])
        x = self.sa_head(x) # torch.Size([32, 8, 32])
        x = self.ffwd(x) # torch.Size([32, 8, 32])
        logits = self.lm_head(x) # torch.Size([32, 8, 65])

        if targets is None:
            loss = None
        else:
            B, T, C = logits.shape
            logits = logits.view(B*T, C) # torch.Size([256, 65])
            targets = targets.view(B*T) # torch.Size([256])
            loss = F.cross_entropy(logits, targets)

        return logits, loss

    def generate(self, idx, max_new_tokens):
        # idx is (B, T) array of indices in the current context
        for _ in range(max_new_tokens):
            idx_cond = idx[:,-block_size:] #pos_emb由于
            # get the predictions
            logits, loss = self(idx_cond)
            # focus only on the last time step
            logits = logits[:, -1, :] # becomes (B, C)
            # apply softmax to get probabilities
            probs = F.softmax(logits, dim=-1) # (B, C)
            # sample from the distribution
            idx_next = torch.multinomial(probs, num_samples=1) # (B, 1)
            # append sampled index to the running sequence
            idx = torch.cat((idx, idx_next), dim=1) # (B, T+1)
        return idx

model = GPTLanguageModel()
m = model.to(device)

# create a PyTorch optimizer
optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)

for iter in range(max_iters):

    # every once in a while evaluate the loss on train and val sets
    if iter % eval_interval == 0:
        losses = estimate_loss()
        print(f"step {iter}: train loss {losses['train']:.4f}, val loss {losses['val']:.4f}")

    # sample a batch of data
    xb, yb = get_batch('train')

    # evaluate the loss
    logits, loss = model(xb, yb)
    optimizer.zero_grad(set_to_none=True)
    loss.backward()
    optimizer.step()

# generate from the model
context = torch.zeros((1, 1), dtype=torch.long, device=device)
print(decode(m.generate(context, max_new_tokens=500)[0].tolist()))
