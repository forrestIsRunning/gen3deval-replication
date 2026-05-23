# Result Schema

## Manifest Row

```json
{
  "uid": "objaverse_uid",
  "category": "chair",
  "prompt": "A high-quality 3D model of a chair.",
  "source": "objaverse-lvis",
  "local_path": null
}
```

## Pair Row

```json
{
  "pair_id": "000001",
  "object_a": {"uid": "...", "prompt": "...", "category": "..."},
  "object_b": {"uid": "...", "prompt": "...", "category": "..."}
}
```

## Comparison Row

```json
{
  "pair_id": "000001",
  "dimension": "appearance",
  "winner": "A",
  "confidence": 0.74,
  "reason": "Object A has cleaner shape and more coherent textures.",
  "model": "qwen3-vl-plus"
}
```

`winner` must be `A`, `B`, or `tie`.
