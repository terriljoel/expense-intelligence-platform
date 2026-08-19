# Code simplification plan

## Objective

Reduce repeated code and make the application easier to read without changing its
API, database schema, user interface, or behavior.

## Guardrails

- Keep each change small and independently testable.
- Refactor only repetition that has a clear shared meaning.
- Do not combine unrelated responsibilities merely to reduce line count.
- Do not change database migrations or public API contracts during cleanup.
- Run focused tests after each batch and the full suite before completion.
- Preserve existing uncommitted work.

## Baseline

- Ruff: passing
- Pytest: 111 passing
- JavaScript syntax checks: passing

## Ranked findings

1. **Draft receipt guard — high repetition, low risk.** Several service methods
   repeat the same locked receipt lookup and status check. Use one private helper.
2. **Household administration predicate — low repetition, low risk.** The UI
   repeats the owner/global-admin rule. Give that business rule one name.
3. **Expense category type — low repetition, low risk.** Receipt create and update
   schemas repeat the same category values. Define the type once.
4. **Route exception translation — high repetition, medium/high risk.** Messages
   and status codes vary by endpoint. Review separately; do not introduce a broad
   exception wrapper merely to reduce lines.
5. **Large dashboard and capture functions — high size, unproven redundancy.**
   Split only around cohesive responsibilities, with characterization tests first.
6. **Large frontend module — medium risk.** Modularization may improve navigation,
   but it changes asset loading and deployment behavior. Defer until the low-risk
   cleanup is complete.

## Intentionally avoided

- Generic repository layers over SQLAlchemy
- Universal exception wrappers
- Minified or compressed source code
- Database changes for a code-only cleanup

These can reduce visible lines while making behavior harder to trace.


# Code simplification plan

## Objective and guardrails

Reduce repeated code without changing the API, database schema, user interface,
or behavior. Keep changes small, preserve existing uncommitted work, and validate
each batch with focused tests followed by the complete suite.

Do not introduce generic repository layers, universal exception wrappers,
minified source, or database changes merely to reduce visible line count.

## Ranked review findings

1. Repeated draft-receipt guard: high repetition, low risk — completed.
2. Repeated update-request validation: high repetition, low risk — completed.
3. Repeated category definitions: low repetition, low risk — completed.
4. Repeated active payment-method lookups: medium repetition, low risk — completed.
5. Route exception translation: high repetition, medium/high risk — deferred because
   endpoint messages and status codes are not uniform.
6. Large dashboard/capture functions: high size but unproven redundancy — split
   only after adding characterization tests around their output.
7. Large frontend module: modularization could improve navigation, but changes asset
   loading and deployment behavior — defer until a dedicated frontend pass.

## Completed passes

### Pass 1

- Centralized the locked draft-receipt editability guard.
- Defined receipt expense categories once.
- Named the frontend household-administration rule.
- Net production-code reduction: 33 lines.

### Pass 2

- Centralized identical update-request validation in `UpdateRequest`.
- Kept payment-method update validation separate because its messages differ.
- Defined income categories once.
- Reused the payment-method service for active receipt-payment lookups.
- Replaced a query that loaded every active method with a single-ID lookup.
- Net production-code reduction: 19 lines.

Together the passes remove 52 production-code lines. Ruff, frontend syntax
validation, and all 111 tests pass after the changes.
