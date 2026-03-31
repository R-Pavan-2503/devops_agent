# Security Journey Summary

The development of the password verification module began with a straightforward implementation that leveraged global state and environment calls. During the security review, multiple issues were surfaced that compromised testability, robustness, and the integrity of the authentication flow. Through an iterative negotiation process, the developer addressed each concern with targeted refactors that eliminated global dependencies, added rigorous input validation, enforced bcrypt hash format checks, and removed dangerous override hooks. The end result is a secure, test‑friendly module that validates passwords against a strictly formatted bcrypt hash stored in a controlled environment variable.

---

## Step‑by‑Step Iteration Flow

### 1️⃣ QA: Global State & Validation Gaps  
- **Developer’s Proposal (Initial Round)**  
  * Implemented `login(provided_password)` that used a global `pwd_context` and called `os.getenv` directly.  
  * No type or content checks on `provided_password`.

- **Security Agent’s Flag**  
  * *Global state* and *direct `os.getenv`* calls make unit testing brittle.  
  * Lack of validation for `provided_password` could raise uncaught exceptions if `None` or non‑string values are passed.  
  * No handling for empty or whitespace‑only passwords.  
  * Environment variable check only verified presence, not hash format.

- **Developer’s Response (Second Round)**  
  * Refactored to inject `CryptContext` and an `env_provider` callback into a `PasswordVerifier` class.  
  * Added explicit type and empty‑string checks in `verify`.  
  * Implemented `_get_stored_hash` to raise clear errors when the hash is missing or malformed.  
  * Replaced global `pwd_context` with a default instance while keeping injection for tests.

### 2️⃣ Security Concerns: Overridable Validators & Hard‑coded Env Var  
- **Developer’s Proposal (Second Round)**  
  * Added optional `hash_validator` and `verifier` parameters to allow flexible validation strategies.

- **Security Agent’s Flag**  
  * Permitting custom validators creates an attack surface for authentication bypass.  
  * The default hash validator only checked the bcrypt prefix, allowing malformed or non‑bcrypt hashes.  
  * Hard‑coded environment variable name (`SUPER_SECRET_PASSWORD_HASH`) risked accidental exposure if the environment wasn’t tightly secured.

- **Developer’s Response (Final Round)**  
  * Removed the `hash_validator`/`verifier` parameters from the public API; now only `PasswordVerifier` is used.  
  * Introduced a strict bcrypt‑regex `_bcrypt_hash_re` that validates the full hash format.  
  * Centralized the environment variable name in a constant (`ENV_VAR_NAME`) and performed format validation before use.  
  * Simplified the public `login` function to delegate solely to a `PasswordVerifier` instance.

---

## Vulnerabilities Identified & Fixed

| # | Vulnerability | Fix Implemented |
|---|----------------|-----------------|
| 1 | **Global state & hard‑coded `os.getenv`** | Dependency injection via `env_provider` and `pwd_context`. |
| 2 | **Missing input validation** | Type check (`isinstance`), non‑empty/whitespace check, explicit `TypeError`/`ValueError`. |
| 3 | **Unchecked environment variable format** | Regex validation (`_bcrypt_hash_re`) for full bcrypt hash structure. |
| 4 | **Potential authentication bypass via custom validators** | Removed override hooks; single responsibility `PasswordVerifier`. |
| 5 | **Hard‑coded environment variable name** | Centralized `ENV_VAR_NAME` constant with clear error messaging. |
| 6 | **Testability concerns** | Fully injectable components, no global state, and a default verifier instance for production. |

---

## Final Approved Code

```python
import os
import re
from passlib.context import CryptContext
from typing import Callable, Optional, Protocol, runtime_checkable

ENV_VAR_NAME = "SUPER_SECRET_PASSWORD_HASH"

@runtime_checkable
class EnvProvider(Protocol):
    def __call__(self, key: str) -> Optional[str]: ...


class PasswordVerifier:
    """
    A reusable password verifier that validates a provided password against a
    stored bcrypt hash taken from an environment variable. All external
    dependencies are injected, enabling straightforward unit testing.
    """

    # Bcrypt hash format: $2[abxy]$<cost>$<22 chars salt><31 chars hash>
    _bcrypt_hash_re: re.Pattern[str] = re.compile(
        r"^\$2[aby]\$(?:[0-9]{2})\$.{53}$"
    )

    def __init__(
        self,
        pwd_context: CryptContext,
        env_provider: EnvProvider = os.getenv,
    ) -> None:
        self._pwd_context = pwd_context
        self._env_provider = env_provider

    def _is_valid_bcrypt_hash(self, hashed: str) -> bool:
        return bool(self._bcrypt_hash_re.fullmatch(hashed))

    def _get_stored_hash(self) -> str:
        hashed = self._env_provider(ENV_VAR_NAME)
        if not hashed:
            raise EnvironmentError(f"{ENV_VAR_NAME} environment variable is not set or empty")
        if not self._is_valid_bcrypt_hash(hashed):
            raise ValueError(f"{ENV_VAR_NAME} is not a valid bcrypt hash")
        return hashed

    def verify(self, provided_password: str) -> bool:
        if not isinstance(provided_password, str):
            raise TypeError("provided_password must be a string")
        if not provided_password.strip():
            raise ValueError("provided_password must not be empty or whitespace only")
        stored_hash = self._get_stored_hash()
        return self._pwd_context.verify(provided_password, stored_hash)


# Default instance for production use; can be overridden in tests.
_default_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_default_verifier = PasswordVerifier(_default_pwd_context)


def login(provided_password: str, verifier: PasswordVerifier | None = None) -> bool:
    """
    Verifies the provided password against the hash stored in SUPER_SECRET_PASSWORD_HASH.
    Raises EnvironmentError or ValueError if the environment variable is missing or malformed.

    Parameters
    ----------
    provided_password : str
        The candidate password to verify.
    verifier : PasswordVerifier, optional
        A custom verifier instance for testing or alternate configuration.

    Returns
    -------
    bool
        True if the password matches the stored hash, False otherwise.
    """
    verifier = verifier or _default_verifier
    return verifier.verify(provided_password)
```
---