# Searcher Context Removal

Determined as a training platform was built around hyperparameter search. Searcher context is an artifact of that assumption, which is no longer valid.

The searcher context in training code maintains a tight control over the training loop. It enables some niche features (dynamic checkpointing/validation) while preventing us from building more practical ones (external training integrations like PyTorch Lightning, Huggingface, etc., better local training). 

Most (data needed here, I remember some data like 90% being surfaced somewhere, but I can't find it) trials users run are single-searcher, which effectively means no searcher. Of the trials using search, all except ASHA do not even need a searcher context.

## Deprecating Searcher Context

Some things currently depend on the searcher context and need to be implemented differently. Existing training needs to work and we need to make things backwards-compatible.

- Progress reports: currently experiment progress reporting (rendered in the web UI and other places) is implemented as part of searcher operations (`searcher_op.report_progress`) 
  - Report progress as a fraction
  - Default progress calculations for experiments
  - Core API + Trial API changes
- Deprecate `max_length` 
  - Trial API changes to support training length specified in user code
    - PyTorchTrial/Trainer API: easy
    - TFKeras: TBD
    - Deepspeed: TBD, deprecate?
  - Backwards compatibility: "fake" searcher operations for `max_length`
- Refactor searchers
  - Configurable pre-emption 
    - Single, grid, random: no changes needed
    - ASHA: Stopping by time? (TBD)
    - Backend changes for master-side searchers
  - Custom searcher, Deepspeed autotune: TBD, deprecate?

## Keras Trainer

Once the searcher context dependency is removed, we can build a better "Trainer API" for Keras. 

- `model.fit`-like training integration
- Native Keras distributed training

## Python Searchers

Python-side searchers. Depends on searcher context removal and streaming updates. 
