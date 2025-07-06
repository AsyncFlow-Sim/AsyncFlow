Below an explanation for the unit tests in the file `tests/unit/simulation/test_simulation_input.py`

### 1. `test_normal_sets_variance_to_mean`

**Purpose:**
Checks that when you create an `RVConfig` with `distribution="normal"` and omit the `variance` field, the model automatically sets `variance = mean`.

* Verifies the “default variance” logic in the post‐init validator.

---

### 2. `test_poisson_keeps_variance_none`

**Purpose:**
Ensures that if you choose the Poisson distribution (`distribution="poisson"`) and do **not** supply a variance, the model **does not** fill in any default variance (keeps it `None`).

* Confirms that defaulting only applies to “normal”/“gaussian,” not to Poisson.

---

### 3. `test_explicit_variance_is_preserved`

**Purpose:**
Validates that if you explicitly pass a `variance` value—even for a distribution that would normally default—it remains exactly what you provided, and is coerced to float.

* Guards against accidental overwriting of user‐supplied variance.

---

### 4. `test_mean_must_be_numeric`

**Purpose:**
Verifies that giving a non‐numeric `mean` (e.g. a string) raises a `ValidationError` with our custom message `"mean must be a number"`.

* Tests the “before” validator on the `mean` field for type checking and coercion.

---

### 5. `test_missing_mean_field`

**Purpose:**
Ensures that completely omitting the `mean` key triggers a standard “field required” error.

* Confirms that `mean` is mandatory in the schema.

---

### 6. `test_gaussian_sets_variance_to_mean`

**Purpose:**
Exactly like the “normal” test above, but for `distribution="gaussian"`.

* Demonstrates that “gaussian” is treated as an alias for “normal” in the default‐variance logic.

---

### 7. `test_default_distribution_is_poisson`

**Purpose:**
Checks two things simultaneously:

1. When you omit `distribution`, it defaults to `"poisson"`.
2. In that default‐poisson case, `variance` remains `None`.

* Validates both the default distribution and its variance behavior in one test.

---

### 8. `test_explicit_variance_kept_for_poisson`

**Purpose:**
Confirms that even if you supply a `variance` when `distribution="poisson"`, the model preserves it rather than discarding it or forcing it back to `None`.

* Provides symmetry to the “explicit variance” test for non‐Poisson cases.

---

### 9. `test_invalid_distribution_raises`

**Purpose:**
Ensures that passing a value for `distribution` outside of the allowed literals (`"poisson"`, `"normal"`, `"gaussian"`) results in a `ValidationError`.

* Confirms that the `Literal[...]` constraint on `distribution` is enforced.

---

With these nine tests you fully cover:

1. **Defaulting behavior** for both “normal” and “gaussian.”
2. **No‐op behavior** for Poisson defaults.
3. **Preservation** of explicit user input.
4. **Type‐checking** on required fields.
5. **Literal‐constraint** enforcement.
