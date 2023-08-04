# LLaMA SQuAD

![LLaMA SQuAD](llama_squad.png)

## TL;DR

This repo uses the TRL (Transformer Reinforcement Library) to fine-tune Meta's Llama 2 model on the SQuAD v2 task. This is a particularly challenging task for decoder models like Llama, because it requires abstention when the answer is not in the context and exact extraction from the context when it is present. If we can fine-tune an encoder model so that it is more "honest" about what it cannot answer and to always give answers in a predictable format, then it should be possible to specialize these generalized foundation models on a wide range of tasks.

While a lot of progress has been made in the field of fine-tuning for mor general tasks, we find that it is necessary to adapt the procedure in order to get good results.

## Motivation

Before ChatGPT, we typically used encoder (discriminative) models to solve specific tasks such as classification and question answering. In fact, many of the SOTA results for these kind of tasks appear to have got stuck in time. Back then, decoder (generative) models like GPT seemed like they could be of little more use than to generate an alternative ending to a Harry Potter book. However, a first hint of their surprising utility was uncovered in the Open AI paper, ["Language Models are Unsupervised Multitask Learners"](https://cdn.openai.com/better-language-models/language_models_are_unsupervised_multitask_learners.pdf) in which they demonstrated the ability of GPT-2 (1.5B parameters!) to perform a variety of tasks such as translation, question answering, and summarization, all without the need for task-specific training.

ChatGPT works astonishingly well on a wide range of tasks, but it is not possible to specialize on a custom task beyond techniques such as "few shot learning" and "prompt engineering". In particular, there is no effective way to feed back examples that do not pass human validation, in order to improve model performance with active learning. Furthermore, there is no guarantee that OpenAI will maintain the performance of the model for your use case (see ["How is ChatGPT Behaviour Changing Over Time?"](https://arxiv.org/pdf/2307.09009.pdf)).

Thankfully, there have been great advances in Open Source, from models like Llama 2 (7B - 70B parameters) to techniques like QLoRA (Quantized Low-Rank Adaption) that make fine-tuning these models on a single prosumer GPU possible.

As an aside, encoders are not usually used for generation, but they can be persuaded to do so. As they were pre-trained on Masked Language Modelling, you can get them to "fill in the blanks". Unfortunately, they quickly become incoherent when several blanks appear together. Nevertheless, using MCMC (Markov Chain Monte Carlo) methods, it is possible to get [good results](https://github.com/teticio/inBERTolate). If you attempt this with an encoder that has been fine-tuned on a specific task, you will find it generates gibberish. The "fine-tuning" is causing catastrophic forgetting that may or may not be an issue for your particular use case. Whatever the case, if a model can be used for multiple purposes, then the cost of training it can be more easily justified. I suspect that this is why available decoder models are so much larger than encoder models.

It seems plausible that decoders may have some advantages over encoders for some tasks that require "reasoning". An encoder is specialized on a task by including a "head", which is often simply a dense layer. [Karpathy](https://www.youtube.com/watch?v=bZQun8Y4L2A) compares encoders to System 1 (automatic) thinking and decoders to System 2 (logical) thinking - Posner's classification of thought processes that was popularized by Daniel Kahneman. Indeed, Prompt Engineers have discovered that adding a seemingly innocuous instruction like "Think step by step" can improve the accuracy of the results. Certainly, the process of generating a sequence of tokens (words) requires much more computation than sticking a dense layer on top of an encoder, as you have to generate each token auto-regressively by feeding the previous generations into the model in sequence. This, combined with the "chat" approach of alternating between generated tokens and human input, seems to give the model more opportunity to "think" about the answer.

So how can we specialize these generalized decoder models? How can we put the Human back In The Loop?

## Approach

While ChatGPT has been fine-tuned with RLHF (Reinforcement Learning with Human Feedback) - a complex process still very much in research - a paper published by Meta called ["LIMA: Less Is More for Alignment"](https://arxiv.org/pdf/2305.11206.pdf) claims that SFT (Supervised Fine-Tuning) may be sufficient with relatively few examples, provided they are of very high quality.

The idea here is to use the excellent [TRL](https://github.com/lvwerra/trl) library from Hugging Face's Leandro von Werra to SFT a model on the SQuAD v2 task. The current SQuAD v2 [SOTA](https://paperswithcode.com/sota/question-answering-on-squad20) is an Exact Match for 90.9% of the test set. The dataset consists of contexts, questions and answers - which are verbatim extracts from the contexts. In some cases, there *is* no answer to the question in the context, and so the answer is an empty string. Foundation models like ChatGPT may excel in "reasoning", but it can be challenging to ensure that the answers are taken word-for-word from the context. In the case that there is no answer, there is an additional risk that they will provide an answer from memory or a "hallucination". There is, of course, also a risk that the SQuAD v2 test dataset was used as part of the training set of the foundation model.

We create a dataset according to the template that was used to train the chat version of Llama 2, with a system prompt enclosed by `<<SYS>>` and `<</SYS>>` tokens followed by an instruction terminated by `[/INST]` and finally the ground truth answer (as a continuation of the prompt).

````
<s>[INST] <<SYS>>                                                                                                                                     
You are a helpful, respectful and honest assistant. Always answer as helpfully as possible, while being safe.  Your answers should not include any harmful, unethical, racist, sexist, toxic, dangerous, or illegal content. Please ensure that your responses are socially unbiased and positive in nature.
If a question does not make any sense, or is not factually coherent, explain why instead of answering something not correct. If you don't know the answer to a question, please don't share false information.
<</SYS>>

Extract from the following context the minimal span word for word that best answers the question. Think step by step and explain your reasoning. Then give the answer in JSON format as follows:
```json
{
  "answer": ...
}
```
If the answer is not in the context, the answer should be "?".
Context: Beyoncé Giselle Knowles-Carter (/biːˈjɒnseɪ/ bee-YON-say) (born September 4, 1981) is an American singer, songwriter, record producer and actress. Born and raised in Houston, Texas, she performed in various singing and dancing competitions as a child, and rose to fame in the late 1990s as lead singer of R&B girl-group Destiny's Child. Managed by her father, Mathew Knowles, the group became one of the world's best-selling girl groups of all time. Their hiatus saw the release of Beyoncé's debut album, Dangerously in Love (2003), which established her as a solo artist worldwide, earned five Grammy Awards and featured the Billboard Hot 100 number-one singles "Crazy in Love" and "Baby Boy".
Question: When did Beyonce start becoming popular? [/INST] ```json
{
  "answer": "in the late 1990s"
}
``` </s>
````

## Masked Causal Language Modeling

We would like to retain the chat capacity of the model, while improving the accuracy of its responses. In order to this, we limit the cross entropy loss in the forward method of the model to only the tokens in the JSON response.

Notice that we include
````
Think step by step and explain your reasoning.
````
in the prompt. This is to encourage the model to space out the answer, rather than generating it all at once and has been shown to improve results with foundation models.

It would probably help if we were able to include the reasoning in the training data. As we do not have a ground-truth for it one approach would be use ChatGPT to generate it in a similar way to how the Alpaca model was trained. One experiment I tried was to simply replace the reasoning with "blah blah blah..." and ensure that the model did not attend those tokens. The hope was that the model would learn to space out the answer due to the relative positional embeddings. However, the results were worse than not including any reasoning at all. Remember that the model generates all the tokens in parallel in the forward pass, because we inject the ground-truth tokens in the input using [teacher forcing](https://towardsdatascience.com/what-is-teacher-forcing-3da6217fed1c). If we were to pass the generation of the previous token as an input to the next token - as is done in generation at inference time - this would mean reverting to a sequential calculation, which would be infeasible. This means that the model is not guided by the blahs, and is likely to go off at a tangent, rather like the encoder models do when generating text as mentioned previously.

We can train an adapted Llama model to do this by subclassing the `LlamaForCausalLM` model and overriding the `forward` method as follows:

```python
class LlamaSquad(LlamaForCausalLM):
    answer_start_token_id = 7521

    def forward(self, **kwargs):
        # Only calculate CE loss for the answer section of the labels
        for batch in range(kwargs["labels"].size(0)):
            answer_start = (
                kwargs["labels"][batch] == self.answer_start_token_id
            ).nonzero(as_tuple=True)[0][-1]
            kwargs["labels"][batch][:answer_start] = -100
        return super(LlamaForMaskedCausalLM, self).forward(**kwargs)
```

## How to use

### Install requirements

```bash
pip install -r requirements.txt
```

### Create dataset

```bash
python create_squad_dataset.py
```

### Train model

The training script `train_llama_squad.py` is heavily based on [one](https://gist.github.com/younesbelkada/9f7f75c94bdc1981c8ca5cc937d4a4da) provided by `younesbelkada`. It was important to use a much lower learning rate, in order to be able to train over the full training set without catastrophic forgetting. You may need to adjust the `per_device_train_batch_size` in order to fit the model in your GPU memory. You should also set the `gradient_accumulation_steps` so that `per_device_train_batch_size * gradient_accumulation_steps` is preserved.

```bash
python train_llama_squad.py \
--model_name meta-llama/Llama-2-7b-chat-hf \
--dataset_name data/squad_v2 \
--bf16 \
--max_seq_length 4096 \
--per_device_train_batch_size 4 \
--gradient_accumulation_steps 4 \
--max_steps 10000 \
--merge_and_push \
--save_steps 1000 \
--learning_rate=2e-7
```

### Evaluate model

If you run out of GPU memory, pass the parameter `--quantize` to the script.

```bash
python test_llama_squad.py --adapter_name=results/final_checkpoints
```

### Results

The fine-tuning was performed over 10,000 steps (1.2 epochs) with a learning rate of `2e-7`. On the test set, the models achieve the following results:

| Model                         | % Valid JSON | % Exact Match | % EM for Valid JSON | % Correct Abstentions |
| ----------------------------- | ------------ | ------------- | ------------------- | --------------------- |
| Llama 2 7b Chat (base model)  | 66.42%       | 16.64%        | 24.62%              | 3.72%                 |
| [Fine-tuned (single turn)](https://wandb.ai/teticio/huggingface/runs/p00jazs1?workspace=user-teticio) | 96.60%       | 41.30%        | 42.71%              | 37.76%                |

The fine-tuned model has clearly learned to respect JSON format, has learned to abstain more often and has greatly improved the exact matches (although this is still far from SOTA!). A qualtitative analysis of the results reveals that the model is inherently limited by its reasoning capabilities. It is often tripped up by deliberately misleading questions, such as the following:

> Studies on income inequality and growth have sometimes found evidence confirming the Kuznets curve hypothesis, which states that with economic development, inequality first increases, then decreases. Economist Thomas Piketty challenges this notion, claiming that from 1914 to 1945 wars and "violent economic and political shocks" reduced inequality. Moreover, Piketty argues that the "magical" Kuznets curve hypothesis, with its emphasis on the balancing of economic growth in the long run, cannot account for the significant increase in economic inequality throughout the developed world since the 1970s.

> What isn't Thomas Piketty's job?

Nevertheless, the results are encouraging and indicate that much better results could be obtained by applying the same procedure to the Llama 2 70b model.

### TODO

* Examples.
* Multi-turn.
* Try EWC ([Elastic Weight Consolidation](https://arxiv.org/pdf/1612.00796.pdf)) to prevent catastrophic forgetting over the question, while further training the answer.
* Try UKD ([Unsupervised Knowledge Distillation](https://arxiv.org/pdf/2302.11074.pdf)).
