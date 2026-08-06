```markdown
# gnomledger Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill teaches the core development patterns and conventions used in the `gnomledger` repository, a Python codebase utilizing the Vite framework. It covers file naming, import/export styles, commit message conventions, and testing patterns, providing practical examples and suggested commands for common workflows.

## Coding Conventions

### File Naming
- Use **camelCase** for file names.
  - Example: `userProfile.py`, `transactionManager.py`

### Import Style
- Use **relative imports** within the codebase.
  - Example:
    ```python
    from .utils import calculateBalance
    ```

### Export Style
- Use **default exports** (Python modules export all top-level functions/classes by default).
  - Example:
    ```python
    # In accountManager.py
    class AccountManager:
        ...
    ```

### Commit Message Conventions
- Use **conventional commits** with the `feat` prefix for new features.
- Commit messages average 78 characters in length.
  - Example:
    ```
    feat: add support for recurring transactions in ledger view
    ```

## Workflows

### Feature Development
**Trigger:** When adding a new feature to the codebase  
**Command:** `/feature-dev`

1. Create a new branch for your feature.
2. Implement the feature using camelCase file naming and relative imports.
3. Write or update tests in `*.test.*` files.
4. Commit your changes using the `feat` prefix and a descriptive message.
5. Push your branch and open a pull request.

### Code Testing
**Trigger:** When verifying code correctness  
**Command:** `/run-tests`

1. Locate or create test files matching the `*.test.*` pattern.
2. Run the test suite using the project's preferred test runner (framework unknown; check project docs or `requirements.txt`).
3. Review test results and fix any failing tests.

## Testing Patterns

- Test files follow the `*.test.*` naming pattern (e.g., `accountManager.test.py`).
- The specific testing framework is not detected; check project documentation for details.
- Place tests alongside or near the modules they cover.

  Example test file:
  ```python
  # accountManager.test.py
  from .accountManager import AccountManager

  def test_account_creation():
      manager = AccountManager()
      assert manager.create_account('Alice') is not None
  ```

## Commands
| Command         | Purpose                                   |
|-----------------|-------------------------------------------|
| /feature-dev    | Start a new feature development workflow   |
| /run-tests      | Run the test suite                        |
```
