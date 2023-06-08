# Exercise 1: Gradients

#### Variables and Definitions
$y$: observed output
$\hat{y}$: predicted value of $y$
$x$: input value
$\hat{y} = mx$: model equation
##### Data set
```math
y(1) = 1 \\
y(2) = 2 \\
y(3) = 3 \\
y(4) = 4
```
---
**Q1**: Looking at the dataset, explain why m=1 is correct before proceeding with further math.

**Answer**:
There exists one value for $m$, ($m = 1$), that would satisfy the model equation $\hat{y} = mx$ for all the 4 data points given.

For every input in our data set, $x = y$, so given our linear model, it follows that 
```math
m = \frac{\hat{y}}{x} = 1
```
---
**Q2**: Can $loss_{point}$ or $loss_{mse}$ ever be negative? Why or why not, and does this make logical sense to you?

**Answer**:
No. In general it's possible for arbitrary loss functions to have negative values, but in this particular loss function, the loss can never be negative. Mathematically, it is the square of the difference between expected and actual outputs which must be positive. Intuitively, the loss represents the amount of error in the model, and the minimum error is no error.

---
**Q3**: 

With $m = 2$, complete the following table by calculating the loss for each
point of our dataset:
$N = 4$
$\hat{y} = mx$
```math
loss_{point} = \frac{(y - \hat{y})^2}{N} = \frac{(y - 2x)^2}{4}
```

| $x$ | $y$ | $\hat{y}$ | $loss_{point}$                      |
| --- | --- | --------- | ----------------------------------- |
| 1   | 1   | 2         | $\frac{(1 - 2)^2}{4} = \frac{1}{4}$ |
| 2   | 2   | 4         | $\frac{(2 - 4)^2}{4} = 1$           |
| 3   | 3   | 6         | $\frac{(3 - 6)^2}{4} = \frac{9}{4}$ |
| 4   | 4   | 8         | $\frac{(4 - 8)^2}{4} = 4$           |

Also calculate the total $loss_{mse}$ for the whole dataset:
```math
loss_{mse} = \sum_{k=1}^N\frac{(y_k - \hat{y}_k)^2}{N}
```
| $loss_{mse}$                                             |
| -------------------------------------------------------- |
| $\frac{1}{4} + 1 + \frac{9}{4} + 4 = \frac{30}{4} = 7.5$ |

---
**Q4**: Write a function for calculating the total `loss_mse`, which takes as input the current model weight `m` and a list of data points `[(x, ytrue), ...]`, and returns the floating-point `loss_mse`.
**Answer**:
```python
def loss_mse(m: float, data: List[Tuple[int, int]]):
    n = len(data)
    ypred = lambda x: m * x
    loss_fn = lambda x, y: ((y - ypred(x)) ** 2) / n
    return sum([loss_fn(x, y) for (x, y) in data])
```
---

**Q5**: Write a function to calculate the gradient for a single data point.  It should
take `m`, a single `(x, ytrue)` pair, and `N` as inputs and return
`dloss_point/dm`.

You can test with:

```python
assert grad_point(m=2, data=(1, 1), N=4) == 0.5
assert grad_point(m=2, data=(2, 2), N=4) == 2.0
```

**Answer**:
```python
def grad_point(m: float, data: Tuple[int, int], N: int):
    x, y = data
    ypred = lambda x: m * x
    return (1 / N) * (-2 * x) * (y - ypred(x))
```

Then write a function to calculate the total gradient for a list of `(x,
ytrue)` pairs.  It should take `m` and a list of `(x, ytrue)` pairs as inputs.

You can test with:

```python
assert grad_multi(m=2, data=[(1, 1), (2, 2), (3, 3), (4, 4)]) == 15.0
```

Is it mathematically valid to call the first function from the second function
to simplify writing the second?  Why or why not?

**Answer**:
Yes, it is valid. According to the sum rule, the derivative of a sum is the sum of the derivatives. 
```math
loss_{mse} = \sum_{k=1}^N loss_k 
\\
\frac{\partial loss_{mse}}{\partial m} = \sum_{k=1}^N \frac{\partial{loss_k}}{\partial m}
```
where $\frac{\partial{loss_k}}{\partial m}$ is `grad_point` and $\frac{\partial loss_{mse}}{\partial m}$ is `grad_multi`

---
**Q6**: Write a training loop to do gradient descent on our `ypred = m*x` model. Your function should take the following inputs:

- initial model weight `m`
- a learning rate `lr` for calculating the step
- a dataset, which is a list of `(x, ytrue)` data pairs
- a number of iterations to do

Your function should return the final trained weight m.

**Answer**:
```python
def train_loop(m: float, lr: float, dataset: List[Tuple[int, int]], iterations: int):
    for i in range(iterations):
        # Loop around over dataset.
        x, y = dataset[i % len(dataset)]
        y_pred = m * x
        grad = (-2 * x) * (y - y_pred)
        m -= lr * grad

    return m
```
---
**Q7**: What happens if you set the learning rate way too low? Describe what is happening.

**Answer**:
The final weight is smaller as a result of each weight update step being smaller. Learning rate effectively controls the "importance" of each weight update, so a very small gradient update would result in slower training.

---

**Q8**: What happens if you set the learning rate way too high? Describe what is happening.

**Answer**:
The model weight varies significantly between each iteration step as a result of each gradient update affecting the weight greatly. A very large learning rate will make weights unstable and the model loss is unlikely to converge.

---
**Q9**: Which learning rates cause training to diverge? Which learning rates cause the model to converge to 1? Are there values which are somewhere in between?
**Answer**:
At learning rates below `0.064` the model converges to 1, and at `0.256` they diverge. Between these values, the model seems to get stuck and converges to wrong values.

---
**Q10**:
Let `m=2` and fill the following table of per-data-point gradients:

| `(x, ytrue)` | `grad_point` |
| ------------ | ------------ |
| (1, 0)       | 4            |
| (2, 1)       | 12           |
| (3, 1)       | 30           |
| (4, 6.25)    | 14           |

Then, with `m=2`, fill the following table of `batch_size=2` batch gradients:

| `(x1, ytrue1)` | `(x2, ytrue2)` | `grad_multi` |
| -------------- | -------------- | ------------ |
| (1, 0)         | (2, 1)         | 8            |
| (3, 1)         | (4, 6.25)      | 22           |

Do you see that by averaging gradients from multiple points, we end up with
smoother overall gradients?

---
**Q11**:
**Answer**:
```python
def train_loop_batches(m: float, lr: float, dataset: List[List[Tuple[int, int]]], iterations: int):
    for i in range(iterations):
        # Loop around over dataset.
        batch = dataset[i % len(dataset)]
        step = lr * grad_multi(m, batch)
        m -= step

    return m
```
---
**Q12**: Write a training loop that simulates data-parallel distributed training. No need for actual distributed mechanics; just do it inside a single process.
**Answer**:
```python
def train_loop_distributed(m: float, lr: float, dataset: List[List[List[Tuple[int, int]]]], iterations: int):
    for i in range(iterations):
        grad = sum(grad_multi(m, shard[i % len(shard)]) for shard in dataset) / len(dataset)
        m -= lr * grad
    return m
```
Explain why you see the same training result with the `train_loop_batches` you wrote previously:
**Answer**:
We are averaging over the same data points. In `train_loop_batches` we average across the batch; in `train_loop_distributed` this batch is split amongst the worker shards, then averaged. 
Logically, $\frac{A + B + C + D}{4} = \frac{\frac{A + B}{2} + \frac{C + D}{2}}{2}$

---