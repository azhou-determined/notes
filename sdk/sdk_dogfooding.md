# Python SDK
This document details upcoming changes to the Python SDK and is intended as a guide for internal user feedback.

## Motivation
We have prioritized work on Python SDK for Q3 and Q4 of 2023 with the motivation of increasing adoption of Determined as a platform. As a user-facing API into Determined features, we want the Python SDK to:
  - Empower users to create and manage automated workflows that fit their custom needs
    - Programmatic control of Determined objects and processes
  - Inspire confidence in the rest of the Determined platform with:
    - Ergonomic tools
    - Consistent, intuitive APIs

## Changes
### Caching
Implementing a consistent strategy for caching in SDK resources is tricky. We don't want to never cache/always do a fresh fetch, since some values may not be present at time of instantiation, but also do not change for the object's lifetime (i.e. `hparams` on `Trial`), and this could incur lots of extraneous network requests. Since we cannot always cache, we've opted to surface an option to users to force a cache refresh themselves.

Our strategy is to always cache mutable resource attributes (everything except ID, usually) unless explicitly requested from the user, except for certain circumstances where we know a local state update should happen (i.e. `experiment.set_name` will automatically update the local attribute `name`).

All SDK resources now have a public `reload()` method, which will always do a fresh API call to the master and update the local object state with the latest response.

For example:
```python
print(trial.summary_metrics) 

# Long-running process
time.sleep(100)

print(trial.summary_metrics) # Local state unchanged
trial.reload()
print(trial.summary_metrics) # Local state updated
```

### Instantiation
We expect SDK resources to usually be obtained from another method call (i.e. `client.get_trial` returns a `Trial` object), but we do allow direct instantiation (i.e. `trial = Trial(id=1)`) for advanced use cases that want to use helper methods on the resource class without incurring the initial `GET` call. 

For example, say I want to kill the first 100 trials:
```python
for i in range(100):
    # This instantiates a "blank" object without fetching any data.
    trial = Trial(id=i, ...)

    # This would call the REST API to fetch and hydrate the Trial.
    trial = get_trial(id=i)

    trial.kill()
```

### Additions
We are shipping a batch of assorted SDK improvements and bugfixes, including but not limited to:
- Useful attributes on various resource objects, including:
  - `config`, `state`, `name`, `description` (and setters) on `Experiment`
  - `hparams`, `summary_metrics`, `state` on `Trial`
- `download_code` for `Experiment`s
- `Workspace` and `Project` support for `Experiment`s
- `add/remove_label` on `Experiment`s
- log searching/querying with `Trial.logs()`
- `list_experiments` on the top-level `Determined` SDK client


### Deprecations / Breaking Changes
Some interfaces were deprecated (to be removed with completion of Q4 Python SDK work):
- `TrialReference` and `ExperimentReference` were renamed to `Trial` and `Experiment`, respectively. This is to be more consistent with the rest of the resources in the SDK. 
  - `*Reference` suffixes existed previously to avoid confusion/conflict with the existing `Trial` objects, which were renamed to `LegacyTrial`. This should not be a breaking change since there is no use for subclassing a `Trial`.
- `select_checkpoint`, `get_checkpoints`, `top_checkpoint`, and `top_n_checkpoints` were all deprecated in favor of `list_checkpoints`, a singular and more powerful/generic method to query and sort checkpoints on `Trial` and `Experiment`.
- `GET` API calls in the SDK now default to aggressively retrying (5 times) 
- Various `get_{collection}` methods were deprecated and replaced with a more consistent `list_{collection}` name.

## Example Workflow
We are shipping a grab bag of SDK improvements along with some core architectural changes (when to cache, reload, etc.). 

My ask from dogfooders would be not to test individual features/improvements, but to assess the Python SDK in its current state as a whole. Try and implement any common workflow you encounter frequently in the SDK:
- Do you encouter any limitations? What's missing (features, data, etc.)? 
- Is there anything about the APIs or features that is confusing?
- Are the methods intuitive? Can you "guess" what classes/methods you need without looking up documentation?

That being said, here is an example workflow of a very primitive distributed hyperparameter search I've implemented taking advantage of some of the new SDK changes:

