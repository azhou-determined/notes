# Python SDK

This document details proposed standards, conventions, and feature additions to the Python SDK.

## Overview
### Motivation
Python SDK has been lacking in attention and support since conception. There are features supported across Determined that are missing from the Python SDK, and design conventions that need to be defined to add them. We have decided to prioritize work on Python SDK in [Q3 of 2023](https://hpe-my.sharepoint.com/:x:/r/personal/maksim_kouznetsov_hpe_com/Documents/ML%20Systems%20roadmap.xlsx?d=w9053a7a12fdf450faf245fcda1b9f520&csf=1&web=1&e=T2TBGt).

- [Conventions](#conventions)
  - [Naming](#naming)
  - [Caching](#caching)
- [Planned Work](#planned-work)
<a name="conventions"></a>
## Conventions
### Philosophy
The Python SDK should be thought of as a programmatic way of interacting with Determined clusters and features that allows users to build and integrate with workflows through code. It is a higher-level API used for scripting with Determined that does not contain any standalone features on its own, in contrast to our training (trial API, core API, inference) APIs.

It should supports operations at scale (caching, batching requests, asynchronous methods on long-running processes) for features like metrics, checkpoints, experiment hooks (future), or anything users would want to do from a Jupyter notebook.

We should be consistent with naming and design conventions and make desired usage obvious when possible while ensuring the overall API feels native to the Python language.

Today, the Python SDK is in an experimental status because it lacks coherent APIs and features we think are essential. As the SDK grows in a stable and consistent way, the intent is for it to become a first-class feature. This project aims to move us closer to that goal.

<a name="naming"></a>
### Structure & Naming
#### Client
Top-level client is represented as both an instance and singleton (`experimental.Determined()` and `experimental.client`). We support both because it's easy to do so and there are merits for each pattern. The top-level client contains authentication methods and various methods to obtain a resource's object (eg. `get_experiment`, `get_model`)<sup>†</sup>. 

#### Resource Classes
Each resource is its own class object. We will rename `TrialReference` and `ExperimentReference` to `Trial` and `Experiment`, since they were originally named as such to avoid confusion between the `Trial` object used in training (this still exists today, but can be deprecated altogether).

First-class entities (`Trial`, `Experiment`, etc.) have `get`/`create` CRUD methods on the class object to fetch related objects (eg. `model.get_versions()`). `get` carries the implication that we are doing a round-trip to master for fetch.

#### List / Iterable
Fetching multiple instances of a resource object should utilize a `list_resource` name, and return an `Iterable` data type. The name `list` is preferred over `get_resources` to be consistent with our CLI methods and some other popular CLIs (eg. boto3 and Google Cloud SDK's `list_` resource methods). We return `Iterable` Python generators containing paginated responses.

This decision was made to support the option to lazily consume objects and reduce memory usage. Users who want the full list up-front will need to call `list(iter)` on the returned object. Because this behavior is somewhat unexpected, we should add detailed documentation explaining these methods.
```
# Lazy fetch of experiments by page.
experiments = client.list_experiments()
# Fetch all at once.
experiments = list(client.list_experiments())
```

Alternative approaches[^1] considered include:
- Providing both `list_` and `iter_` methods for the same resource for both `List` and `Iterable` return types. This makes the expected return object explicit, but introduces double the number of APIs to implement and maintain.
- Only returning iterables and naming methods `iter_`. This is explicit, but a rather unexpected name for most users.
- Surfacing a flag (eg. `lazy=True`) to indicate the return type. This introduces a feature flag for a relatively simple operation `list()` users can call themselves but with more overhead.

<a name="caching"></a>
### Caching
Network round-trips to the master can get expensive, and we want to minimize fetching "fresh" data when the user does not need it. It's not always possible for us to tell when data is stale, so we will surface a public `refresh()` method on resource objects that will force fetch and update all the properties on the object. 

Today, objects may be partially hydrated or fully hydrated depending on which caller they were obtained from. This can cause unexpected behavior because it is unclear which properties exist on an object at any given time, and also prevents us from doing validation on instantiation for objects might not exist (eg. `TrialReference(NONEXISTENT_ID)`). 

Moving forward, we should always fully hydrate objects on instantiation. Any resource object present will have all properties at all times. Our REST APIs will do a full fetch of the corresponding object's row in the database anyway, and frequently we discard mutable properties to construct a partially hydrated object. 

This may be an issue later on if each fetch becomes expensive (has many nested joins), but the alternative is partially hydrating objects, which is confusing for both developers and users. Expensive queries should be broken up into their own functions, like fetching `logs()` on a trial.

```
# First fetch returns fully-hydrated object.
trial = get_trial(trial_id=1)
# Properties on trial are always cached.
metadata = trial.metadata
# Explicit refresh to do a fresh fetch (and automatically update trial.metadata)
trial.refresh()
# In some cases where we know the state has changed, we will automatically refresh() under-the-hood.
trial.add_metadata()
```

Some alternative approaches[^2][^3] that were considered include:
- Never caching. Always do a full fetch on every method call. This gets very expensive when fetching nested properties on objects.
- Always caching and surfacing explicit methods to fetch (`get_`) on dynamic properties, which updates the property on the object. This approach makes it clear which properties are immutable vs. refreshable, but introduces uncertainty around the state of the object at any particular time.
- Maintaining two separate objects (eg. `TrialReference` and `Trial`) to distinguish between immutable and dynamic properties. This introduces a layer of abstraction that is probably unnecessary, since most immutable properties are useless on their own, and we usually receive the properties in a single HTTP fetch request anyway.

### Long-running Requests
Some API requests (eg. fetching trial metrics) may return large responses with long response times. We follow the general philosophy of allowing the backend REST API server to handle request and query optimization because many of our REST APIs are fine-tuned at the SQL level for performance. 

There are a few other ways we can try to reduce memory usage and time client-side if needed:
- Paging: this is already done server-side for most HTTP requests, but could be surfaced client-side for requests we expect to be large.
- Batching: if multiple pages need to be fetched, we could support batching of HTTP requests as a separate API or as an option in certain methods to reduce the request overhead of multiple individual requests.


## New Features

### CLI <> SDK <> Web UI 
Some methods exist in the Determined CLI but not the SDK [^4], but we should not try to achieve perfect feature parity between the two. The CLI and SDK are not strictly speaking equals in terms of intended use, as the CLI is intended for one-off, simple commands that do not need to interact with code.

Still, there are methods available in the CLI that should also exist in the Python SDK. We should fill in these gaps for consistency, while ensuring that each API follows a convention that feels native to its interface (command line for the CLI, Python for the SDK). This includes commands/shells and projects/workspaces.

Some features available to the web UI and/or REST APIs are also proposed additions to the Python SDK, including downloading code, config, and tensorboard files and support for profiler metrics.

<a name="planned-work"></a>
## Planned Work

Pre-requisites of new feature adds include implementation of the conventions detailed above:
| Task                                                                      | Notes                                                                                                                                          | Jira |
| ------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- | ---- |
| Rename `TrialReference` and `ExperimentReference` to `Trial`/`Experiment` | This requires deprecation/removal of the existing `Trial` abstract class, which is no longer needed.                                           |
| Change `get_*s` methods to `list_*s` with `Iterable` return types         | Documentation of motivation and lazy usage                                                                                                     |
| Caching and fully-hydrated objects on instantiation, `reload()`           | Requires documentation of caching behavior and property lifecycle                                                                              |
| Reorganization of top-level client and subresources                       | Likely out of scope unless we move to first-class Python SDK support with other major breaking changes and/or other work makes this necessary. |


New features, roughly organized by priority, determined by user/AMLE requests[^5][^6][^7]:

| Feature                                                  | Notes                                                                                                          | JIRA                                                            |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| Hyperparameters for a trial                              | Long-time request from users and AMLEs                                                                         |
| Summary metrics                                          | From Metrics V2 project, REST APIs already exist                                                               | [DET-9403](https://hpe-aiatscale.atlassian.net/browse/DET-9403) |
| Improving performance of getting metrics and checkpoints | May require backend query optimization or client-side pagination and/or batching                               |
| Trial logs (getting and searching)                       | Exists in CLI and AMLE request[^5]; fetch requires streaming, search requires more thought                     |
| Trial status                                             | Add property on the `Trial` class                                                                              |
| Fetch multiple experiments                               | Not sure why this is missing, seems like an obvious add; need to consider filtering, sorting                   |
| Workspace & Project                                      | Feature missing in SDK entirely; requires methods on `Experiment`/`Trial`/`Model` to move and assign           |
| Tags                                                     | Adding/removing tags on `Experiment`                                                                           |
| Experiment attributes                                    | Exists in ClI; add attribute (name, priority, description, etc.) properties and update methods on `Experiment` |
| Command support                                          | Command feature add in SDK, exists in CLI and request from Recursion[^8]                                       |
| Continue trial                                           | Exists in CLI and Web UI                                                                                       |
| Download Tensorboard files                               | Local download of Tensorboard files from cloud/shared FS                                                       |
| Downloading code/experiment config                       | Exists in Web UI; download zipped archive of code from cloud/shared FS                                         |
| Task information                                         | Task allocation information; requires new `Task` object                                                        |
| Profiler metrics                                         | Stream profiler metrics from torch profiler and Keras                                                          |
| Template                                                 | Exists in CLI; may be of use for RBAC templates                                                                |
| Shell                                                    | Missing feature from CLI, low-priority; method for killing shells might be useful for scripting                |
| Job                                                      | Missing feature from CLI, low-priority due to no explicit requests for this.                                   |
------

<sup>†</sup> In the future, we should reorganize the resource-related methods into their own subclass (eg. `client.experiments.list()`) for clearer separation between high-level client concerns (authentication, establishing initial HTTP connections) and resource classes. However, this is currently not worth the significant breaking change in order to do so. Should a major refactor of Python SDK be planned, we should consider this reorganization.

[^1]: Discussion on list vs. iterable: https://hpe-aiatscale.slack.com/archives/
[^2]: Discussion of rich objects: https://hpe-aiatscale.slack.com/archives/C02PV33GSN5/p1661531387380029CSLAGUF3M/p1649172941376699?thread_ts=1649172902.178179&cid=CSLAGUF3M
[^3]: Discussion on caching: https://hpe-aiatscale.slack.com/archives/CSLAGUF3M/p1665082805089849
[^4]: Spreadsheet of feature parity between the CLI and SDK: https://hpe-my.sharepoint.com/:x:/p/anda_zhou/EUq7dEQ7aoZCpbcnMGrJCCUBVEjBwrKvO5QbmYDTpzpuAA?e=8rqekN
[^5]: AMLE feature requests (Corey): https://hpe-aiatscale.slack.com/archives/CPVD08KD1/p1682777943035489?thread_ts=1681504314.537819&cid=CPVD08KD1
[^6]: AMLE feature requests (Garrett): https://hpe-aiatscale.slack.com/archives/CPVD08KD1/p1682962044009959?thread_ts=1681504314.537819&cid=CPVD08KD1
[^7]: AMLE feature requests (Liam): https://hpe-aiatscale.slack.com/archives/CPVD08KD1/p1682962178402109?thread_ts=1681504314.537819&cid=CPVD08KD1
[^8]: Recursion request for command support: https://hpe-aiatscale.slack.com/archives/CLXTF088G/p1674506192673319?thread_ts=1674503260.580589&cid=CLXTF088G

