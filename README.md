# aws-annoying

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![CI](https://github.com/lasuillard/aws-annoying/actions/workflows/ci.yaml/badge.svg)](https://github.com/lasuillard/aws-annoying/actions/workflows/ci.yaml)
[![codecov](https://codecov.io/gh/lasuillard/aws-annoying/graph/badge.svg?token=gbcHMVVz2k)](https://codecov.io/gh/lasuillard/aws-annoying)
![PyPI - Version](https://img.shields.io/pypi/v/aws-annoying)

Utils to handle some annoying AWS tasks.

## ❓ About

This project aims to provide a set of utilities and examples to help with some annoying tasks when working with AWS.

Major directories of the project:

- **aws_annoying** Python package containing CLI and utility functions.
- **console** Utilities to help working with AWS Console.
- **examples** Examples of how to use the package.

## 🚀 Installation

It is recommended to use [pipx](https://pipx.pypa.io/stable/) to install `aws-annoying`:

```bash
$ pipx install aws-annoying
$ aws-annoying --help

 Usage: aws-annoying [OPTIONS] COMMAND [ARGS]...

...
```

Available commands:

- **ecs** ECS utilities.
  - **task-definition-lifecycle** Help to manage ECS task definitions lifecycle.
  - **wait-for-deployment** Wait for ECS deployment to complete.
- **load-variables** Wrapper command to run command with variables from AWS resources injected as environment variables.
- **mfa** Commands to manage MFA authentication.
  - **configure** Configure AWS profile for MFA.
- **session-manager** AWS Session Manager CLI utilities.
  - **install** Install AWS Session Manager plugin.
  - **port-forward** Start a port forwarding session using AWS Session Manager.
  - **start** Start new session.
  - **stop** Stop running session for PID file.

Please refer to the CLI help for more information about the available commands and options.

## 💖 Contributing

Any feedback, suggestions or contributions are welcome! Feel free to open an issue or a pull request.
