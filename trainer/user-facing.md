# PyTorch Trainer API

### Overview
Trainer API provides an interface for all of Determined's automatic training features that is minimally-invasive to native training code, and feels natural to use -- whether on-cluster with Determined, or off-cluster locally.

PyTorch Trainer introduces local training mode which can be run directly on any machine without any cluster setup. With some additional configuration, the same training code can be submitted to a cluster.


## Walkthrough
This is a walkthrough detailing how to use the new PyTorch Trainer API. A full example for training with PyTorch Trainer can be found [here](./examples/); it was not included in the main repo's `examples` directory because it is not specific to any example and we already have too many examples. Following dogfooding feedback, an official example may be added.
### 0. Setup
Checkout the feature branch (`determined/feature/pytorch-trainer`) and make sure it is up to date.
### 1. Define a `PyTorchTrial`
Nothing new here. Though it's worth noting that since you instantiate the `Trial` and `TrialContext` objects yourself, you no longer have to initilize and wrap models and optimizers inside of the `Trial.__init__` method. You are free to pass in a wrapped model to `Trial.__init__` if you wish.
```python
class MyPyTorchTrial(pytorch.PyTorchTrial):
    def __init__(self, context: PyTorchTrialContext, hparams: Dict) -> None:
        self.context = context
        self.model = context.wrap_model(nn.Sequential(
            nn.Linear(9216, 128),
        ))
        self.optimizer = context.wrap_optimizer(torch.optim.Adadelta(
            self.model.parameters(), lr=hparams["lr"])
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
+ hparams = {"global_batch_size": 32, "lr": 0.02}
+ expconf = yaml.safe_load(pathlib.Path("./det.yaml").read_text())

# hparams and exp_conf are optional. Only needed by init() if training code calls
# context.get_hparams() or context.get_experiment_config()
+ with det.pytorch.init(hparams=hparams, exp_conf=expconf) as train_context:
      # (Optional) Preferred way to access hparams in the Trial
+     trial = MyPytorchTrial(train_context, hparams)
      trainer = det.pytorch.Trainer(trial, train_context)
      trainer.fit(
+         max_length=pytorch.Epoch(1),
          checkpoint_period=pytorch.Batch([2,5]),
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
+       distributed=core.DistributedContext.from_torch_distributed  (chief_ip="localhost")
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
### 3.5. Preparing your local training code for cluster deployment
Once the training script is satisfactory with local training, we're ready to submit it to a cluster. This code should allow for local and cluster training with no code changes.

```diff
  def main():
+   local = det.get_cluster_info() is None
+   if local:
+       # (Optional) Initialize distributed backend before pytorch.init()
+       dist.init_process_group(backend="gloo|nccl")
+       # Set flag used by internal PyTorch training loop
+       os.environ["USE_TORCH_DISTRIBUTED"] = "true"
+       distributed_context = core.DistributedContext.from_torch_distributed  (chief_ip="localhost")
+       # (Optional) Pass in an exp conf and instance of hparams if training code needs it
+       expconf = yaml.safe_load(pathlib.Path("./config.yaml"))
+       hparams = {"lr": 0.02}
+   else:
+       hparams = det.get_cluster_info().trial.hparams
+       expconf = None
+       distributed_context = None
  
+     with det.pytorch.init(
+       hparams=hparams,
+       exp_conf=expconf,
+       distributed=distributed_context
      ) as train_context:
          trial = MNistTrial(train_context)
          trainer = det.pytorch.Trainer(trial, train_context)
          trainer.fit(
              max_length=pytorch.Epoch(1),
              checkpoint_period=pytorch.Batch(10),
              validation_period=pytorch.Batch(10),
          )
```

The above showcases an example workflow of frequent iterations between local debugging and cluster deployment. To run Trainer API solely on-cluster, the code is much simpler:

```
def on_cluster():
    """
    On-cluster training with Trainer API (entrypoint: python3 train.py)
    """
    hparams = det.get_cluster_info().trial.hparams

    with det.pytorch.init() as train_context:
        trial_inst = model.MNistTrial(train_context, hparams)
        trainer = det.pytorch.Trainer(trial_inst, train_context)
        trainer.fit(
            max_length=pytorch.Epoch(1),
            checkpoint_period=pytorch.Batch(10),
            validation_period=pytorch.Batch(10),
        )