```python
from determined.experimental import client
from determined.common import yaml
import pathlib
import time
import threading
import queue


hp_search = {
    "learning_rate": [0.0001, 0.001, 0.01, 0.1]
}

def monitor_trial(trial, interval):
    prev_val_steps = None
    prev_best_val = None
    steps_threshold = 5
    
    logs_thread = threading.Thread(target=trial.follow_logs, args=(True,))
    logs_thread.start()
    while trial.state.name not in ["CANCELED", "COMPLETED", "ERROR"]:
        trial.reload()
        summary_metrics = trial.summary_metrics
        if not summary_metrics or "validation_metrics" not in summary_metrics:
            time.sleep(interval)
            continue
        current_val = summary_metrics["validation_metrics"][val_metric_name]["min"]
        current_steps = summary_metrics["validation_metrics"][val_metric_name]["count"]
        
        if prev_val_steps is not None and prev_best_val is not None:
            early_stop = should_early_stop(prev_best_val, prev_val_steps, current_val, current_steps, steps_threshold)
            if early_stop:
                print(f"Early stopping trial {trial.id} due to no improvement for {val_metric_name} for {steps_threshold} steps.")
                trial.kill()
                
        time.sleep(interval)
    logs_thread.join()

def create_experiment_with_hparams(
    hp_name, hp_val, val_metric_name, trial_queue
):
    print(f"Starting experiment with {hp_name}={hp_val}")
    exp_conf["hyperparameters"][hp_name] = hp_val

    exp = client.create_experiment(config=exp_conf, model_dir=model_dir)
    exp.move_to_project("my_workspace", "my_hpsearch_project")

    trial = exp.await_first_trial()
    trial_queue.put(trial.id)

    monitor_trial(trial, 5)
    
def should_early_stop(
    prev_best_val, prev_val_steps, current_best_val, current_val_steps, stop_threshold
):
    """
    Primitive early stopping: returns True if a trial's searcher validation metric has not improved within a specified number of steps, else False.
    """
    if prev_val_steps + stop_threshold <= current_val_steps and current_best_val == prev_best_val:
        return True
    return False

def main():
    trial_queue = queue.Queue()
    exp_threads = []

    for hp_name, hp_vals in hp_search.items():
        for hp_val in hp_vals:
            exp_thread = threading.Thread(target=create_experiment_with_hparams, args=(hp_name, hp_val, val_metric_name, trial_queue))
            exp_threads.append(exp_thread)
            exp_thread.start()

    for thread in exp_threads:
        thread.join()

    print(f"All trials completed. Generating summary report.")
    trial_vals = []
    for trial_id in trial_queue.queue:
        trial = client.get_trial(trial_id=trial_id)
        
        # Smaller is better
        trial_best_val = trial.summary_metrics["validation_metrics"][val_metric_name]["min"]
        
        for hparam in hp_search.keys():  
            trial_vals.append({
                "trial_id": trial.id,
                "hparam_name": hparam,
                "hparam_val": trial.hparams[hparam],
                "val_metric_name": val_metric_name,
                "best_val_metric": trial_best_val,
            })

    trial_vals.sort(key=lambda x: x["best_val_metric"])

    print("=" * 100)
    print(f"Hyperparameter space: {hp_search}")
    print(f"Trials completed: {len(trial_vals)}")
    print(f"Best validation: {trial_vals[0]}")
```

## Discussion Topics
### List vs. Iter
We have gone back and forth on this (both as a larger team and just Wes and I) on whether collections of objects should by default be returned as an `iterator` or a `list`. Pro's and con's for both:

List:
➕ Easy for all users to understand, the "expected" return type for a collection
➕ Sufficient for majority of use cases
➖ Always fetches all pages of a response at the expense of additional API calls even if you only want the first X pages.

Iterator:
➕ Allows for a more powerful API that lazily consumes paginated server responses, avoiding unnecessary and potentially expensive round trips to master.
➖ Might be confusing for users unfamiliar with Python generators.

We have settled on a convention of no strict convention here: return an `Iterator` when we expect a large number of response objects to be returned/consumed (i.e. streaming metrics), for the majority of use cases just return a `List`, but this is open for discussion.


### Query / Filter Interfaces
A common usage pattern for SDK methods is to fetch a collection of resources with some query or filtering parameters. Often these parameters can be either a predefined value we offer or a custom field. We want the interface for these methods to be clear, concise, and convenient to the end user, but these concepts can sometimes be at odds. 

Case in point, `list_checkpoints`:
- We support sorting by predefined enum values (e.g. `CheckpointSortBy.UUID`, `CheckpointSortBy.BATCH_NUMBER`, etc.). We also want to support sorting by custom metric name, an arbitrary string ("val_accuracy", "loss", etc.).
- We settled on an interface of `sort_by=str|CheckpointSortBy` (for users, this means you can pass in either `"loss"` or `CheckpointSortBy.UUID`) in favor of convenience, but at the cost of clarity of the method interface.

If we want to get really fancy with filtering capability (perhaps useful for metrics in the future), we might want to support a primitive query language (`list_metrics(filter="accuracy > 0.95")`), but this is probably overkill for now.

