import json
import torch
from pathlib import Path
from datasets import Dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from trl import SFTTrainer
import config


class FinetuneEngine:
    def __init__(self, db, output_dir=None):
        self.db = db
        self.output_dir = output_dir or str(config.MODEL_DIR)

    def prepare_training_data(self, pair_ids=None):
        pairs = self.db.list_training_pairs()
        if pair_ids:
            pairs = [p for p in pairs if p["id"] in pair_ids]

        data = []
        for p in pairs:
            messages = [
                {"role": "system", "content": "你是一个知识库助手，请准确回答用户的问题。"},
                {"role": "user", "content": p["question"]},
                {"role": "assistant", "content": p["answer"]}
            ]
            data.append({"messages": json.dumps(messages, ensure_ascii=False)})

        dataset = Dataset.from_list(data)
        split = dataset.train_test_split(test_size=0.1, seed=42)
        return split

    def train(self, model_name, base_model=None, epochs=None, lora_rank=None, batch_size=None, lr=None):
        base_model = base_model or config.DEFAULT_BASE_MODEL
        epochs = epochs or config.DEFAULT_EPOCHS
        lora_rank = lora_rank or config.DEFAULT_LORA_RANK
        batch_size = batch_size or config.DEFAULT_BATCH_SIZE
        lr = lr or config.DEFAULT_LR

        output_path = str(Path(self.output_dir) / model_name)

        tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        bnb_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_compute_dtype=torch.float16,
            bnb_4bit_use_double_quant=True,
        )

        model = AutoModelForCausalLM.from_pretrained(
            base_model,
            quantization_config=bnb_config,
            device_map="auto",
            trust_remote_code=True
        )
        model = prepare_model_for_kbit_training(model)

        lora_config = LoraConfig(
            r=lora_rank,
            lora_alpha=32,
            target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM"
        )
        model = get_peft_model(model, lora_config)

        split = self.prepare_training_data()

        def formatting_func(examples):
            return [tokenizer.apply_chat_template(json.loads(msg), tokenize=False) for msg in examples["messages"]]

        training_args = TrainingArguments(
            output_dir=output_path,
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            gradient_accumulation_steps=4,
            learning_rate=lr,
            weight_decay=0.01,
            warmup_ratio=0.1,
            lr_scheduler_type="cosine",
            fp16=True,
            logging_steps=10,
            save_strategy="epoch",
            evaluation_strategy="epoch",
            load_best_model_at_end=True,
            report_to="none"
        )

        trainer = SFTTrainer(
            model=model,
            args=training_args,
            train_dataset=split["train"],
            eval_dataset=split["test"],
            formatting_func=formatting_func,
            tokenizer=tokenizer,
            max_seq_length=1024
        )

        trainer.train()
        trainer.save_model(output_path)
        tokenizer.save_pretrained(output_path)

        return output_path

    def list_models(self):
        models = []
        model_dir = Path(self.output_dir)
        if model_dir.exists():
            for p in model_dir.iterdir():
                if p.is_dir() and (p / "adapter_config.json").exists():
                    models.append({"name": p.name, "path": str(p)})
        return models
