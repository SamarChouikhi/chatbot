from __future__ import annotations

import copy
import json
import logging
from dataclasses import asdict, dataclass
from datetime import date
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

import numpy as np
import pandas as pd
import torch

_log = logging.getLogger(__name__)

MONTHS_TO_MATURITY = 12


class RetrainOutcome(str, Enum):
    """Result of a MonthlyRetrainer.retrain() call — lets callers distinguish
    an actually-adopted checkpoint from a failure, instead of assuming every
    call produced a usable new model."""
    ADOPTED = "adopted"   # new checkpoint saved and now active for this device
    FAILED  = "failed"    # fine-tuning itself failed — state left untouched, retry next run


# ── Config protocol ───────────────────────────────────────────────────────────

class RetrainConfig(Protocol):
    """Minimal interface that any domain Config must satisfy for retraining."""
    timestamp_col:      str
    device_col:         str
    retrain_enabled:    bool
    fine_tune_epochs:   int
    fine_tune_lr:       float
    context_length:     int
    prediction_length:  int
    checkpoint_dir:     str
    retrain_state_file: str


# ── Per-device state ──────────────────────────────────────────────────────────

@dataclass
class DeviceRetrainState:
    months_accumulated:  int  = 0
    last_retrain_date:   str  = ""   # "YYYY-MM-DD"
    checkpoint_filename: str  = ""   # relative to checkpoint_dir
    is_mature:           bool = False


# ── Core class ────────────────────────────────────────────────────────────────

