# Unified Metrics

Today metrics are rather limited in scope. They are strictly for training tasks, belong to the `Experiment`, and can only be accessed programatically through internal APIs, logs, and the web UI. This document details the concepts and proposed Python SDK support for a more unified and generic metrics interface.

## Motivations
### Generic metrics
- Expand the scope of metrics support to non-training-specific tasks
    - NTSC (notebook, tensorboard, shell, command) and generic (future planned work) tasks should be able to report/retrieve metrics
- Metrics themselves should be generic. We don't want to dictate which x-axis to support, or constrain what users report.

### Scalable
- Easily access collections of metrics from across different Trials, Experiments, and generic Tasks through:
    - Training code
    - Exports/downloads in various formats:
        - CSV, JSON, pd.dataframe
- Compare metrics across many different trials and experiments
- Ability to filter and query a potentially large amount of metrics meaningfully


## Concepts

### Task
A task is any job that is submitted to and/or runs on Determined. Generic tasks have minimal special Determined interaction, but there are other types of more managed tasks:
- Trial
- Notebooks
- Tensorboard
- Inference (future)

 All metrics are reported by and belong to a `Task`. 

### Run
A run consists of a group of `Tasks`, which can span across `Trials`. Today's `Experiment` abstraction is limiting as its scope serves the sole purpose of hyperparameter search, and frequently users want to compare metrics across many `Experiments`. However, a higher-level abstraction than the base `Task` is helpful operations outside of a singular `Task` when comparing performance across `Trials`.

`Run` serves as a grouping of `Tasks` that exists outside of today's `Trial`/`Experiment` hierarchy.

### Artifact (Out of scope)
`Tasks` may report non-standard metrics. They may not serve the same purpose as metrics, but still belong to a `Task`. These objects can potentially consist of images, audio clips, or any arbitrary file directory.

## Python SDK
The existing Python SDK has limited support for some of the aforementioned concepts. The APIs detailed below will incorporate any additional methods into the existing Python SDK implementation.

All `Tasks` implement `get_metrics` to retreive reported metrics.

`Task` is the base class representing Determined tasks which special (NTSC) task types will extend from.

### `get_metrics(...) -> Metrics`
Retrieving metrics from a `Task` takes into account querying, filtering, and potential downsampling:
```
def get_metrics(
        self,
        # For generic tasks, this may be user defined
        # For Trial/training tasks, this will be train|validate|profile
        series: Optional[str] = None,
        # asc|desc
        order: Optional[str] = None,
        limit: Optional[int] = None,
) -> Dict:
    pass
```
Once we have the resulting `Metrics`, there are a few options for "downloading" to the client and formatting:
```python3
class Metrics:
    # Export metrics externally to a specified directory with a file format (.csv, .json, etc)
    def export(self, filepath: pathlib.Path, format: str) -> pathlib.Path:
        pass

    def as_df(self) -> pd.DataFrame:
        pass

    def as_dict(self) -> Dict:
        pass
```

Example of JSON-formatted metrics returned by a `Trial` training task:
```json
{
  "train": [
    {
      "batch_idx": 1,
      "loss": 2.33,
      "acc":  3.24
    },
    {
      "batch_idx": 5,
      "loss": 5.33,
      "acc":  5.24
    }
  ],
  "validate": [
    {
      "batch_idx": 1,
      "val_loss": 2.33,
      "val_acc":  3.24
    },
    {
      "batch_idx": 3,
      "val_loss": 5.33,
      "val_acc":  4.24
    }
  ]
}
```

### Task
Base `Tasks` will contain immutable properties and methods to fetch mutable metadata.

```python3
class Task:
    def __init__(self, id: str):
        self.id = id

    @property
    def id(self):
        return self.id

    def get_tags(self) -> List[str]:
        pass

    def get_state(self) -> str:
        pass

    def get_metrics(
            self,
            # For generic tasks, this may be user defined
            # For Trial/training tasks, this will be train|validate|profile
            series: Optional[str] = None,
            # asc|desc
            order: Optional[str] = None,
            limit: Optional[int] = None,
    ) -> Metrics:
        pass

    def artifacts(self) -> List[Artifact]:
        pass

    def add_artifact(self, artifact: Artifact) -> None:
        pass
```

### Trial(Task)
`Trial` is a special type of managed `Task` that contains all base `Task` properties as well as some additional methods to get training-specific metadata. 
> **_NOTE:_** This is conceptually just an extension to the existing `TrialReference` object in the Python SDK, naming TBD

```python3
class Trial(Task):
    def __init__(self, id: str, hyperparameters: Dict):
        super().__init__(id)

    def get_latest_checkpoint(self) -> str:
        pass

    def get_best_validation(self) -> Dict:
        pass

    @property
    def hyperparameters(self) -> Dict:
        pass

    def get_metrics(
            self,
            series: Optional[str] = None,
            order: Optional[str] = None,
            limit: Optional[int] = None,
    ) -> Metrics:
        pass

trial = create_trial(name="new trial", hparams={"lr": 0.03})
```

### Run
A `Run` is a collection of `Tasks`, intended to be a better abstraction than today's `Experiment`, though likely out of scope, but proposed additions here can be dropped in to today's `Experiment`/`ExperimentReference`.
> **_NOTE:_** `get_metrics` may not be necessary for a `Run`, as a user can fetch metrics for each child `Task`, but is included here for potentially supporting convenient downsampling of a large amount of metrics, and preventing a large number of API calls to fetch each `Task` metric
```python3
class Run:
    def __init__(self, id: str, name: str, trials: List[Task]):
        pass

    def get_metrics(
            self,
            series: Optional[str] = None,
            order: Optional[str] = None,
            limit: Optional[int] = None,
    ) -> Metrics:
        pass

    def add_task(self, task: Task) -> None:
        pass

    def get_tasks(self) -> List[Task]:
        pass

run = create_run("new run")
run.add_task(task=trial)

```

### Example
```python3
def main():
    # Create a run
    run = create_run("new run")
    
    # Create a new trial
    trial = create_trial("my trial", hparams={"lr": 0.34})
    run.add_task(trial)
    
    # Get metrics out of our trial
    metrics = trial.get_metrics().as_dict()
    validation_metrics = trial.get_metrics(series="validate", order="desc", limit=100).as_df()
    hparams = trial.hyperparameters
    
    # Create another trial
    new_trial = create_trial("my trial 2", hparams={"lr": 0.54})
    run.add_task(new_trial)
    
    # Finished our small "experiment"
    results = run.get_metrics().as_dict()
```

## Other considerations
- For large metrics series, there may be smarter ways to query/filter (e.g. start/end/skip indexes, batch REST API calls)
- Profiling metrics may be too large to be included in the `Trial` metrics. We could potentially return them separately, or not return them by default.
- We could support similar batching methods on `Project` and `Workspace` definitions as well, if helpful.
