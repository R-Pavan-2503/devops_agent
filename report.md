# DevOps Agent Negotiation Report

## **1. Security Journey Summary**

- **Initial State** – A simple `login()` function was provided that validated a password against a single bcrypt hash stored in an environment variable.  
- **First Critique** – Security Agent highlighted missing password type validation, lack of per‑user checks, and brittle handling of the environment variable.  
- **Developer Response** – Added input validation, refactored to use a JSON‑encoded mapping of usernames to hashes, and introduced graceful fallbacks for missing or malformed configuration.  
- **Second Critique** – Agent pointed out that the function ignored the `username` argument entirely and that the hard‑coded `os.getenv` made testing difficult.  
- **Final Fixes** – Implemented per‑user authentication logic, injected an environment‑retrieval callback for testability, and enhanced error handling to avoid runtime crashes.  
- **Outcome** – The code now meets security best practices and is robust against common edge cases.

---

## **2. Step‑by‑Step Iteration Flow**

| Iteration | Developer Proposal | Security Agent Feedback | Developer Fix |
|-----------|---------------------|--------------------------|---------------|
| **Iteration 0** (Original) | Simple `login()` that compared the supplied password to a single bcrypt hash from `os.getenv("USER_PASSWORD_HASH")`. | *Vulnerability*: No validation of `password` type → `AttributeError` on non‑string values.<br>*Vulnerability*: Dependence on a hard‑coded environment variable without injection → hard to test.<br>*Vulnerability*: Lacks per‑user authentication → any user can log in if the password matches. | Not applicable – this was the starting point. |
| **Iteration 1** | Updated function to (a) check that `password` is a `str`; (b) load the environment variable; (c) return `False` if the variable is missing. | *Issue*: Function still ignored `username` → same password used for every user.<br>*Issue*: Environment variable missing causes unhandled exception (potential DoS). | Rewrote logic to accept a **JSON mapping** of usernames to bcrypt hashes, and added **graceful handling** of missing/malformed env vars. |
| **Iteration 2** | Introduced a `get_env` callback parameter to allow injection of environment retrieval for testing; added checks for JSON structure and hash validity; ensured bcrypt comparison uses bytes. | *Issue*: Function still didn’t enforce per‑user hash look‑ups; error handling around `bcrypt.checkpw` was missing.<br>*Issue*: No explicit type validation for the `password` argument after refactor. | Finalized the code: <br>• Validates `password` type.<br>• Retrieves JSON mapping via `get_env`.<br>• Looks up the hash for the given `username`.<br>• Handles all error conditions (missing var, bad JSON, missing user, invalid hash).<br>• Returns `False` for any failure, never raising exceptions. |

---

## **3. Vulnerabilities Identified & Fixed**

| Category | Vulnerability | Fix Implemented |
|----------|---------------|-----------------|
| **Input Validation** | `password` may be non‑string → `AttributeError`. | Explicit `isinstance(password, str)` check; return `False` on invalid type. |
| **Configuration Injection** | Hard‑coded `os.getenv` → hard to unit‑test. | Added `get_env` callback parameter with default `os.getenv`. |
| **Environment Variable Handling** | Missing/empty env var → crash. | Graceful fallback: if `env_value` is falsy, return `False`. |
| **JSON Parsing** | Malformed JSON → `json.JSONDecodeError`. | Wrapped `json.loads` in `try/except`; return `False` on decode error. |
| **Data Structure Validation** | Non‑dict JSON or missing user → `TypeError`. | Check `isinstance(user_hash_map, dict)` and `isinstance(stored_hash, str)` before use. |
| **Per‑User Authentication** | Same password accepted for any username. | Store a **JSON map** of `username → bcrypt hash` and enforce lookup of the specific user’s hash. |
| **bcrypt Error Handling** | `bcrypt.checkpw` could raise `ValueError/TypeError`. | Wrapped call in `try/except`; return `False` on failure. |
| **Return Semantics** | Unhandled exceptions could leak stack traces. | All failure paths return `False`; no exceptions propagate. |

---

## **4. Final Approved Code**

```python
import os
import json
import bcrypt
from typing import Any, Callable, Optional

def login(
    username: str,
    password: Any,
    *,
    get_env: Callable[[str], Optional[str]] = os.getenv,
    env_var: str = "USER_PASSWORD_HASH",
) -> bool:
    """
    Securely verify a user's password against a per-user bcrypt hash
    stored in an environment variable.

    The environment variable must contain a JSON object mapping usernames
    to their corresponding bcrypt hash strings. Example:
        {
            "alice": "$2b$12$...",
            "bob": "$2b$12$..."
        }

    Parameters
    ----------
    username : str
        The user's username.
    password : Any
        The plaintext password provided by the user. Must be a string.
    get_env : Callable[[str], Optional[str]], optional
        Function to retrieve environment variables. Defaults to ``os.getenv``.
    env_var : str, optional
        Name of the environment variable that contains the JSON mapping.

    Returns
    -------
    bool
        ``True`` if the password matches the stored hash for the user,
        ``False`` otherwise (including when the environment variable is missing
        or malformed).
    """
    # Validate password type
    if not isinstance(password, str):
        return False

    # Retrieve the JSON mapping from the environment
    env_value = get_env(env_var)
    if not env_value:
        # Gracefully handle missing environment variable
        return False

    try:
        user_hash_map = json.loads(env_value)
    except json.JSONDecodeError:
        # Malformed JSON; cannot authenticate
        return False

    if not isinstance(user_hash_map, dict):
        return False

    # Fetch the hash for the specific user
    stored_hash = user_hash_map.get(username)
    if not isinstance(stored_hash, str):
        return False

    try:
        # bcrypt.checkpw expects bytes
        return bcrypt.checkpw(password.encode("utf-8"), stored_hash.encode("utf-8"))
    except (ValueError, TypeError):
        # Invalid hash format or other errors
        return False
```

---