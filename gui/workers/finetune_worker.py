from PySide6.QtCore import QObject, Signal
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
import config
from core.database import DatabaseManager
from core.finetune_engine import FinetuneEngine


class FinetuneWorker(QObject):
    progress = Signal(int, int)  # (current_epoch, total_epochs)
    log_message = Signal(str)
    finished = Signal(str)  # output_path
    error = Signal(str)

    def __init__(self, training_pairs, model_name, base_model, epochs, lora_rank, batch_size, lr):
        super().__init__()
        self.training_pairs = training_pairs
        self.model_name = model_name
        self.base_model = base_model
        self.epochs = epochs
        self.lora_rank = lora_rank
        self.batch_size = batch_size
        self.lr = lr
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        try:
            db = DatabaseManager(str(config.DB_PATH))
            job_id = db.create_finetune_job(
                self.model_name, self.base_model,
                len(self.training_pairs), self.epochs, self.lora_rank
            )
            db.update_finetune_job(job_id, status="training")

            self.log_message.emit(f"开始微调: {self.model_name}")
            self.log_message.emit(f"基础模型: {self.base_model}")
            self.log_message.emit(f"训练样本: {len(self.training_pairs)}")
            self.log_message.emit(f"Epochs: {self.epochs}, LoRA Rank: {self.lora_rank}")

            engine = FinetuneEngine()

            def progress_callback(current_epoch, total_epochs):
                self.progress.emit(current_epoch, total_epochs)
                self.log_message.emit(f"Epoch {current_epoch}/{total_epochs} 完成")

            output_path = engine.train(
                training_pairs=self.training_pairs,
                model_name=self.model_name,
                base_model=self.base_model,
                lora_rank=self.lora_rank,
                epochs=self.epochs,
                batch_size=self.batch_size,
                learning_rate=self.lr,
                progress_callback=progress_callback
            )

            db.update_finetune_job(job_id, status="completed", output_path=output_path)
            self.log_message.emit(f"微调完成: {output_path}")
            self.finished.emit(output_path)

        except Exception as e:
            try:
                db.update_finetune_job(job_id, status="failed", error_message=str(e))
            except Exception:
                pass
            self.error.emit(str(e))
