# Python SDK: Standards and Conventions
## Overview
We have prioritized work on Python SDK for Q3 and Q4 of 2023 with the motivation of increasing adoption of Determined as a platform. As a user-facing API into Determined features, we want the Python SDK to:
  - Empower users to create and manage automated workflows that fit their custom needs
    - Programmatic control of Determined objects and processes
  - Inspire confidence in the rest of the Determined platform with:
    - Ergonomic tools
    - Consistent, intuitive APIs

As we've been working towards these goals during Q3, we've formed some opinions about the shape and structure of the Python SDK as it evolves.

## Simplify Existing APIs
SDKs are built for easy integration with the overall platform. We want to make it as simple and intuitive as possible for developers to interact with the Determined platform. 

Today, the SDK offers a lot of methods, some of them are conceptually redundant with each other. We should not support auxiliary functions that provide minimal value and would be trivial for users to write themselves. These methods should be consolidated into more generic, powerful APIs.

### Consolidate various ways of fetching checkpoints
We support multiple ways of fetching checkpoints for an `Experiment`/`Trial`:
1. Experiment.top_checkpoint
   - Gets the checkpoint with best searcher metric for an experiment, dictated by `smaller_is_better` in the experiment config
2. Experiment.top_n_checkpoints
   - Sorts checkpoints by searcher metric, orders by `smaller_is_better`, and returns the top N checkpoints.
3. Trial.top_checkpoint
   - Gets the checkpoint with best searcher metric for a trial, dictated by `smaller_is_better` in the experiment config
4. Trial.select_checkpoint
   - Accepts various selection parameters (latest, best, uuid, searcher metric) to fetch a single checkpoint.
5. Trial.get_checkpoints
   - Accepts sorting and ordering parameters to fetch a list of checkpoints for a trial

These methods offer more confusion than convenience for an end user who is deciphering the best way to get checkpoints from their experiment or trial. We should consolidate them into a single `list_checkpoints` method on `Trial` and `Experiment` that offers a generic but powerful interface for filtering checkpoints. 

### Consolidate entrypoints SDK client instantiation
There are currently two ways of instantiating a Python SDK client:
1. `determined.experimental.client` module
   - Sufficient/ideal for most use cases
   - don't have to pass around an object everywhere
2. `determined.experimental.Determined` singleton
   - advanced use cases
   - different masters/users

XXX: should we consolidate these? 

### Deprecate and remove "user code"
We should not implement methods that are trivial for users to do themselves. This makes our APIs less intuitive and powerful for users, and introduces additional codepaths to maintain for us.
- `Checkpoint.write_metadata_file` simply dumps an attribute into a file. If this was actually useful, we should just create a generic interface for writing to a file.

## Implement consistent standards
We should maintain consistency in design, naming, and behavior across SDK components. The SDK should behave predictably and reliably, providing a stable interface for users.

### Fetching Resources
Getting a resource object from the server is a basic in SDK functionality. We should be consistent in implementing methods to get resources, both in naming and in interface.

SDK methods for fetching objects should function as a very thin wrapper around REST API calls. The client methods should contain very little logic whatsoever and should not order results from the server, because any querying or sorting optimizations will ultimately need to be implemented on the master and database side.

#### Collections
A common use case of the SDK is to be able to fetch, filter, and query collections of resources. For example, getting checkpoints for an experiment, all the models in the model registry, or trials for an experiment.

##### Lists
Most resource collections call the server with some specifiers and parse the response into SDK objects in a simple flat `List` type. These methods should follow a consistent standard:

- Naming should be clear and explicit: `list_{resource}s`
- Often lists need to be sorted and ordered. `list_*` should accept an optional `sort_by` parameter, usually of a pre-determined `Enum` type.
- If sorting is offered, it should be accompanied by an `order_by` parameter of `OrderBy` type, containing `OrderBy.ASC` and `OrderBy.DESC`.
- Since all results are fetched at once, an optional parameter `max_results: Optional[int]` should be accepted, which will limit the database query to the specified number of results.

*Example:*
```python
def list_checkpoints(
   sort_by: Union[checkpoint.CheckpointSortBy, str],
   order_by: checkpoint.CheckpointOrderBy,
   max_results: Optional[int]
) -> List[checkpoint.Checkpoint]
```

