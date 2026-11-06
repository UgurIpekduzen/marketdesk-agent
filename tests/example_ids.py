"""One helper the example-set tests share: the id of an example, as the name of
its parametrized test."""


def by_id(example: dict) -> str:
    return example["id"]
