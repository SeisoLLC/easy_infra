# Contributing

1. [Fork the repository](https://github.com/SeisoLLC/easy_infra/fork)
1. Create a feature branch via `git checkout -b feature/description`
1. Make your changes
1. Commit your changes via `git commit -am 'Summarize the changes here'`
1. Create a new pull request ([how-to](https://help.github.com/articles/creating-a-pull-request/))

## Running tests

If you are attempting to run the tests locally, consider running the following
to ensure that the user from inside the container can write to the host:

```bash
find tests -mindepth 1 -type d -exec chmod o+w {} \;
```