```python
latest_checkpoint = client.list_checkpoints(
   sort_by=checkpoint.CheckpointSortBy.REPORT_TIME,
   order_by=checkpoint.CheckpointOrderBy.DESC,
   max_results=1
)[0]
```
##### Iterators
Certain collections may be very large in size, and we want to reduce the latency of a single large network request. 

For these collections, we will offer an additional interface that returns a generator (iterator) which will call the server-side REST APIs in a paginated fashion. This allows for more flexibility in fetching large collections of resources and reduces the time of each network request. 

Which resources require this additional iterator method will be determined on a case-by-case basis. For example, the total number of `Project` resources that exists in a Determined instance is unlikely to require paging, but fetching all `Checkpoint`s is often a large and expensive request.

##### Querying
Querying a resource collection is a faster and more precise way of 
searching for specific objects. Currently, many methods accept function arguments as filter parameters, but this interface is not consistent and limited in functionality. It cannot take advantage of the server-side filtering capabilities offered, such as numeric operators (less than, greater than, etc.) and list inclusion (x IN y).

As SDK functionality grows, we need to introduce a better, more generic way of filtering. This is a proposal for a primitive but powerful interface to query objects, that takes advantage of existing server-side filtering options. 

Each query _clause_ consists of exactly one of each of the following:
- Parameter: usually a property of the class object (i.e. `start_time`, `id`, `status`) that we are querying by
- Value: static desired values of query parameter (i.e. `2023-09-14T18:21:02.788012028Z`, `100`, `State.COMPLETED`)
- Operator: mapping function between parameters and values (i.e. less than, greater than, in, etc.)

A _query_ consists of one or more _clauses_ joined by a _clause operator_: `AND` or `OR`.

Available parameters for querying should be documented. The client method will be responsible for validating that the parameters are valid for the corresponding REST API call, and translating the query into appropriate REST bindings. 

There are two different paths we can take for user-facing implementation of this concept.

**Option 1:** Query string interface
```python
exps = list_experiments(query="id >= 100 AND archived = true")
exps = list_experiments(query="id < 100 OR state IN [COMPLETED,STOPPED]")

```
Benefits:
- Readable, convenient string interface
- "Pythonic" operator syntax (`>`, `<=`)

Drawbacks:
- Defining lists is awkward
- Parsing introduces some unknowns 

**Option 2:** Dict filters interface
```python
list_experiments(filters={
   "id": {
      "gte": 100,
   },
   "archived": True,
   "state": {
      "in": ["COMPLETED", "STOPPED"],
   }
})
```
Benefits:
- Explicit, clear operator/clause structure
- Minimal parsing/translation needed
- Easy to implement `contains` operator
- Intuitive `AND` clauses

Drawbacks:
- Clunky to write for simple queries
- `OR` clause operator difficult to support


#### Single Objects
Some methods for fetching an object are redundant due to the resource having multiple unique identifiers (e.g. `get_user_by_username(username: str)` and `get_user_by_id(id: int)`). This is rarely necessary as a user should be able to rely on a single unique identifier to fetch a resource. Usually this identifier is in the form of a UUID, but in some cases it is more sensible to use a name string (provided it is unique). 

In cases where an object can have multiple unique identifiers, we should decide on the most intuitive identifier and only recognize one on the client. In the rare case that an object should be referred to by many identifiers, we should offer each identifier as a separate named function parameter and enforce client-side that only one is specified.

Fetching a single resource should be contained in a single method and contain a single identifier:
- Name: `get_{resource}`
- Fetching by a UUID: `get_resource(id: int)`
- If there are multiple, equally-valid identifiers: `get_resource(id: int, name: str)`

### Class Attributes
Many SDK resource objects, i.e. `Experiment`, `Trial`, `Model`, etc., do not have consistent methods for getting and setting object attributes. For example:
- `add_metadata` and `remove_metadata` exist on `Model`, but not `set_metadata`, while `set_labels` exists without `add_label`/`remove_label`
- `Model` and `Experiment` have `archive`/`unarchive` methods, but no `set_archived`
- `name` is a property of `Model` but lacks a corresponding `set_name`

Every primitive (of a built-in type) attribute on a resource class should have a corresponding `set_{attribute}` method. Attributes that are collection types should additionally have `add_{attribute}` and `remove_{attribute}` methods.

