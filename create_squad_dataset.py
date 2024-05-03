import json
from dataclasses import dataclass, field
from textwrap import dedent
from types import SimpleNamespace
from typing import Optional

import yaml
from datasets import DatasetDict, load_dataset
from transformers import HfArgumentParser

from model import REASONING


@dataclass
class ScriptArguments:
    prompt: Optional[str] = field(
        default="single_turn",
        metadata={"help": "single_turn, multi_turn"},
    )
    validation_ratio: Optional[float] = field(
        default=0.005,
        metadata={"help": "Validation ratio"},
    )
    seed: Optional[int] = field(
        default=42,
        metadata={"help": "Seed for the random number generator"},
    )


parser = HfArgumentParser(ScriptArguments)
script_args = parser.parse_args_into_dataclasses()[0]
config = SimpleNamespace(**yaml.safe_load(open("config.yaml")))


def get_single_turn_prompt_and_response(item):
    context = item["context"]
    question = item["question"]
    answers = item["answers"]["text"]
    if len(answers) == 0:
        answers = ["?"]
    answers = json.dumps(answers)

    return {
        "messages": [
            {"role": "system", "content": config.system_prompt},
            {
                "role": "user",
                "content": dedent(
                    f"""\
                    Extract from the following context the minimal span word for word that best answers the question. Think step by step and explain your reasoning. Then give the answer in JSON format as follows:
                    ```json
                    {{
                    "answer": ...
                    }}
                    ```
                    If the answer is not in the context, the answer should be "?".
                    Context: {context}
                    Question: {question}"""
                ),
            },
            {
                "role": "assistant",
                "content": dedent(
                    f"""\
                    {REASONING}
                    ```json
                    {{
                    "answer": {answers}
                    }}
                    ```"""
                ),
            },
        ]
    }


def get_multi_turn_prompt_and_response(item):
    context = item["context"]
    question = item["question"]
    answers = item["answers"]["text"]
    if len(answers) == 0:
        answers = ["?"]
    answers = json.dumps(answers)

    return {
        "messages": [
            {"role": "system", "content": config.system_prompt},
            {
                "role": "user",
                "content": dedent(
                    f"""\
                    Use the following context to answer the question. Think step by step and explain your reasoning.
                    Context: {context}
                    Question: {question}"""
                ),
            },
            {"role": "assistant", "content": REASONING},
            {
                "role": "user",
                "content": dedent(
                    """\
                    Extract the minimal span word for word from the context that best answers the question.
                    """
                ),
            },
            {"role": "assistant", "content": REASONING},
            {
                "role": "user",
                "content": dedent(
                    """\
                    Now give the answer in JSON format as follows:
                    ```json
                    {
                    "answer": ...
                    }
                    ```
                    If the answer is not in the context, the answer should be "?".
                    """
                ),
            },
            {
                "role": "assistant",
                "content": dedent(
                    f"""\
                    {REASONING}
                    ```json
                    {{
                    "answer": {answers}
                    }}
                    ```"""
                ),
            },
        ]
    }


instruction = {
    "single_turn": get_single_turn_prompt_and_response,
    "multi_turn": get_multi_turn_prompt_and_response,
}[script_args.prompt]

squad_dataset = load_dataset("squad_v2")
dataset = squad_dataset["train"].train_test_split(
    test_size=script_args.validation_ratio,
    seed=script_args.seed,
)
train_dataset = dataset["train"].map(instruction)
val_dataset = dataset["test"].map(instruction)
print(train_dataset[0])
test_dataset = squad_dataset["validation"].map(instruction)
dataset = DatasetDict(
    {"train": train_dataset, "val": val_dataset, "test": test_dataset}
)
dataset.save_to_disk(config.dataset_name)
