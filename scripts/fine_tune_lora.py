"""LoRA fine-tune the local LLM on collected user feedback.

This script is run *offline*, separate from the API. It:
  1. Pulls preferred (Q, A) pairs from feedback.sqlite
  2. Builds an instruction-tuning dataset
  3. Loads a base HF model (default: meta-llama/Llama-3.2-3B-Instruct or
     google/gemma-2-2b-it — any chat model)
  4. Trains a LoRA adapter with PEFT
  5. Optionally exports a GGUF + Modelfile for serving via Ollama

Usage:
    python scripts/fine_tune_lora.py --base meta-llama/Llama-3.2-3B-Instruct \
        --out data/lora/ragh-tutor --epochs 3

Requires extra deps (install in a venv since they're heavy):
    pip install transformers peft datasets accelerate bitsandbytes trl
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

# allow `from ragh...` when run via PYTHONPATH=./src
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def collect_examples(min_rating: int = 0) -> list[dict]:
    from ragh.training.feedback_store import FeedbackStore
    store = FeedbackStore()
    raw = store.export_jsonl(only_rated=True)
    examples = []
    for r in raw:
        if r.get("label") == "rejected":
            continue
        if r.get("rating", 0) < min_rating:
            continue
        instr = r.get("rewritten_query") or r.get("instruction") or ""
        resp = r.get("response") or ""
        if not instr or not resp:
            continue
        examples.append({"instruction": instr, "response": resp})
    return examples


def build_chat_dataset(examples, tokenizer):
    from datasets import Dataset
    rows = []
    for ex in examples:
        msgs = [
            {"role": "system", "content": "You are a JEE/NEET study tutor. Answer with clean prose, cite sources, reconstruct any garbled math."},
            {"role": "user", "content": ex["instruction"]},
            {"role": "assistant", "content": ex["response"]},
        ]
        text = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=False)
        rows.append({"text": text})
    return Dataset.from_list(rows)


def train(args):
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, TrainingArguments
    from peft import LoraConfig, get_peft_model, TaskType
    from trl import SFTTrainer

    print(f"[+] Collecting feedback examples …")
    examples = collect_examples(min_rating=args.min_rating)
    if len(examples) < 4:
        print(f"[!] Only {len(examples)} examples — collect more thumbs-up feedback before training.")
        return
    print(f"[+] {len(examples)} positive examples")

    print(f"[+] Loading base model: {args.base}")
    tokenizer = AutoTokenizer.from_pretrained(args.base)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(
        args.base,
        torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
        device_map="auto",
    )

    print("[+] Wrapping in LoRA")
    peft_cfg = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=0.05,
        target_modules=["q_proj", "v_proj"],
    )
    model = get_peft_model(model, peft_cfg)
    model.print_trainable_parameters()

    print("[+] Building dataset")
    ds = build_chat_dataset(examples, tokenizer)

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    targs = TrainingArguments(
        output_dir=str(out_dir),
        per_device_train_batch_size=args.batch,
        gradient_accumulation_steps=4,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        bf16=False,
        fp16=torch.cuda.is_available(),
        logging_steps=5,
        save_strategy="epoch",
        report_to=[],
    )

    trainer = SFTTrainer(
        model=model,
        args=targs,
        train_dataset=ds,
        tokenizer=tokenizer,
        dataset_text_field="text",
        max_seq_length=2048,
    )
    print("[+] Training …")
    trainer.train()

    print(f"[+] Saving LoRA adapter to {out_dir}")
    model.save_pretrained(str(out_dir))
    tokenizer.save_pretrained(str(out_dir))

    # write a Modelfile so the user can `ollama create ragh-tutor -f Modelfile`
    modelfile = out_dir / "Modelfile"
    modelfile.write_text(
        f"FROM {args.base}\n"
        f"# After converting the LoRA adapter to GGUF, replace this with: ADAPTER ./adapter.gguf\n"
        f"PARAMETER temperature 0.2\n"
        f"SYSTEM \"You are a JEE/NEET tutor. Cite sources. Use clean math notation.\"\n"
    )
    print(f"[+] Wrote Modelfile: {modelfile}")
    print("\nTo serve via Ollama:")
    print("  1. Convert adapter.safetensors → adapter.gguf (llama.cpp convert script)")
    print("  2. Edit Modelfile to point at adapter.gguf via `ADAPTER`")
    print(f"  3. ollama create ragh-tutor -f {modelfile}")
    print("  4. Set OLLAMA_MODEL=ragh-tutor in ragh config and restart the API")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="meta-llama/Llama-3.2-3B-Instruct")
    p.add_argument("--out", default="data/lora/ragh-tutor")
    p.add_argument("--epochs", type=int, default=3)
    p.add_argument("--batch", type=int, default=1)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--lora_r", type=int, default=16)
    p.add_argument("--lora_alpha", type=int, default=32)
    p.add_argument("--min_rating", type=int, default=1, help="train only on rating >= this")
    train(p.parse_args())
