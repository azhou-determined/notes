# Keras Trainer API

The proposed Keras Trainer API is designed to be a lightweight wrapper around native Keras implementations while 
providing Determined features in an accessible, intuitive way using a Callbacks approach.

## Training
Basic training is done with a `fit` call similar to the native Keras implementation, but as a method on the train 
context object. Horovod will be the default launch layer if slots_per_trial > 1, no launch layer needs to be specified if using horovod.

```diff
 # Initialize a train context
+with det.keras.init() as train_context:
     # Define your model
     model = keras.models.Sequential([
         keras.layers.Flatten(input_shape=(28, 28)),
         keras.layers.Dense(128, activation='relu'),
         keras.layers.Dense(10),
         keras.layers.Dropout(1.0)
     ])
 
     # Access hparams from the ClusterInfo API
-    learning_rate = 0.001
+    learning_rate = det.get_cluster_info().trial.hparams["learning_rate"]
 
     # Wrap your optimizer
     # This is needed before model.compile
     # Train context wraps the optimizer with HorovodOptimizer if doing distributed training and
     # makes sure optimizer state is saved correctly in checkpoints
     optimizer = keras.optimizers.Adam(learning_rate)
+    optimizer = train_context.wrap_optimizer(optimizer)
     
     # Wrap your datasets
     # This ensures proper sharding happens for distributed training before the .fit call
+    ds_train = train_context.wrap_dataset(ds_train)
+    ds_test = train_context.wrap_dataset(ds_test)
     
     # Compile your model as usual
     model.compile(
         optimizer=optimizer,
         loss=keras.losses.SparseCategoricalCrossentropy(from_logits=True),
         metrics=[keras.metrics.SparseCategoricalAccuracy()],
     )

     # Training is done with a fit call on the context object with a similar API as native Keras but the
     # model is passed in.
          
-    model.fit(
+    train_context.fit(
+        model=model,
         x=ds_train,
         epochs=6,
         # Validation data must be passed into the fit call instead of a separate evaluate call
         validation_data=ds_test,
         validation_split=0.0,
         # Add custom callbacks here. The Trainer will by default inject certain Determined callbacks to
         # handle automatic checkpointing and metrics reporting
         callbacks=[],
     )
```

### Native Keras Distributed Training
We will support a Keras launch layer which initializes the environment variables needed for distributed training in 
Tensorflow.

`entrypoint: python3 -m determined.launch.tensorflow_distributed train.py`

```diff

with det.keras.init() as train_context:
    # Choose a distributed training strategy
+   strategy = tf.distribute.MirroredStrategy()

    # Model must be defined and compiled within the tf.keras strategy scope
+   with strategy.scope():
        model = tf.keras.Sequential([
            tf.keras.layers.Conv2D(32, 3, activation="relu", input_shape=(28, 28, 1)),
            tf.keras.layers.MaxPooling2D(),
            tf.keras.layers.Flatten(),
            tf.keras.layers.Dense(64, activation="relu"),
            tf.keras.layers.Dense(10)
        ])

        model.compile(loss=tf.keras.losses.SparseCategoricalCrossentropy(from_logits=True),
                      optimizer=tf.keras.optimizers.Adam(),
                      metrics=["accuracy"])

    # Fit is called from the train context
    train_context.fit(model, ...)

```

### Inference and Checkpoint Loading
`model.predict` can be called directly for inference.

```
with det.keras.init() as train_context:
    model = train_context.load_model_from_checkpoint(trial_id)
    model.predict(...)
```

By default, continue trial behavior will load from `context.latest_checkpoint` if exists, following existing merging 
behavior in the master, which loads either `latest_checkpoint` or `searcher.source_checkpoint`.

### Custom Checkpointing
By default, Determined will checkpoint on set periods (every epoch), but the user can override this behavior by passing
in a custom checkpoint callback. `DeterminedModelCheckpoint` is a subclass of native Keras' `ModelCheckpointCallback` 
that provides automatic checkpoint handling for preemption. At the method interface level, both callbacks should be 
identical. Only one checkpoint callback is expected, so an error will be thrown if the user passes in a native 
`tf.keras.ModelCheckpointCallback`.

