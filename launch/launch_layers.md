# Entrypoint 
The entrypoint of a model is configured in the experiment configuration, and specifies the path of the model and how it 
should be launched. Determined supports a few distributed launch layers out-of-the-box as well as custom scripts. 

- Overview
- Launch Layers
  - Supported backends
    - Horovod
    - Deepspeed
    - PyTorch
  - Trial specification
    - Trial class definition
    - Custom launcher
  - Legacy usage
 - Nested Launchers


## Overview
The launch layer is configurable in the experiment configuration's entrypoint field. The entrypoint field is 
responsible for launching the training code, which can call pre-canned launch layers provided in the 
`determined.launch` module, or a custom launcher script:

```
entrypoint: python3 -m (LAUNCH_LAYER) (TRIAL_DEFINITION)
```

or a totally custom

```
entrypoint: python3 script.py arg1 arg2
```


The entrypoint field expects a script, but supports 
[legacy file and trial class definitions]("https://docs.determined.ai/0.12.3/topic-guides/model-definitions.html")
as well.


## Launch Layers

Entrypoints for pre-configured launch layers may differ slightly in arguments, but share the same format:

```
python3 -m (LAUNCH_MODULE) (--trial TRIAL)|(SCRIPT...)
```
where `LAUNCH_MODULE` is a Determined launcher, and `(--trial TRIAL)|(SCRIPT...)` refers to the training script 
specification, which can be in a simplified format that the Determined launcher will recognize and locate, or a 
custom script.

### Launch Modules

Determined supports a few pre-configured launch layers provided in the `determined.launch` module.


#### Horovod (determined.launch.horovod)


```determined.launch.horovod [[HVD_OVERRIDES...] --] (--trial TRIAL)|(SCRIPT...)```

The module accepts arguments to be passed directly to the horovod launcher called under-the-hood, `horovodrun`, which 
will override values set by Determined automatically. See 
[official horovod documentation]("https://horovod.readthedocs.io/en/stable/running_include.html") for details on the 
`horovodrun` launcher.

The optional override arguments must end with a ```--``` separator before the trial specification.

> **Example**:
> ```
> python3 -m determined.launch.horovod --fusion-threshold-mb 1 --cycle-time-ms 2 -- --trial model_def:MyTrial
> ```

#### PyTorch Distributed

```determined.launch.torch_distributed [[TORCH_OVERRIDES...] --] (--trial TRIAL)|(SCRIPT...)```

This launcher is a Determined wrapper around PyTorch's native distributed training launcher, `torch.distributed.run`. 
 Any arbitrary override arguments to `torch.distributed.run` are accepted, which will override default values set by 
Determined. See 
[official PyTorch documentation]("https://pytorch.org/docs/stable/elastic/run.html")
for details on `torch.distributed.run` usage.

The optional override arguments must end with a ```--``` separator before the trial specification.

> **Example**:
> ```
> python3 -m determined.launch.torch_distributed --rdzv_endpoint=$CUSTOM_RDZV_ADDR -- --trial model_def:MyTrial
> ```


#### Deepspeed

```determined.launch.deepspeed [[DEEPSPEED_ARGS...] --] (--trial TRIAL)|(SCRIPT...)```
The deepspeed launcher launches a training script under deepspeed with automatic handling of IP addresses, node and 
container communication, and fault tolerance.

See 
[official deepspeed documentation]("https://www.deepspeed.ai/getting-started/#launching-deepspeed-training") 
for details on the deepspeed launcher usage.

> **Example**:
> ```
> python3 -m determined.launch.deepspeed --trial model_def:MyTrial
> ```
> 


### Training Code Definition

To launch a model or training script, either pass a trial class path to `--trial` or run a custom script that runs the 
training code. Only one of these can be used at the same time.

#### Trial Class 
```--trial TRIAL```

To specify a trial class to be trained, the launcher accepts a `TRIAL` argument in the following format:
```
filepath:ClassName
```
where `filepath` is the location of your training class file, and `ClassName` is the name of the Python training class


#### Custom Script
```script.py [args...]```

A custom script can be launched under supported launch layers instead of a trial class definition, with arguments 
passed as expected.



### Legacy Entrypoint Configuration
An entrypoint definition with only the file and class name of the model.

```
entrypoint: model_def:TrialClass
```

Determined will locate a `TrialClass` found in the filepath `model_def` and launch automatically. This usage is 
considered legacy behavior. 

> **Note:**
> 
> By default, this configuration will automatically detect distributed training based on slot size and number of machines, 
and will launch with horovod if distributed training. If used in a distributed training context, this entrypoint 
effectively becomes:
> ```
> python3 -m determined.launch.horovod --trial model_def:TrialClass
> ```
> 
> 


## Nested Launch Layers

Entrypoint supports nesting multiple launch layers in a single script. This can be useful for executing anything that 
should be run before the training code begins (e.g. profiling tools like dlprof, custom memory management tools like 
numactl, or data preprocessing)

> **Example**:
> ```
> dlprof --mode=simple python3 -m determined.launch.autohorovod --trial model_def:MNistTrial
> ```