class MonthlyRetrainer:
    """
    Tracks per-device retraining state and fine-tunes Chronos monthly up to M12.

    Typical usage in a pipeline:

        retrainer = MonthlyRetrainer(config)
        base_state = retrainer.snapshot_base_weights(pipeline)

        for device_id in devices:
            device_df = df[df[device_col] == device_id]

            if retrainer.should_retrain(device_id, device_df):
                retrainer.retrain(device_id, device_df, pipeline)

            retrainer.load_checkpoint(device_id, pipeline)
            result = detector.detect(device_df)   # uses fine-tuned weights

            retrainer.restore_base_weights(pipeline, base_state)
    """

    def __init__(self, config: RetrainConfig) -> None:
        self.config       = config
        self._ckpt_dir    = Path(config.checkpoint_dir)
        self._state_path  = Path(config.retrain_state_file)
        self._states: dict[str, DeviceRetrainState] = {}
        self._load_states()

    # ── Public API ────────────────────────────────────────────────────────────

    def should_retrain(self, device_id: str, device_df: pd.DataFrame) -> bool:
        """
        Return True when:
          - retraining is enabled in config
          - the device has not reached M12 yet
          - at least one new month of data has arrived since the last retrain
        """
        if not self.config.retrain_enabled:
            return False
        state = self._states.get(device_id, DeviceRetrainState())
        if state.is_mature:
            _log.info("[%s] M12 atteint — retraining ignoré", device_id)
            return False
        months_now = self._count_months(device_df)
        if months_now > state.months_accumulated:
            _log.info(
                "[%s] nouveau mois détecté : M%d → M%d",
                device_id, state.months_accumulated, months_now,
            )
            return True
        _log.debug("[%s] aucun nouveau mois (M%d)", device_id, months_now)
        return False

    def retrain(
        self,
        device_id: str,
        device_df: pd.DataFrame,
        pipeline:  Any,
    ) -> RetrainOutcome:
        """
        Fine-tune Chronos on this device's accumulated data, then persist state.
        If fine-tuning itself fails (API mismatch), state is left untouched so
        the same month is retried on the next run.

        Retourne ADOPTED (nouveau checkpoint actif) ou FAILED (rien de
        persisté). L'appelant doit s'en servir plutôt que de supposer qu'un
        appel à retrain() a toujours produit un modèle utilisable.
        """
        months_now = self._count_months(device_df)
        _log.info("[%s] démarrage fine-tune — M%d", device_id, months_now)

        self._ckpt_dir.mkdir(parents=True, exist_ok=True)
        ckpt_filename = f"{device_id}_m{months_now:02d}.pt"
        ckpt_path     = self._ckpt_dir / ckpt_filename

        series_list = self._extract_series(device_df)
        if not self._fine_tune(pipeline, series_list, ckpt_path):
            _log.warning(
                "[%s] fine-tuning échoué — état NON mis à jour. "
                "Corrigez l'erreur puis supprimez retrain_state.json pour forcer un retry.",
                device_id,
            )
            return RetrainOutcome.FAILED

        is_mature = months_now >= MONTHS_TO_MATURITY

        old_state = self._states.get(device_id)
        if old_state and old_state.checkpoint_filename:
            old_ckpt = self._ckpt_dir / old_state.checkpoint_filename
            if old_ckpt.exists() and old_ckpt.name != ckpt_filename:
                old_ckpt.unlink(missing_ok=True)
                old_ckpt.with_name(old_ckpt.stem + "_metrics.json").unlink(missing_ok=True)
                _log.debug("[%s] ancien checkpoint supprimé : %s", device_id, old_ckpt.name)

        self._states[device_id] = DeviceRetrainState(
            months_accumulated  = months_now,
            last_retrain_date   = date.today().isoformat(),
            checkpoint_filename = ckpt_filename,
            is_mature           = is_mature,
        )
        self._save_states()

        if is_mature:
            _log.info("[%s] M12 atteint — modèle mature, aucun retraining ultérieur", device_id)
        else:
            _log.info("[%s] checkpoint sauvegardé : %s", device_id, ckpt_path.name)

        return RetrainOutcome.ADOPTED

    def load_checkpoint(self, device_id: str, pipeline: Any) -> bool:
        """
        Load the latest fine-tuned checkpoint for this device into the pipeline.
        Returns True if a checkpoint was loaded, False otherwise.
        """
        state = self._states.get(device_id)
        if state is None or not state.checkpoint_filename:
            return False

        ckpt_path = self._ckpt_dir / state.checkpoint_filename
        if not ckpt_path.exists():
            _log.warning("[%s] checkpoint introuvable : %s", device_id, ckpt_path)
            return False

        try:
            model      = self._get_model(pipeline)
            state_dict = torch.load(
                ckpt_path,
                map_location=next(model.parameters()).device,
                weights_only=True,
            )
            model.load_state_dict(state_dict, strict=False)
            _log.info(
                "[%s] checkpoint chargé : %s (M%d)",
                device_id, ckpt_path.name, state.months_accumulated,
            )
            return True
        except Exception as exc:  # noqa: BLE001
            _log.warning("[%s] chargement checkpoint échoué : %s", device_id, exc)
            return False

    def snapshot_base_weights(self, pipeline: Any) -> dict | None:
        """
        Clone the current model weights (CPU tensors) so they can be
        restored with restore_base_weights() after loading a device checkpoint.
        Returns None if the model is not accessible.
        """
        try:
            model = self._get_model(pipeline)
            return {k: v.cpu().clone() for k, v in model.state_dict().items()}
        except Exception as exc:  # noqa: BLE001
            _log.warning("snapshot_base_weights failed : %s", exc)
            return None

    def restore_base_weights(self, pipeline: Any, base_state: dict | None) -> None:
        """Restore the model to its pre-fine-tuning weights."""
        if base_state is None:
            return
        try:
            model  = self._get_model(pipeline)
            device = next(model.parameters()).device
            restored = {k: v.to(device) for k, v in base_state.items()}
            model.load_state_dict(restored, strict=False)
        except Exception as exc:  # noqa: BLE001
            _log.warning("restore_base_weights failed : %s", exc)

    def months_accumulated(self, device_id: str) -> int:
        return self._states.get(device_id, DeviceRetrainState()).months_accumulated

    def is_mature(self, device_id: str) -> bool:
        return self._states.get(device_id, DeviceRetrainState()).is_mature

    # ── Internal — data utils ─────────────────────────────────────────────────

    def _count_months(self, df: pd.DataFrame) -> int:
        ts = pd.to_datetime(df[self.config.timestamp_col])
        return int(ts.dt.to_period("M").nunique())

    def _extract_series(self, df: pd.DataFrame) -> list[np.ndarray]:
        """
        Return one numpy array per value column, sorted by timestamp.
        Uses config.value_cols if available, else falls back to numeric columns
        excluding identifier columns.
        """
        sorted_df  = df.sort_values(self.config.timestamp_col)
        value_cols = getattr(self.config, "value_cols", None)

        if value_cols:
            cols = [c for c in value_cols if c in sorted_df.columns]
        else:
            exclude = {self.config.timestamp_col, self.config.device_col}
            cols    = [
                c for c in sorted_df.select_dtypes(include="number").columns
                if c not in exclude
            ]

        min_length = self.config.prediction_length + 4
        series: list[np.ndarray] = []
        for col in cols:
            vals = sorted_df[col].dropna().to_numpy(dtype=np.float32)
            if len(vals) >= min_length:
                series.append(vals)
        return series

    # ── Internal — model access ───────────────────────────────────────────────

    @staticmethod
    def _get_model(pipeline: Any) -> Any:
        """
        Extract the underlying torch.nn.Module from a Chronos pipeline.
        Handles both Chronos2Pipeline (AutoGluon) and BaseChronosPipeline (Amazon).
        """
        if hasattr(pipeline, "model") and pipeline.model is not None:
            return pipeline.model
        raise AttributeError("Cannot locate a torch.nn.Module in this pipeline object.")

    # ── Internal — fine-tuning ────────────────────────────────────────────────

    def _fine_tune(
        self,
        pipeline:    Any,
        series_list: list[np.ndarray],
        ckpt_path:   Path,
    ) -> bool:
        """
        Fine-tune the Chronos model with a few gradient-descent epochs.

        Split temporel 80/20 par série :
          - 80 % premiers points → entraînement (gradient)
          - 20 % derniers points → validation (torch.no_grad, aucun gradient)

        Les métriques train_loss / val_loss par epoch sont persistées dans
        <ckpt>.stem + '_metrics.json' pour permettre la détection du sur-apprentissage
        et la traçabilité lors de la soutenance ou d'un audit.

        Returns True on success, False on any irrecoverable error.
        """
        try:
            model = self._get_model(pipeline)
        except AttributeError as exc:
            _log.warning("fine-tune: %s", exc)
            return False

        device    = next(model.parameters()).device
        optimizer = torch.optim.AdamW(
            model.parameters(),
            lr           = self.config.fine_tune_lr,
            weight_decay = 1e-2,
        )

        ctx_len  = self.config.context_length
        pred_len = self.config.prediction_length
        rng      = np.random.default_rng(seed=42)

        # Split temporel 80/20 : respecte l'ordre temporel (pas de fuite future→passé).
        # Si la tranche val est trop courte pour former une paire, elle est ignorée.
        train_series: list[np.ndarray] = []
        val_series:   list[np.ndarray] = []
        for s in series_list:
            split = max(pred_len + 2, int(len(s) * 0.8))
            train_series.append(s[:split])
            if len(s) - split >= pred_len + 2:
                val_series.append(s[split:])

        model.train()
        trained = False
        epoch_metrics: list[dict] = []

        for epoch in range(self.config.fine_tune_epochs):
            # ── Phase entraînement ───────────────────────────────────────────
            train_loss = 0.0
            n_train    = 0
            for series in train_series:
                pairs = _make_training_pairs(series, ctx_len, pred_len, rng)
                for ctx_np, tgt_np in pairs:
                    ctx = torch.tensor(ctx_np, dtype=torch.float32).unsqueeze(0).to(device)
                    tgt = torch.tensor(tgt_np, dtype=torch.float32).unsqueeze(0).to(device)

                    loss = _forward_loss(model, pipeline, ctx, tgt)
                    if loss is None:
                        continue

                    optimizer.zero_grad()
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()

                    train_loss += loss.item()
                    n_train    += 1
                    trained     = True

            # ── Phase validation (aucun gradient) ────────────────────────────
            val_loss = 0.0
            n_val    = 0
            if val_series:
                model.eval()
                with torch.no_grad():
                    for series in val_series:
                        pairs = _make_training_pairs(series, ctx_len, pred_len, rng)
                        for ctx_np, tgt_np in pairs[:8]:   # cap à 8 paires val/série
                            ctx = torch.tensor(ctx_np, dtype=torch.float32).unsqueeze(0).to(device)
                            tgt = torch.tensor(tgt_np, dtype=torch.float32).unsqueeze(0).to(device)
                            loss = _forward_loss(model, pipeline, ctx, tgt)
                            if loss is not None:
                                val_loss += loss.item()
                                n_val    += 1
                model.train()

            row: dict = {
                "epoch":      epoch + 1,
                "train_loss": round(train_loss / max(n_train, 1), 6),
                "val_loss":   round(val_loss   / max(n_val,   1), 6) if n_val else None,
                "n_train":    n_train,
                "n_val":      n_val,
            }
            epoch_metrics.append(row)

            if n_train:
                _log.info(
                    "[fine-tune] epoch %d/%d  train=%.4f  val=%s  batches=%d/%d",
                    epoch + 1, self.config.fine_tune_epochs,
                    row["train_loss"],
                    f"{row['val_loss']:.4f}" if row["val_loss"] is not None else "n/a",
                    n_train, n_val,
                )

        model.eval()

        if not trained:
            _log.warning("fine-tune: aucun batch valide — checkpoint non sauvegardé")
            return False

        torch.save(model.state_dict(), ckpt_path)

        # Persistance des métriques de validation pour la traçabilité
        metrics_path = ckpt_path.with_name(ckpt_path.stem + "_metrics.json")
        try:
            with metrics_path.open("w", encoding="utf-8") as fh:
                json.dump(
                    {
                        "checkpoint":       ckpt_path.name,
                        "n_train_series":   len(train_series),
                        "n_val_series":     len(val_series),
                        "epochs":           epoch_metrics,
                        "final_train_loss": epoch_metrics[-1]["train_loss"] if epoch_metrics else None,
                        "final_val_loss":   epoch_metrics[-1]["val_loss"]   if epoch_metrics else None,
                    },
                    fh, indent=2, ensure_ascii=False,
                )
            _log.info("[fine-tune] métriques sauvegardées : %s", metrics_path.name)
        except Exception as exc:
            _log.warning("[fine-tune] impossible de sauvegarder les métriques : %s", exc)

        return True

    # ── Internal — state persistence ──────────────────────────────────────────

    def _load_states(self) -> None:
        if not self._state_path.exists():
            return
        try:
            with self._state_path.open(encoding="utf-8") as fh:
                raw = json.load(fh)
            for dev_id, data in raw.items():
                self._states[dev_id] = DeviceRetrainState(**data)
            _log.debug("État retraining chargé : %d device(s)", len(self._states))
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            _log.warning("Impossible de lire %s : %s", self._state_path, exc)

    def _save_states(self) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        data = {dev: asdict(st) for dev, st in self._states.items()}
        with self._state_path.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        _log.debug("État retraining sauvegardé : %s", self._state_path)


