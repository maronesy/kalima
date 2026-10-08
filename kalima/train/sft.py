"""Supervised fine-tuning of the subgoal model (stage 1 of docs/TRAINING_PLAN.md).

LoRA on a 7-8B prover, bf16, on one GPU (H100/A100 80 GB). Loss on the completion only.
Usage: python -m kalima.train.sft --config configs/sft.yaml
"""
import argparse, json, yaml
import torch
from datasets import load_dataset
from peft import LoraConfig
from trl import SFTConfig, SFTTrainer
from transformers import AutoModelForCausalLM, AutoTokenizer


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--config", required=True)
    cfg = yaml.safe_load(open(ap.parse_args().config))
    tok = AutoTokenizer.from_pretrained(cfg["base_model"])
    model = AutoModelForCausalLM.from_pretrained(cfg["base_model"], torch_dtype=torch.bfloat16, attn_implementation="sdpa")
    data = load_dataset("json", data_files={"train": cfg["train_file"], "validation": cfg["valid_file"]})
    lora = LoraConfig(r=cfg["lora_r"], lora_alpha=cfg["lora_alpha"], lora_dropout=0.05, target_modules="all-linear", task_type="CAUSAL_LM")
    args = SFTConfig(output_dir=cfg["output_dir"], num_train_epochs=cfg["epochs"], learning_rate=cfg["lr"],
                     per_device_train_batch_size=cfg["batch_size"], gradient_accumulation_steps=cfg["grad_accum"],
                     bf16=True, gradient_checkpointing=True, logging_steps=10, eval_strategy="steps", eval_steps=200,
                     save_steps=500, max_length=cfg["max_length"], completion_only_loss=True, report_to="none")
    SFTTrainer(model=model, args=args, train_dataset=data["train"], eval_dataset=data["validation"],
               processing_class=tok, peft_config=lora).train()


if __name__ == "__main__":
    main()
