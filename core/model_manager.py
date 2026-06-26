import os
import shutil
import json
from pathlib import Path
import config


class ModelManager:
    def __init__(self, custom_model_dir=None, fine_tuned_dir=None):
        self.custom_model_dir = Path(custom_model_dir or config.CUSTOM_MODEL_DIR)
        self.fine_tuned_dir = Path(fine_tuned_dir or config.MODEL_DIR)
        self.custom_model_dir.mkdir(parents=True, exist_ok=True)
        self.fine_tuned_dir.mkdir(parents=True, exist_ok=True)

    def list_custom_models(self):
        models = []
        if self.custom_model_dir.exists():
            for p in self.custom_model_dir.iterdir():
                if p.is_dir():
                    info = self._get_model_info(p)
                    if info:
                        info["type"] = "custom"
                        models.append(info)
        return models

    def list_finetuned_models(self):
        models = []
        if self.fine_tuned_dir.exists():
            for p in self.fine_tuned_dir.iterdir():
                if p.is_dir() and (p / "adapter_config.json").exists():
                    info = self._get_model_info(p)
                    if info:
                        info["type"] = "finetuned"
                        models.append(info)
        return models

    def list_all_models(self):
        return self.list_custom_models() + self.list_finetuned_models()

    def _get_model_info(self, path):
        if not path.exists():
            return None

        info = {
            "name": path.name,
            "path": str(path),
            "size": self._get_dir_size(path),
        }

        config_file = path / "config.json"
        if config_file.exists():
            try:
                with open(config_file, "r") as f:
                    cfg = json.load(f)
                info["model_type"] = cfg.get("model_type", "unknown")
                info["architectures"] = cfg.get("architectures", [])
            except Exception:
                pass

        adapter_config = path / "adapter_config.json"
        if adapter_config.exists():
            try:
                with open(adapter_config, "r") as f:
                    cfg = json.load(f)
                info["base_model"] = cfg.get("base_model_name_or_path", "")
                info["lora_rank"] = cfg.get("r", 0)
            except Exception:
                pass

        return info

    def _get_dir_size(self, path):
        total = 0
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
        return total

    def save_uploaded_model(self, file, model_name):
        model_dir = self.custom_model_dir / model_name
        model_dir.mkdir(parents=True, exist_ok=True)

        filename = file.filename
        file_path = model_dir / filename
        file.save(str(file_path))

        return str(file_path)

    def save_uploaded_model_files(self, files, model_name):
        model_dir = self.custom_model_dir / model_name
        model_dir.mkdir(parents=True, exist_ok=True)

        saved_files = []
        for file in files:
            if file.filename:
                file_path = model_dir / file.filename
                file.save(str(file_path))
                saved_files.append(str(file_path))

        return saved_files

    def delete_model(self, model_name, model_type="custom"):
        if model_type == "custom":
            model_dir = self.custom_model_dir / model_name
        else:
            model_dir = self.fine_tuned_dir / model_name

        if model_dir.exists():
            shutil.rmtree(model_dir)
            return True
        return False

    def get_model_path(self, model_name, model_type="custom"):
        if model_type == "custom":
            return str(self.custom_model_dir / model_name)
        else:
            return str(self.fine_tuned_dir / model_name)

    def validate_model_files(self, path):
        path = Path(path)
        required_files = ["config.json"]
        has_weights = any(path.glob("*.safetensors")) or any(path.glob("*.bin"))

        missing = []
        for f in required_files:
            if not (path / f).exists():
                missing.append(f)

        return {
            "valid": len(missing) == 0 and has_weights,
            "missing": missing,
            "has_weights": has_weights
        }