```
checkpoint_callback = DeterminedModelCheckpoint(
        "checkpoint_path",
        monitor="val_loss",
        verbose=0,
        save_best_only=False,
        save_weights_only=False,
        mode='auto',
        save_freq=checkpoint_freq,
        options=None,
        initial_value_threshold=None,
    )
```

### Profiling with Determined
The Determined profiler is configured as a Keras callback to be passed into `context.fit`
```
with det.keras.init() as train_context:
    train_context.fit(
        ...,
        callbacks=[
            DeterminedProfilerCallback(
                profiling=True,
                profiling_start=0,
                profiling_end=10,
                sync_timings=None,
            )
        ]
    )
```


## Technical Details
Additional features Determined provides will be injected into the training methods via callbacks. These are 
automatically included by default with the call to `fit` on the context.

### `context.fit`
The `context.fit` call is a wrapper around `model.fit` with a few differences:
- Training and validation datasets passed in will be automatically wrapped and sharded for distributed training
- Callbacks will be injected to handle metrics reporting, hyperparameter search, preemption, and checkpointing
- Evaluation/validation on the model will be called as part of the training loop

```
def fit(
        model=model,
        checkpoint_freq=2,
        x=None,
        y=None,
        batch_size=None,
        epochs=1,
        verbose='auto',
        callbacks=None,
        validation_split=0.0,
        validation_data=None,
        shuffle=True,
        class_weight=None,
        sample_weight=None,
        initial_epoch=0,
        steps_per_epoch=None,
        validation_steps=None,
        validation_batch_size=None,
        validation_freq=1,
        max_queue_size=10,
        workers=1,
        use_multiprocessing=False
):
    # Set up callbacks to be passed in by default
    
    # If a DeterminedModelCheckpoint callback type is not passed in, construct one by default
    checkpoint_callback = DeterminedModelCheckpoint(
        "checkpoint_path",
        monitor="val_loss",
        verbose=0,
        save_best_only=False,
        save_weights_only=False,
        mode='auto',
        save_freq=checkpoint_freq,
        options=None,
        initial_value_threshold=None,
    )

    callbacks = [
        checkpoint_callback,
        # Handles metrics reporting, preemption
        context.DeterminedCallback(validation_steps, validation_freq, validation_batch_size),
    ]

    # We pass in a subclassed container to validation_freq to call evaluate during training
    model.fit(validation_freq=context.ValidationFreq(),
              callbacks=callbacks)
```

## Discussion + Notes

---
      
- What is the difference between continue trial and warm starting?
  - Continue trial means just continue training without modifying anything (pause & restart, restarts exhausted)
    - resumes optimizer state
  - warm starting means picking and choosing between checkpoints


- Checkpoint loading flavors
    - Forking: basically just copying model code and rerunning it
      - Nothing fancy here, we can do what is currently done
      
    - Warm starting: starting from a particular part of the model infrastructure (optimizers, weights, LR Scheduler). 
      Today either the `latest_checkpoint` of the Trial OR the `source_checkpoint` (if specified) is loaded by the 
      master and passed down to the `CoreContext` as `context.latest_checkpoint`.
      - With the same model architecture:
        - Effectively the same as continue trial. `context.fit()` will load from `context.latest_checkpoint` if exists.
          
      - With different model architecture:
        - No way for us to automatically support this. We would end up with a Frankenstein model.
    
    - Trial continuation: resume training where we left off without modifying anything.
      

        
- Do we want to support predict inference during training? 
  - Seems like a rare use case. Users can implement their own callback for this so long as it's supported in native 
    Keras
    
- Do we need a context wrapper around the `predict` inference method?
  - Only use case would be distributed batch inference, but unless we support model parallel this seems like a non-
use case since there's no distributed communication required on just the forward pass.
    - Is distributed inference hard to support? Do we need to support this at all?
      - Probably not that useful and we should avoid shipping too many new apis at once. The existing Trainer should be 
        easy to extend if this becomes an important use case in the future.
- How should users configure custom model checkpointing?
  - We configure a default callback, so maybe we can just move the checkpoint callback outside of the fit call as a 
    separate configurable callback. This makes more sense for checkpoint-related configs also, since they aren't natural
    in the native `fit` call.
  - We need to inject some logic for automatic checkpoint handling during preemption.