# ── Module-level helpers ──────────────────────────────────────────────────────

def _make_training_pairs(
    series:  np.ndarray,
    ctx_len: int,
    pred_len: int,
    rng:     np.random.Generator,
) -> list[tuple[np.ndarray, np.ndarray]]:
    """
    Build (context, target) training pairs by sliding a window over the series.
    Capped at 16 pairs per series per epoch to limit GPU time.
    """
    min_pos  = 1
    max_pos  = len(series) - pred_len
    if max_pos < min_pos:
        return []

    stride    = max(1, pred_len // 2)
    positions = list(range(min_pos, max_pos + 1, stride))
    rng.shuffle(positions)

    pairs: list[tuple[np.ndarray, np.ndarray]] = []
    for pos in positions[:16]:
        ctx = series[max(0, pos - ctx_len):pos]
        tgt = series[pos:pos + pred_len]
        if len(ctx) >= 2 and len(tgt) == pred_len:
            pairs.append((ctx, tgt))
    return pairs


def _forward_loss(
    model:    Any,
    pipeline: Any,
    context:  torch.Tensor,
    target:   torch.Tensor,
) -> torch.Tensor | None:
    """
    Compute a differentiable training loss for Chronos2Model.

    Chronos2 forward signature (discovered via diagnostic):
        model(context, future_target=..., num_output_patches=...)
    The model uses patch-based encoding (output_patch_size=16) and computes
    a built-in quantile loss when future_target is provided.
    """
    import math

    dev = next(model.parameters()).device

    # ── Chronos2 : future_target API ─────────────────────────────────────────
    try:
        cfg        = model.chronos_config
        patch_size = cfg.output_patch_size          # 16
        pred_len   = target.shape[-1]
        num_patches = math.ceil(pred_len / patch_size)

        # Pad target to exact multiple of patch_size
        pad = num_patches * patch_size - pred_len
        future_target = (
            torch.nn.functional.pad(target, (0, pad)) if pad > 0 else target
        )

        out = model(
            context            = context.to(dev),
            future_target      = future_target.to(dev),
            num_output_patches = num_patches,
        )
        if hasattr(out, "loss") and out.loss is not None:
            return out.loss
        _log.debug("Chronos2 forward retourné loss=None")
    except Exception as exc:
        _log.debug("Chronos2 future_target failed : %s", exc)

    # ── Fallback : Chronos1 — context_input_transform ────────────────────────
    try:
        tokenizer = pipeline.tokenizer
        ctx_ids, ctx_mask, tok_state = tokenizer.context_input_transform(context)
        tgt_ids, _                   = tokenizer.label_input_transform(target, tok_state)
        hf  = model.model
        out = hf(
            input_ids      = ctx_ids.to(dev),
            attention_mask = ctx_mask.to(dev),
            labels         = tgt_ids.to(dev),
        )
        if hasattr(out, "loss") and out.loss is not None:
            return out.loss
    except Exception as exc:
        _log.debug("Chronos1 tokenizer fallback failed : %s", exc)

    _log.warning(
        "Fine-tuning : aucune stratégie n'a retourné de loss — "
        "pipeline opérationnel sans checkpoint fine-tuné."
    )
    return None