```
### 4. (On-cluster) Submit your trial for training
Create a `.yaml`. Must contain searcher configuration and entrypoint. `global_batch_size` is required if `max_length` is configured in `records`
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


# Trainer API Reference
```
determined.pytorch.init(
    *,
    hparams: Optional[Dict] = None,
    exp_conf: Optional[Dict[str, Any]] = None,
    distributed: Optional[core.DistributedContext] = None
) -> pytorch.PyTorchTrialContext:
```
`pytorch.init()` builds a `pytorch.PyTorchTrialContext` for use with `PyTorchTrial`.

Always use this method to construct a `PyTorchTrialContext` instead of instantiating the class directly.

All of the arguments are optional, but `hparams` and `exp_conf` are used to set the corresponding variables on `PyTorchTrialContext`. So if not passed in, calling `context.get_hparams()` or `context.get_experiment_config()` will fail in local-training mode. `DistributedContext` can be optionally passed in to manually configure distributed training; otherwise, it will be automatically initialized from the launch layer.

All `trainer.*` calls must be within the scope of this `with pytorch.init() as trial_context`, as there are resources necessary for training which start in the __enter__ method and must be cleaned up in the corresponding __exit__() method.


## determined.pytorch.Trainer
`class determined.pytorch.Trainer(trial: pytorch.PyTorchTrial, context: pytorch.PyTorchTrialContext)`

`Trainer` is the main class for Trainer API. It has the following required arguments:
- `trial`: an instance of the `PyTorchTrial` class
- `context`: the `PyTorchTrialContext` returned from `pytorch.init()`


```
classmethod configure_profiler(
    sync_timings: bool, enabled: bool, begin_on_batch: int, end_after_batch: int
) -> None:
```
Configure profiler settings. This method can only be called once per `Trainer` object and must be called before `.fit()`

```
classmethod fit(
    checkpoint_period: Optional[pytorch.TrainUnit] = None,
    validation_period: Optional[pytorch.TrainUnit] = None,
    max_length: Optional[pytorch.TrainUnit] = None,
    reporting_period: Optional[pytorch.TrainUnit] = None,
    aggregation_frequency: Optional[int] = None,
    checkpoint_policy: Optional[str] = None,
    test_mode: Optional[bool] = None,
)
```
`fit()` trains a `PyTorchTrial` configured from the `Trainer` and handles checkpointing and validation steps, and metrics reporting. 

`checkpoint_period` 
The number of steps to train for before checkpointing. This is a `TrainUnit` type (`Batch` or `Epoch`) which can take an `int` or instance of `collections.abc.Container` (list, tuple, etc.). For example, `Batch(100)` would checkpoint every 100 batches, while `Batch([5, 30, 45])` would checkpoint after every 5th, 30th, and 45th batch. 

`validation_period`
The number of steps to train for before validating. This is a `TrainUnit` type (`Batch` or `Epoch`) which can take an `int` or instance of `collections.abc.Container` (list, tuple, etc.). For example, `Batch(100)` would validate every 100 batches, while `Batch([5, 30, 45])` would validate after every 5th, 30th, and 45th batch. 

`max_length`
The maximum number of steps to train for. This value is required and only applicable in local training mode. For on-cluster training, this value will be ignored; the searcher's `max_length` must be configured from the experiment configuration. This is a `TrainUnit` type (`Batch` or `Epoch`) which takes an `int`. For example, `Epoch(1)` would train for a maximum lenght of one epoch.

`reporting_period`
The number of steps to train for before reporting metrics. Note that metrics are automatically reported before every validation and checkpoint, so this configures additional metrics reporting outside of those steps. This is a `TrainUnit` type (`Batch` or `Epoch`) which can take an `int` or instance of `collections.abc.Container` (list, tuple, etc.). For example, `Batch(100)` would report metrics every 100 batches, while `Batch([5, 30, 45])` would report after every 5th, 30th, and 45th batch.

`aggregation_frequency`
The number of batches trained before gradients are exchanged during distributed training. If unset, will default to 1.

`checkpoint_policy`
Controls how Determined performs checkpoints after validation operations, if at all. Should be set to one of the following values:

best (default): A checkpoint will be taken after every validation operation that performs better than all previous validations for this experiment. Validation metrics are compared according to the metric and smaller_is_better options in the searcher configuration. This option is only supported for on-cluster training.

all: A checkpoint will be taken after every validation, no matter the validation performance.

none: A checkpoint will never be taken due to a validation. However, even with this policy selected, checkpoints are still expected to be taken after the trial is finished training, due to cluster scheduling decisions, before search method decisions, or due to min_checkpoint_period.

`test_mode`
Runs a minimal loop of training for testing and debugging purposes. Will train and validate one batch. Defaults to false.

