"""
Script de diagnostic — inspecte la structure interne de Chronos2Pipeline.
Exécuter depuis HotStart/ :
    python debug_chronos.py
"""
import torch

print("=== Chargement Chronos2Pipeline ===")
from chronos import Chronos2Pipeline
pipeline = Chronos2Pipeline.from_pretrained("amazon/chronos-2", device_map="cpu")
model = pipeline.model

print(f"\ntype(pipeline)       : {type(pipeline)}")
print(f"type(pipeline.model) : {type(model)}")

# ── Tokenizer ──────────────────────────────────────────────────────────────
print("\n=== Tokenizer ===")
if hasattr(pipeline, "tokenizer"):
    tok = pipeline.tokenizer
    print(f"type(tokenizer) : {type(tok)}")
    methods = [m for m in dir(tok) if not m.startswith("_")]
    print(f"méthodes        : {methods}")
else:
    print("pipeline.tokenizer : ABSENT")

# ── Model interne ──────────────────────────────────────────────────────────
print("\n=== Model interne ===")
if hasattr(model, "model"):
    print(f"type(model.model) : {type(model.model)}")
    print(f"model.model classe: {model.model.__class__.__name__}")
else:
    print("model.model : ABSENT")
    print(f"attributs model : {[a for a in dir(model) if not a.startswith('_')][:20]}")

# ── Test tokenizer context_input_transform ─────────────────────────────────
ctx = torch.randn(1, 64)
print("\n=== Test tokenizer methods ===")

for method_name in ["context_input_transform", "input_transform"]:
    if hasattr(pipeline, "tokenizer") and hasattr(pipeline.tokenizer, method_name):
        try:
            result = getattr(pipeline.tokenizer, method_name)(ctx)
            print(f"{method_name}({ctx.shape}) → {[type(r).__name__ + str(getattr(r,'shape','')) for r in result]}")
        except Exception as e:
            print(f"{method_name} → ERREUR : {e}")
    else:
        print(f"{method_name} : ABSENT")

# ── Test label_input_transform ─────────────────────────────────────────────
for method_name in ["label_input_transform", "output_transform"]:
    if hasattr(pipeline, "tokenizer") and hasattr(pipeline.tokenizer, method_name):
        print(f"{method_name} : PRÉSENT")
    else:
        print(f"{method_name} : ABSENT")

# ── Test forward pass ──────────────────────────────────────────────────────
print("\n=== Test forward pass ===")
try:
    ctx_t = torch.zeros(1, 10, dtype=torch.long)
    tgt_t = torch.zeros(1,  4, dtype=torch.long)
    out = model.model(input_ids=ctx_t, labels=tgt_t)
    print(f"model.model(input_ids, labels) → loss={out.loss}")
except Exception as e:
    print(f"model.model(input_ids, labels) → ERREUR : {e}")


# ── Explorer Chronos2Model en profondeur ───────────────────────────────────
print("\n=== Attributs complets Chronos2Model ===")
all_attrs = [a for a in dir(model) if not a.startswith("_")]
print(all_attrs)

print("\n=== chronos_config ===")
if hasattr(model, "chronos_config"):
    cc = model.chronos_config
    print(f"type : {type(cc)}")
    print(f"attrs: {[a for a in dir(cc) if not a.startswith('_')]}")
    if hasattr(cc, "__dict__"):
        print(f"dict : {cc.__dict__}")

print("\n=== base_model ===")
bm = model.base_model
print(f"type(base_model)         : {type(bm)}")
print(f"base_model is model      : {bm is model}")
print(f"base_model_prefix        : {model.base_model_prefix}")

print("\n=== Sous-modules du modèle ===")
for name, module in model.named_children():
    print(f"  {name}: {type(module).__name__}")

print("\n=== Test forward pass direct ===")
ctx = torch.zeros(1, 10, dtype=torch.long)
tgt = torch.zeros(1,  4, dtype=torch.long)
for call in [
    ("model(ctx)",                   lambda: model(ctx)),
    ("model(ctx, tgt)",              lambda: model(ctx, tgt)),
    ("model(input_ids=ctx)",         lambda: model(input_ids=ctx)),
    ("model(input_ids=ctx,labels=tgt)", lambda: model(input_ids=ctx, labels=tgt)),
]:
    try:
        out = call[1]()
        print(f"{call[0]} → type={type(out).__name__} | has loss={hasattr(out,'loss')}")
    except Exception as e:
        print(f"{call[0]} → ERREUR: {e}")


# ── Signature forward ──────────────────────────────────────────────────────
print("\n=== Signature model.forward ===")
import inspect
try:
    sig = inspect.signature(model.forward)
    print(f"forward({sig})")
except Exception as e:
    print(f"ERREUR signature: {e}")

# ── Contenu Chronos2Output ─────────────────────────────────────────────────
print("\n=== Chronos2Output.loss (sans target) ===")
ctx32  = torch.zeros(1, 32)
mask32 = torch.ones(1, 32)
tgt16  = torch.randn(1, 16)
tgt32  = torch.randn(1, 32)
out    = model(ctx32)
print(f"out.loss     : {out.loss}")
print(f"out fields   : {[f for f in dir(out) if not f.startswith('_')]}")

# ── Test target comme keyword ──────────────────────────────────────────────
print("\n=== Tests avec target ===")
for label, call in [
    ("model(ctx, target=tgt16)",        lambda: model(ctx32, target=tgt16)),
    ("model(ctx, target=tgt32)",        lambda: model(ctx32, target=tgt32)),
    ("model(ctx, mask, tgt16)",         lambda: model(ctx32, mask32, tgt16)),
    ("model(ctx, mask, target=tgt16)",  lambda: model(ctx32, mask32, target=tgt16)),
    ("model(ctx, mask, tgt32)",         lambda: model(ctx32, mask32, tgt32)),
    ("model(context=ctx,target=tgt16)", lambda: model(context=ctx32, target=tgt16)),
]:
    try:
        out = call()
        loss_val = out.loss if hasattr(out, "loss") else "N/A"
        print(f"OK  {label} → loss={loss_val}")
    except Exception as e:
        print(f"ERR {label} → {e}")

print("\n=== Fin diagnostic ===")
