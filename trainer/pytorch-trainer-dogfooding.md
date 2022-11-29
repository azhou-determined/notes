# PyTorch Trainer - Dogfooding
- [Overview](#overview)
    - [Motivation](#motivation)
- [Technical Details](#technical-details)
    - [Breaking Changes](#breaking-changes)
- [API Specifications](#api-specifications)
    - [PyTorchTrial](#pytorchtrial)
    - [pytorch.init()](#pytorchinit---pytorchcontext)
    - [trainer.fit()](#trainerfit)
    - [trainer.configure_profiler()](#trainerconfigureprofiler)
- [Walkthrough](#walkthrough)
    - [Define PyTorchTrial](#1-define-a-pytorchtrial)
    - [Initialize Trainer](#2-initialize-your-pytorchtrial-and-the-trainer)
    - [Local Training](#3-local-training-run-your-training-script-locally)
    - [Local + Distributed Training](#local--distributed-training)
    - [Local Training - Test Mode](#local-training---test-mode)
    - [On-cluster training](#4-on-cluster-submit-your-trial-for-training)
- [Discussion](#discussion)

## Overview
---
This document serves as the dogfooder's guide to PyTorch Trainer, detailing the major changes and features and some points for discussion. I've included a rough walkthrough and example, but I hope to see more organic usages of Trainer API for higher quality feedback.

Thank you, and happy dogfooding!

### Motivation
The goal of Trainer APIs is to provide an interface for all of Determined's automatic training features that is minimally-invasive to native training code, and feels natural to use -- whether on-cluster with Determined, or off-cluster locally. With that in mind, I hope you'll find that implementing a training script with PyTorch Trainer is faster to develop and easier to debug.

## Technical Details
---
This feature was a major refactor of all Determined PyTorch internals and touches all PyTorch codepaths under `harness`. All `PyTorch` codepaths now call the PyTorch Trainer API, either explicitly through new training code, or internally under legacy training scripts (`harness.py`).

### Breaking Changes
- `records_per_epoch` has been dropped from all codepaths (legacy and new). Previously we were using this value in the workload sequencer to estimate epoch lengths before the dataloader was initialized. During training, the internal training loop logic used the chief worker's epoch length to do all important calculations (when to step LR schedulers, optimizers, call callbacks), so this change seemed like an easy win.
- `average_training_metrics` will no longer be configurable. This clunky value was used by `PyTorchContext` and set by default to false. After some discussions around the value of this option, we couldn't think of a good reason to complicate the new codepaths when it's not a feature users really want. We always average training metrics now.
- `min_checkpoint_period`/`min_validation_period` are no longer relative to last validation, and are explicit periods relative to start of training. They have been appropriately renamed (`checkpoint_period`/`validation_period`) in the Trainer API, but legacy names are still used in the experiment config.
- `num_gpus`, a previously public value on `PyTorchContext`, is now private. I'm not aware of a real use case for this, and it seems like we accidentally made it public before.

## API Specifications
---
### PyTorchTrial
Users must still implement a Trial class for use with Trainer API. This abstraction was kept because Determined needs to hook into optimizer step and train batch calls. Though it introduces Determined-specific code to users' PyTorch training, this is a minimal amount of boilerplate needed for the features we support. I've come to think of `PyTorchTrial` as a way of organizing training code rather than rewriting or adding additional code overhead. 

The API definition for `PyTorchTrial` remains the same, the only difference being users can now instantiate their own Trial object (see below).

### pytorch.init() -> PyTorchContext
A major quirk with our Trial code today is the inability for users to instantiate a trial class themselves. Due to complex interactions and dependencies between context and object lifetimes, we can't easily untangle these abstractions today. So, we provide users with the context object to use as they wish.
```python
def init(
    hparams: Optional[Dict] = None, 
    distributed: Optional[core.DistributedContext] = None
) -> Iterator[pytorch.PyTorchTrialContext]:
```
- `hparams["global_batch_size"]` is a required parameter for local training. When training on-cluster, this value (along with other hyperparameters) will be pulled from the experiment config.
- `distributed` context can be optionally passed in for custom/advanced use cases (see Distributed Training)

### trainer.fit()
The main training loop is Trainer's `fit` call, named fit because it is a common name given to this type of managed training loop (see PyTorchLightning, Ray Train, etc.).
```python
def fit(
    self,
    checkpoint_period: Optional[pytorch.TrainUnit],
    validation_period: Optional[pytorch.TrainUnit],
    max_length: Optional[pytorch.TrainUnit],
    reporting_period: Optional[pytorch.TrainUnit],
    average_aggregated_gradients: Optional[bool],
    aggregation_frequency: Optional[int],
    checkpoint_policy: Optional[str],
    test_mode: Optional[bool],
) -> None:
```
- `TrainUnit` specifies a type of training step of either `Batch()`, `Epoch()`, or `Record()` type. You can mix and match step types for different training step configurations.
- `checkpoint_period`/`validation_period` (previously `min_checkpoint_period`/`min_validation_period`) are explicit periods to checkpoint and validate. If not specified, these default to `sys.maxsize`. In legacy codepaths, these values will be pulled from the experiment config (if running on-cluster). 
- `reporting_period` (previously `scheduling_unit`) specifies the period to report metrics and check for pre-emption. If not specified, this value defaults to `sys.maxsize`
- `max_length` specifies the maximum length to train for. This value is only applicable in local training mode. On-cluster training will instead respect the searcher's length.
- `average_aggregated_gradients` (previously in the expconf) specifies whether to average gradients during training, and defaults to `True` 
- `aggregation_frequency` (previously in the expconf) specifies how often to aggregate gradients during training and defaults to `1`
- `checkpoint_policy=all|best|none` specifies when to checkpoint during searcher validations. For local training mode (searcherless), this value will be overridden to `all` because our current implementation of this config does not account for checkpoint GC without a searcher metric configured. 
- `test_mode` will train for only one batch, and is only supported in local-training mode. `det e create --local --test` traverses this codepath.


### trainer.configure_profiler()
This configures the Determined profiler and must be called before `trainer.fit()`. Any additional calls will override the previous configuration.
```python
def configure_profiler(
    self, 
    sync_timings: bool, 
    enabled: bool, 
    begin_on_batch: int, 
    end_after_batch: int
) -> None:
```
- All parameters mirror existing configurations from the expconf and should have the same behavior. See `Discussions` section for more comments on this feature.


## Walkthrough
---
This is a walkthrough detailing how to use the new PyTorch Trainer API. A full example for training with PyTorch Trainer can be found [here](./examples/); it was not included in the main repo's `examples` directory because it is not specific to any example and we already have too many examples. Following dogfooding feedback, an official example may be added.
### 0. Setup
Checkout the feature branch (`determined/feature/pytorch-trainer`) and make sure it is up to date.
### 1. Define a `PyTorchTrial`
Nothing new here. Though it's worth noting that since you instantiate the `Trial` and `TrialContext` objects yourself, you no longer have to initilize and wrap models and optimizers inside of the `Trial.__init__` method. You are free to pass in a wrapped model to `Trial.__init__` if you wish.
```python
class MyPyTorchTrial(pytorch.PyTorchTrial):
    def __init__(self, context: PyTorchTrialContext) -> None:
        self.context = context
        self.model = context.wrap_model(nn.Sequential(
            nn.Linear(9216, 128),
        ))
        self.optimizer = context.wrap_optimizer(torch.optim.Adadelta(
            self.model.parameters(), lr=0.1)
        )

    def train_batch(
            self, batch: pytorch.TorchData, epoch_idx: int, batch_idx: int
    ) -> Dict[str, torch.Tensor]:
        ...
        output = self.model(data)
        loss = torch.nn.functional.nll_loss(output, labels)

        self.context.backward(loss)
        self.context.step_optimizer(self.optimizer)

        return {"loss": loss}

    def evaluate_batch(self, batch: pytorch.TorchData) -> Dict[str, Any]:
        ...
        return {"validation_loss": validation_loss, "accuracy": accuracy}

    def build_training_data_loader(self) -> DataLoader:
        ...
        return DataLoader(train_set)

    def build_validation_data_loader(self) -> DataLoader:
        ...
        return DataLoader(validation_set)
```

### 2. Initialize your `PyTorchTrial` and the `Trainer`
```python
from determined import pytorch

def main():
    # pytorch.init() returns a PyTorchTrialContext for instantiating PyTorchTrial
    with det.pytorch.init() as train_context:
        trial = MyPyTorchTrial(train_context)
        trainer = det.pytorch.Trainer(trial, train_context)
        
        # (Optional) Configure Determined profiler before calling .fit()
        trainer.configure_profiler(enabled=True,
                                   sync_timings=True,
                                   begin_on_batch=0,
                                   end_after_batch=10)
        
        # Train
        trainer.fit(
            checkpoint_period=pytorch.Batch(10),
            validation_period=pytorch.Batch(10),
        )


if __name__ == "__main__":
    # Configure logging here instead of through the expconf
    logging.basicConfig(level=logging.INFO, format=det.LOG_FORMAT)
    main()

```

### 3. (Local training) Run your training script locally
Training scripts using PyTorch Trainer can be run locally, no experiment config file needed. Be sure to specify `max_length` in the `.fit()` call, and `global_batch_size` in `pytorch.init()`.
```diff
+ with det.pytorch.init(hparams={"global_batch_size": 32}) as train_context:
      trial = MyPytorchTrial(train_context)
      trainer = det.pytorch.Trainer(trial, train_context)
      trainer.fit(
+         max_length=pytorch.Epoch(1),
          checkpoint_period=pytorch.Batch(10),
          validation_period=pytorch.Batch(10),
    )
```
Run this script directly (`python3 train.py`), or inside of a Jupyter notebook.

### Local + Distributed Training
Local training can utilize multiple GPUs on a single node with a few modifications to the above code. Note: this is not currently supported as a first-class feature, see Discussions.

Currently only Horovod and PyTorch Distributed backends are supported.
```diff
  def main():
+     # Initialize distributed backend before pytorch.init()
+     dist.init_process_group(backend="gloo|nccl")
  
+     # Set flag used by internal PyTorch training loop
+     os.environ["USE_TORCH_DISTRIBUTED"] = "true"
  
+     # Initialize DistributedContext specifying chief IP
      with det.pytorch.init(
              hparams={"global_batch_size": 32},
+             distributed=core.DistributedContext.from_torch_distributed  (chief_ip="localhost")
      ) as train_context:
          trial = MNistTrial(train_context)
          trainer = det.pytorch.Trainer(trial, train_context)
          trainer.fit(
              max_length=pytorch.Epoch(1),
              checkpoint_period=pytorch.Batch(10),
              validation_period=pytorch.Batch(10),
          )
```

Call your distributed backend's launcher directly:
`torchrun --nproc_per_node=4 train.py`

### Local Training - Test Mode
Helpful for debugging code, PyTorch Trainer accepts a `test_mode` parameter which, if true, trains and validates your training code for only one batch, then exits.
```diff
  trainer.fit(
              max_length=pytorch.Epoch(1),
              checkpoint_period=pytorch.Batch(10),
              validation_period=pytorch.Batch(10),
+             # Train and validate 1 batch, then exit.
+             test_mode=True
          )
```
This is the same codepath as `det e create det.yaml . --local --test`.

### 4. (On-cluster) Submit your trial for training
Create a `.yaml`. Must contain searcher configuration, global batch size, and entrypoint.
``` 
name: my_pytorch_trainer_trial
hyperparameters:
  global_batch_size: 32
searcher:
  name: single
  metric: validation_loss
  max_length:
    batches: 937 
resources:
  slots_per_trial: 8
entrypoint: python3 -m determined.launch.torch_distributed python3 train.py
```

Submit to cluster as usual: `det e create det.yaml .`


## Discussion
---
This section details known limitations and possible directions for future work. Feedback from dogfooding will also be aggregated here.
- `det_profiler` is a very clunky object in the Trainer API today. It had to be supported for backwards compatibility reasons, but until we have a clearer picture of `det_profiler`'s role, I decided to keep the complexity out of Trainer API as much as possible. We explored exposing the Determined profiler as a first-class feature of Core API, but without more defined use cases and goals, integrating this feature cleanly into Trainer API was pushed out of scope. This work will instead be a part of the upcoming 'Unified Metrics' project.
- We do not expose metrics out of `trainer.fit()`. The only way to get metrics during training is via `on_training_workload_end` callbacks. A few ideas for future directions in supporting this:
    - Returning a large object containing all the training and validation metrics, checkpoints created, and other training metadata. There are concerns that this may lead to a non-trivial increase in RAM usage, but this is exactly how [Ray Train](https://docs.ray.io/en/latest/ray-air/package-ref.html#ray.air.result.Result) solves this problem.
    - Write metrics to a file and stream from file when needed. This could be a separate API, or another call to `trainer`
    - Expose internal training step calls (something like `train_for(num_steps)`)
- True epoch-based training was decidedly out-of-scope for this project. Further discussions need to be had around how we want to support this, due to complexities around stepping LR schedulers and optimizers on epoch boundaries. The current implementation of the training loop is flexible to support true epoch-based training if we decide to pursue it.
- The technical integration of local and non-local training is not perfect (some configs in `trainer.fit()` are only applicable in local training mode, others only relevant on-cluster). I believe we have a solid foundation to build future iterations on local training support, but more discussions should be had on the scope of local training functionality (ie: supporting searcherless trials and checkpointing policies)
- Local training mode + distributed training (see Walkthrough) can be done, but is not currently supported as a first-class feature. Additional configuration is needed for a seamless experience, and future work may involve:
    - Providing a barebones launch layer that includes the cluster-independent benefits (like fault tolerance, automatic distributed training setup, wrappers for aggregating logs, etc.) for use with bring-your-own launchers
    - Exposing Determined launch layers for local training use
