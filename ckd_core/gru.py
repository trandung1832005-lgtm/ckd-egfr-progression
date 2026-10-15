"""GRU dự đoán eGFR 18/24/30/36M từ lịch sử 0/6/12M (PyTorch)."""
from __future__ import annotations

import copy
import random

import numpy as np
import torch
from torch import nn

from . import config as C

torch.set_num_threads(2)


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


class GRUForecaster(nn.Module):
    """GRU đọc chuỗi [eGFR đã chuẩn hóa, cờ quan sát, Δt]; đầu ra là phần dư cộng vào eGFR gần nhất."""

    def __init__(self, n_static: int, hidden=32, layers=1, dropout=0.2, static_dim=16, head_dim=32,
                 n_out=len(C.FUT_COLS)):
        super().__init__()
        self.gru = nn.GRU(3, hidden, layers, batch_first=True, dropout=dropout if layers > 1 else 0.0)
        self.n_static = n_static
        sd = 0
        if n_static > 0:
            sd = static_dim
            self.static = nn.Sequential(nn.Linear(n_static, sd), nn.ReLU(), nn.Dropout(dropout))
        self.head = nn.Sequential(nn.Linear(hidden + sd, head_dim), nn.ReLU(), nn.Dropout(dropout),
                                  nn.Linear(head_dim, n_out))

    def forward(self, seq, static, last):
        _, h = self.gru(seq)
        z = h[-1]
        if self.n_static > 0:
            z = torch.cat([z, self.static(static)], 1)
        return last.unsqueeze(1) + self.head(z)


def _tensors(batch, prep, use_clinical):
    static = batch["static"] if use_clinical else np.zeros((len(batch["seq"]), 0), np.float32)
    y = np.nan_to_num((batch["y"] - prep.egfr_mean) / prep.egfr_std, nan=0.0).astype(np.float32)
    return (torch.from_numpy(batch["seq"]), torch.from_numpy(static), torch.from_numpy(batch["last_scaled"]),
            torch.from_numpy(y), torch.from_numpy(batch["mask"].astype(np.float32)))


def predict(model: GRUForecaster, batch, prep, use_clinical: bool) -> np.ndarray:
    """Trả eGFR dự đoán theo đơn vị thật, chặn dưới ở 0."""
    model.eval()
    seq, st, last, _, _ = _tensors(batch, prep, use_clinical)
    with torch.no_grad():
        out = model(seq, st, last).numpy()
    return np.clip(out * prep.egfr_std + prep.egfr_mean, 0.0, None)


def masked_mae(pred, batch):
    mk = batch["mask"]
    return float(np.abs(pred[mk] - batch["y"][mk]).mean())


def train_one(hp: dict, prep, tr, va, seed: int, max_epochs=200, patience=25, verbose=False):
    """Huấn luyện trên Train, chọn checkpoint theo MAE Validation (đơn vị thật). Không đụng Test."""
    set_seed(seed)
    use_clinical = hp["use_clinical"]
    n_static = prep.n_static if use_clinical else 0
    model = GRUForecaster(n_static, hp["hidden"], hp["layers"], hp["dropout"], hp["static_dim"], hp["head_dim"])
    opt = torch.optim.AdamW(model.parameters(), lr=hp["lr"], weight_decay=hp["weight_decay"])
    seq, st, last, y, mk = _tensors(tr, prep, use_clinical)
    # Dòng không có đích nào được quan sát không đóng góp vào loss; bỏ để batch gọn hơn
    keep = torch.where(mk.sum(1) > 0)[0]
    n = len(keep)
    loss_fn = nn.SmoothL1Loss(reduction="none")
    best, best_state, best_ep, bad = float("inf"), None, 0, 0
    hist = {"train_loss": [], "val_mae": []}
    g = torch.Generator().manual_seed(seed)
    for ep in range(max_epochs):
        model.train()
        perm = keep[torch.randperm(n, generator=g)]
        tot, cnt = 0.0, 0.0
        for i in range(0, n, hp["batch_size"]):
            idx = perm[i:i + hp["batch_size"]]
            out = model(seq[idx], st[idx], last[idx])
            loss = (loss_fn(out, y[idx]) * mk[idx]).sum() / mk[idx].sum().clamp(min=1)
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()
            tot += float(loss.detach()) * float(mk[idx].sum())
            cnt += float(mk[idx].sum())
        vmae = masked_mae(predict(model, va, prep, use_clinical), va)
        hist["train_loss"].append(tot / max(cnt, 1))
        hist["val_mae"].append(vmae)
        if vmae < best - 1e-4:
            best, best_state, best_ep, bad = vmae, copy.deepcopy(model.state_dict()), ep, 0
        else:
            bad += 1
            if bad >= patience:
                break
    model.load_state_dict(best_state)
    return model, {"best_val_mae": best, "best_epoch": best_ep, "epochs_run": ep + 1, "history": hist}


SEARCH_SPACE = {
    "use_clinical": [True, False],
    "hidden": [16, 32, 64],
    "layers": [1, 2],
    "static_dim": [8, 16, 32],
    "head_dim": [16, 32, 64],
    "dropout": [0.0, 0.1, 0.2, 0.3],
    "lr": [3e-4, 1e-3, 3e-3],
    "weight_decay": [0.0, 1e-4, 1e-3],
    "batch_size": [32, 64],
}


def sample_configs(n: int, seed: int) -> list[dict]:
    rng = random.Random(seed)
    seen, out = set(), []
    while len(out) < n:
        hp = {k: rng.choice(v) for k, v in SEARCH_SPACE.items()}
        key = tuple(hp.values())
        if key not in seen:
            seen.add(key)
            out.append(hp)
    return out
