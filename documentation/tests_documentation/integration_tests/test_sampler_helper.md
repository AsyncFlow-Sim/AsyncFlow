Below is a guided walkthrough of **`tests/unit/simulation/test_sampler_helper.py`**, explaining core ideas and each test’s intent.

---

## File purpose

This file verifies that your three helper functions—

* `uniform_variable_generator`
* `poisson_variable_generator`
* `truncated_gaussian_generator`

—correctly delegate to whatever RNG you pass in, and fall back to NumPy’s default RNG when you don’t provide one.

---

## Key testing patterns

1. **Dependency injection via `rng`**
   Each helper takes an `rng` parameter. In production you’ll pass a `np.random.Generator`; in tests we inject a **`DummyRNG`** with predictable outputs to make our tests **deterministic**.

2. **Duck typing**
   Python doesn’t require `rng` to be a specific class—only that it implements the required methods (`random()`, `poisson(mean)`, `normal(mean, sigma)`). Our `DummyRNG` simply implements those three methods.

3. **`typing.cast` for static typing**
   We wrap `DummyRNG` instances in `cast("np.random.Generator", DummyRNG(...))` so mypy sees them as satisfying the generator type, but at runtime they remain our dummy.

---

## Test-by-test breakdown

| Test name                                                            | What it checks                                                                                                                  |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| **`test_uniform_variable_generator_with_dummy_rng`**                 | Passing a `DummyRNG(uniform_value=0.75)`, `rng.random()` returns 0.75 → helper must return exactly 0.75.                        |
| **`test_uniform_variable_generator_default_rng_range`**              | Without supplying `rng`, the helper uses `default_rng()`. We call it 100× to ensure it always returns a `float` in \[0.0, 1.0). |
| **`test_poisson_variable_generator_with_dummy_rng`**                 | With `DummyRNG(poisson_value=3)`, `rng.poisson(mean)` yields 3 → helper returns 3.                                              |
| **`test_poisson_variable_generator_reproducible`**                   | Two NumPy generators created with the same seed (`12345`) must produce the same Poisson sample for `mean=10.0`.                 |
| **`test_truncated_gaussian_generator_truncates_negative`**           | `DummyRNG(normal_value=-2.7)` forces a negative draw: helper must clamp it to **0**.                                            |
| **`test_truncated_gaussian_generator_truncates_toward_zero`**        | `DummyRNG(normal_value=3.9)` forces a positive draw: helper must cast/round toward zero (int(3.9) → **3**).                     |
| **`test_truncated_gaussian_generator_default_rng_non_negative_int`** | With a real seeded RNG, helper must produce **some** non-negative `int` (verifies default fallback path is valid).              |

---

## Why this matters

* **Deterministic behavior**: by forcing the RNG’s output via `DummyRNG`, we can assert exactly how our helpers transform that value (clamping, rounding, type conversion).
* **Fallbacks work**: tests with **no** `rng` verify that calling `default_rng()` still gives valid outputs of the correct type and range.
* **Type safety**: using `cast(...)` silences mypy errors while still executing our dummy logic at runtime—ensuring we meet both static‐typing and functional correctness goals.

With this suite, you have **full confidence** that your sampling helpers behave correctly under both controlled (dummy) and uncontrolled (default) RNG conditions.
