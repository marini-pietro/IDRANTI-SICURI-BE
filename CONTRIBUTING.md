# Contributing to IDRANTI SICURI BE

Thank you for considering contributing.  
This file contains high-level contribution guidelines and expectations.  
Please keep in mind that, because this codebase processes sensitive data related to municipality and public objects (i.e. hydrants) most external contributions related to the handling and distribution of data are unlikely to be accepted.  
If you want to contribute topics like documentation or underlying functionality like security or performance would be a much better fit.

## Notice

As explained in more detail in the README, this is a project I was invited to join by a professor in high school.  
I like the project and I have grown a lot as a developer because of it, but I probably will not keep working on this codebase once the project is shipped and in users' hands. University is taking priority, and I want to move on to other, more complex topics.    
Also, for larger contributions, such as a major rework of security handling, those changes will most likely stay in this repository (or in the generic clone I would create if I can no longer keep it open source) and serve as a template for future projects rather than being deployed directly to the end users.

## Scope

- Code changes: add features, fix bugs, or improve tests and documentation.
- Tests: any code change that affects behavior should be accompanied by tests (using pytest) the moment the code change is proposed in a PR.
- Security: when changing authentication, authorization, password handling, or token logic, include a short rationale and tests that demonstrate safe behavior.
  For security related code changes make as many commits as possible, to facilitate and speed up potential rollback.

## Guidelines

- Follow existing project structure and naming conventions, especially in `api_blueprints/` (automatic blueprint detection won't work otherwise).
- Linting, type hints and formatting (i personally used [black](https://pypi.org/project/black/) command) are preferable but not compulsory, general good written code will sufice.
- Add unit tests for new behaviors in `tests/` and ensure existing tests keep passing.
- General engineering hygiene (e.g. keep secrets out of the repository (placeholder secrets can be left hardcoded but have to be clearly documents as such) and to not add credentials, private keys, or tokens to commits)

## Review process

- Open a pull request describing the change, the reasoning, and test coverage.
- Ensure the PR includes updated or new tests and references any relevant issue addressed in the commits part of the PR.

## Testing

- Tests are pytest-based and can be found in the `tests/` tree.  
  Focus on small, isolated tests, especially for blueprints and logic regarding sensitive sections such as the authorization flow and input validation.
- Make sure to respect the naming convention already put in place and to document all relevant tests with extensive comments and, ideally, a docstring.

## Security sensitive changes

- For changes to authentication, password verification, token creation/validation, and input sanitization, include a concise security note in the PR describing the change, why it is safe and why the new solutions is better than the previous one.

## Contact

- If you need help or want to discuss a larger design change: open an issue adding the proper details (such as your hardware configuration or possible constraints) in the repository Github page.
